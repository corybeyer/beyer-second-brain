"""Azure Functions app using v2 programming model.

Requires AzureWebJobsFeatureFlags=EnableWorkerIndexing app setting.

Implements System Behavior patterns from CLAUDE.md:
- Validation (size limits, magic bytes, minimum text)
- Processing states
- Structured logging with timing
- Cost controls

Architecture:
- Blob trigger: Parse → Chunk → Store (fast, always completes)
- Timer trigger: Embed → Extract Concepts (resumable, self-healing)

The blob trigger stores chunks with PENDING status. The timer function
processes pending chunks in batches, enabling large documents to complete
across multiple timer invocations.
"""

import logging
import os

import azure.functions as func

# Lazy imports to avoid startup failures - these are imported inside functions
# from shared.chunker import chunk_document
# from shared.logging_utils import structured_logger
# from shared.parser import detect_file_type, parse_pdf
# from shared.storage import store_document
# from shared.validation import (...)

app = func.FunctionApp()


@app.function_name(name="health")
@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint to verify function deployment.

    This function has no dependencies beyond azure.functions,
    so it should always work if deployment succeeded.

    Test with: curl https://func-secondbrain.azurewebsites.net/api/health
    """
    import sys

    # Test imports and report which ones fail
    import_status = {}

    modules_to_test = [
        ("fitz", "PyMuPDF - PDF parsing"),
        ("pyodbc", "pyodbc - SQL Server connection"),
        ("anthropic", "anthropic - Claude API"),
        ("openai", "openai - Embeddings API"),
    ]

    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            import_status[module_name] = "OK"
        except ImportError as e:
            import_status[module_name] = f"FAILED: {e}"
        except Exception as e:
            import_status[module_name] = f"ERROR: {type(e).__name__}: {e}"

    # Build response
    lines = [
        "Second Brain Function App - Health Check",
        "=" * 40,
        f"Python version: {sys.version}",
        f"Platform: {sys.platform}",
        "",
        "Import Status:",
    ]

    all_ok = True
    for module_name, status in import_status.items():
        lines.append(f"  {module_name}: {status}")
        if status != "OK":
            all_ok = False

    lines.append("")
    lines.append(f"Overall: {'HEALTHY' if all_ok else 'UNHEALTHY - check imports above'}")

    return func.HttpResponse(
        "\n".join(lines),
        status_code=200 if all_ok else 500,
        mimetype="text/plain"
    )


@app.blob_trigger(
    arg_name="blob",
    path="documents/{name}",
    connection="AzureWebJobsStorage",
)
def ingest_document(blob: func.InputStream) -> None:
    """Process uploaded document with full validation and observability.

    Implements System Behavior patterns:
    - Input validation (size, magic bytes, file type)
    - Processing state tracking
    - Cost controls (page/chunk limits)
    - Structured JSON logging with timing
    - Minimum text validation for scanned PDFs

    Args:
        blob: Input stream from blob trigger
    """
    # Lazy imports to avoid startup failures
    from shared.chunker import chunk_document
    from shared.logging_utils import structured_logger
    from shared.parser import detect_file_type, parse_pdf
    from shared.storage import store_document
    from shared.validation import (
        ProcessingStatus,
        validate_chunk_count,
        validate_chunk_positions,
        validate_file_size,
        validate_minimum_text,
        validate_page_count,
        validate_pdf_magic_bytes,
    )

    filename = blob.name or "unknown"
    file_size = blob.length or 0
    status_str = "UPLOADED"  # Track status as string for finally block

    # Set logging context for all subsequent logs
    structured_logger.set_context(file_path=filename)

    try:
        # === VALIDATION PHASE ===
        status = ProcessingStatus.PARSING
        status_str = "PARSING"

        # 1. Validate file size (cost control)
        size_result = validate_file_size(file_size)
        if not size_result.is_valid:
            structured_logger.error(
                "validate",
                size_result.error_message or "File size validation failed",
                file_size=file_size,
            )
            return

        structured_logger.info(
            "validate",
            "File size within limits",
            file_size=file_size,
        )

        # 2. Detect file type by extension
        file_type = detect_file_type(filename)
        if file_type != "pdf":
            structured_logger.warning(
                "validate",
                f"Unsupported file type: {file_type}",
                file_type=file_type,
            )
            return

        # 3. Read content
        with structured_logger.timed_operation("read", "Read blob content") as ctx:
            content = blob.read()
            ctx["bytes_read"] = len(content)

        # 4. Validate magic bytes (security: ensure it's really a PDF)
        magic_result = validate_pdf_magic_bytes(content)
        if not magic_result.is_valid:
            structured_logger.error(
                "validate",
                magic_result.error_message or "Magic bytes validation failed",
            )
            status = ProcessingStatus.PARSE_FAILED
            status_str = "PARSE_FAILED"
            # TODO: Store status in DB when implemented
            return

        structured_logger.info("validate", "PDF magic bytes valid")

        # === PARSING PHASE ===
        with structured_logger.timed_operation("parse", "Parse PDF document") as ctx:
            doc = parse_pdf(content, filename)
            ctx["page_count"] = doc.page_count
            ctx["title"] = doc.title
            ctx["author"] = doc.author

        # 5. Validate page count (cost control)
        page_result = validate_page_count(doc.page_count)
        if not page_result.is_valid:
            structured_logger.error(
                "validate",
                page_result.error_message or "Page count validation failed",
                page_count=doc.page_count,
            )
            status = ProcessingStatus.PARSE_FAILED
            status_str = "PARSE_FAILED"
            return

        # 6. Validate minimum text (catch scanned/image PDFs)
        text_result = validate_minimum_text(doc.full_text)
        if not text_result.is_valid:
            structured_logger.error(
                "validate",
                text_result.error_message or "Minimum text validation failed",
                text_length=len(doc.full_text.strip()),
            )
            status = ProcessingStatus.PARSE_FAILED
            status_str = "PARSE_FAILED"
            return

        structured_logger.info(
            "parse",
            "Document parsed successfully",
            page_count=doc.page_count,
            text_length=len(doc.full_text),
        )

        # === CHUNKING PHASE ===
        with structured_logger.timed_operation("chunk", "Chunk document") as ctx:
            chunks = chunk_document(doc, max_chunk_size=2000, overlap=200)
            ctx["chunks_created"] = len(chunks)

        # 7. Validate chunk count (cost control)
        chunk_count_result = validate_chunk_count(len(chunks))
        if not chunk_count_result.is_valid:
            structured_logger.error(
                "validate",
                chunk_count_result.error_message or "Chunk count validation failed",
                chunk_count=len(chunks),
            )
            status = ProcessingStatus.PARSE_FAILED
            status_str = "PARSE_FAILED"
            return

        # 8. Validate chunk positions are sequential (invariant)
        position_result = validate_chunk_positions(chunks)
        if not position_result.is_valid:
            structured_logger.error(
                "validate",
                position_result.error_message or "Chunk positions invalid",
            )
            status = ProcessingStatus.PARSE_FAILED
            status_str = "PARSE_FAILED"
            return

        # 9. Validate at least one chunk exists (invariant for COMPLETE status)
        if len(chunks) == 0:
            structured_logger.error(
                "validate",
                "No chunks created from document",
            )
            status = ProcessingStatus.PARSE_FAILED
            status_str = "PARSE_FAILED"
            return

        status = ProcessingStatus.PARSED
        status_str = "PARSED"

        # Log document structure
        structure = {
            "filename": doc.filename,
            "title": doc.title,
            "author": doc.author,
            "page_count": doc.page_count,
            "chunk_count": len(chunks),
            "metadata": doc.metadata,
        }
        structured_logger.info(
            "parse",
            "Document structure extracted",
            structure=structure,
        )

        # === STORAGE PHASE ===
        # Store document and chunks with idempotency (delete-and-replace)
        # Chunks are stored with embedding_status=PENDING, concept_status=PENDING
        # The timer function will process these asynchronously
        with structured_logger.timed_operation("store", "Store in database") as ctx:
            source_id = store_document(doc, chunks, filename)
            ctx["source_id"] = source_id
            ctx["chunk_count"] = len(chunks)

        structured_logger.info(
            "store",
            "Document stored successfully",
            source_id=source_id,
            chunk_count=len(chunks),
        )

        # Blob trigger complete - timer function will handle embedding and concepts
        # Source remains in PARSED status until timer completes all chunks
        structured_logger.info(
            "complete",
            "Blob trigger complete - chunks queued for processing",
            source_id=source_id,
            chunk_count=len(chunks),
            status=status_str,
        )

    except Exception as e:
        status_str = "PARSE_FAILED"
        logging.error(f"Processing failed: {e!s}", exc_info=True)
        # Re-raise to let Azure Functions handle retry
        raise

    finally:
        logging.info(f"Processing finished with status: {status_str}")
        try:
            structured_logger.clear_context()
        except Exception:
            pass  # Ignore if logger wasn't initialized


@app.timer_trigger(
    schedule="0 */5 * * * *",  # Every 5 minutes
    arg_name="timer",
    run_on_startup=False,
)
def process_pending_chunks(timer: func.TimerRequest) -> None:
    """Process pending embeddings and concept extraction.

    This timer function runs every 5 minutes to process chunks that need
    embeddings or concept extraction. It implements the "early exit" pattern:
    if no work is pending, it exits immediately (minimal cost).

    The function processes work in batches to stay within the 10-minute
    timeout limit. If it doesn't finish, the next invocation continues
    where it left off.

    Processing order:
    1. Generate embeddings for chunks with embedding_status=PENDING
    2. Extract concepts for chunks with concept_status=PENDING
       (only after embeddings are complete)
    3. Update source status to COMPLETE when all chunks are done
    """
    import time

    from shared.chunker import Chunk
    from shared.concepts import extract_concepts_from_chunk
    from shared.embeddings import get_embedding
    from shared.graph import store_chunk_extraction_standalone
    from shared.logging_utils import structured_logger
    from shared.storage import (
        check_source_complete,
        get_pending_concept_chunks,
        get_pending_embedding_chunks,
        get_processing_stats,
        update_chunk_concept_status,
        update_chunk_embedding,
        update_chunk_embedding_failed,
        update_source_status,
    )

    start_time = time.time()
    MAX_RUNTIME_SECONDS = 540  # 9 minutes (leave 1 min buffer before 10 min timeout)

    structured_logger.info(
        "timer",
        "Timer function started",
        is_past_due=timer.past_due,
    )

    # === EARLY EXIT CHECK ===
    stats = get_processing_stats()
    pending_embeddings = stats.get("pending_embeddings", 0)
    pending_concepts = stats.get("pending_concepts", 0)

    if pending_embeddings == 0 and pending_concepts == 0:
        structured_logger.info(
            "timer",
            "No pending work - early exit",
            stats=stats,
        )
        return

    structured_logger.info(
        "timer",
        "Pending work found",
        pending_embeddings=pending_embeddings,
        pending_concepts=pending_concepts,
    )

    # Track which sources we process for status updates
    processed_source_ids: set[int] = set()
    embeddings_processed = 0
    concepts_processed = 0

    # === PHASE 1: EMBEDDINGS ===
    if pending_embeddings > 0:
        structured_logger.info(
            "timer",
            "Starting embedding phase",
            pending=pending_embeddings,
        )

        # Get batch of pending chunks
        pending_chunks = get_pending_embedding_chunks(limit=500)

        for chunk_data in pending_chunks:
            # Check if we're running out of time
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME_SECONDS:
                structured_logger.info(
                    "timer",
                    "Approaching timeout - stopping embedding phase",
                    elapsed_seconds=elapsed,
                    embeddings_processed=embeddings_processed,
                )
                break

            try:
                # Generate embedding
                embedding = get_embedding(chunk_data["text"])

                # Update chunk with embedding
                update_chunk_embedding(chunk_data["id"], embedding)

                embeddings_processed += 1
                processed_source_ids.add(chunk_data["source_id"])

                if embeddings_processed % 50 == 0:
                    structured_logger.info(
                        "timer",
                        f"Embedded {embeddings_processed} chunks",
                        embeddings_processed=embeddings_processed,
                    )

            except Exception as e:
                # Mark as failed, will retry up to 3 times
                update_chunk_embedding_failed(chunk_data["id"], str(e)[:500])
                structured_logger.warning(
                    "timer",
                    f"Embedding failed for chunk {chunk_data['id']}",
                    error=str(e),
                )

        structured_logger.info(
            "timer",
            "Embedding phase complete",
            embeddings_processed=embeddings_processed,
        )

    # === PHASE 2: CONCEPT EXTRACTION ===
    elapsed = time.time() - start_time
    if elapsed < MAX_RUNTIME_SECONDS and pending_concepts > 0:
        structured_logger.info(
            "timer",
            "Starting concept extraction phase",
            pending=pending_concepts,
        )

        # Get batch of pending chunks (only those with embeddings complete)
        pending_chunks = get_pending_concept_chunks(limit=200)

        for chunk_data in pending_chunks:
            # Check if we're running out of time
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME_SECONDS:
                structured_logger.info(
                    "timer",
                    "Approaching timeout - stopping concept phase",
                    elapsed_seconds=elapsed,
                    concepts_processed=concepts_processed,
                )
                break

            try:
                # Extract concepts from chunk
                extraction = extract_concepts_from_chunk(chunk_data["text"])

                # Create a Chunk object for store_chunk_extraction
                chunk = Chunk(
                    text=chunk_data["text"],
                    position=0,  # Not needed for extraction
                )
                chunk.id = chunk_data["id"]

                # Store extraction results (concepts, mentions, relationships)
                store_chunk_extraction_standalone(
                    source_id=chunk_data["source_id"],
                    chunk=chunk,
                    extraction=extraction,
                )

                # Mark chunk as extracted
                update_chunk_concept_status(chunk_data["id"], "EXTRACTED")

                concepts_processed += 1
                processed_source_ids.add(chunk_data["source_id"])

                if concepts_processed % 50 == 0:
                    structured_logger.info(
                        "timer",
                        f"Extracted concepts from {concepts_processed} chunks",
                        concepts_processed=concepts_processed,
                    )

            except Exception as e:
                # Mark as failed
                update_chunk_concept_status(
                    chunk_data["id"],
                    "FAILED",
                    str(e)[:500],
                )
                structured_logger.warning(
                    "timer",
                    f"Concept extraction failed for chunk {chunk_data['id']}",
                    error=str(e),
                )

        structured_logger.info(
            "timer",
            "Concept extraction phase complete",
            concepts_processed=concepts_processed,
        )

    # === PHASE 3: UPDATE SOURCE STATUS ===
    # Check if any processed sources are now complete
    sources_completed = 0
    for source_id in processed_source_ids:
        if check_source_complete(source_id):
            update_source_status(source_id, "COMPLETE")
            sources_completed += 1
            structured_logger.info(
                "timer",
                "Source processing complete",
                source_id=source_id,
            )

    # === FINAL SUMMARY ===
    elapsed = time.time() - start_time
    structured_logger.info(
        "timer",
        "Timer function complete",
        elapsed_seconds=round(elapsed, 2),
        embeddings_processed=embeddings_processed,
        concepts_processed=concepts_processed,
        sources_completed=sources_completed,
    )
