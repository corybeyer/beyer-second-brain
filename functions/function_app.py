"""Azure Functions app using v2 programming model.

Requires AzureWebJobsFeatureFlags=EnableWorkerIndexing app setting.

Implements System Behavior patterns from CLAUDE.md:
- Validation (size limits, magic bytes, minimum text)
- Processing states
- Structured logging with timing
- Cost controls

Pipeline steps:
1. Parse PDF → 2. Chunk → 3. Embed → 4. Store → 5. Extract Concepts
"""

import os

import azure.functions as func

from shared.chunker import chunk_document
from shared.embeddings import embed_chunks
from shared.graph import process_source_concepts
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

# Feature flags for optional pipeline steps
ENABLE_EMBEDDINGS = os.environ.get("ENABLE_EMBEDDINGS", "true").lower() == "true"
ENABLE_CONCEPTS = os.environ.get("ENABLE_CONCEPTS", "true").lower() == "true"

app = func.FunctionApp()


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
    filename = blob.name or "unknown"
    file_size = blob.length or 0

    # Set logging context for all subsequent logs
    structured_logger.set_context(file_path=filename)
    status = ProcessingStatus.UPLOADED

    try:
        # === VALIDATION PHASE ===
        status = ProcessingStatus.PARSING

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
            return

        # 8. Validate chunk positions are sequential (invariant)
        position_result = validate_chunk_positions(chunks)
        if not position_result.is_valid:
            structured_logger.error(
                "validate",
                position_result.error_message or "Chunk positions invalid",
            )
            status = ProcessingStatus.PARSE_FAILED
            return

        # 9. Validate at least one chunk exists (invariant for COMPLETE status)
        if len(chunks) == 0:
            structured_logger.error(
                "validate",
                "No chunks created from document",
            )
            status = ProcessingStatus.PARSE_FAILED
            return

        status = ProcessingStatus.PARSED

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

        # === EMBEDDING PHASE (optional) ===
        if ENABLE_EMBEDDINGS:
            with structured_logger.timed_operation(
                "embedding", f"Generating embeddings for {len(chunks)} chunks"
            ) as ctx:
                chunks = embed_chunks(chunks)
                ctx["chunks_embedded"] = len(chunks)

            structured_logger.info(
                "embedding",
                "Embeddings generated",
                chunk_count=len(chunks),
            )
        else:
            structured_logger.info(
                "embedding",
                "Embedding generation disabled",
            )

        # === STORAGE PHASE ===
        # Store document and chunks with idempotency (delete-and-replace)
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

        # === CONCEPT EXTRACTION PHASE (optional) ===
        if ENABLE_CONCEPTS:
            with structured_logger.timed_operation(
                "concepts", "Extracting concepts"
            ) as ctx:
                stats = process_source_concepts(source_id, chunks)
                ctx["concepts_extracted"] = stats["concepts_extracted"]
                ctx["relationships_created"] = stats["relationships_created"]

            structured_logger.info(
                "concepts",
                "Concept extraction complete",
                source_id=source_id,
                stats=stats,
            )
        else:
            structured_logger.info(
                "concepts",
                "Concept extraction disabled",
            )
            # Update status to COMPLETE if concepts are disabled
            from shared.storage import update_source_status
            update_source_status(source_id, "COMPLETE")

        status = ProcessingStatus.COMPLETE

        structured_logger.info(
            "complete",
            "Pipeline complete",
            source_id=source_id,
            chunk_count=len(chunks),
            status=status.value,
        )

    except Exception as e:
        status = ProcessingStatus.PARSE_FAILED
        structured_logger.error(
            "error",
            f"Processing failed: {e!s}",
            error_type=type(e).__name__,
            status=status.value,
        )
        # Re-raise to let Azure Functions handle retry
        raise

    finally:
        structured_logger.info(
            "complete",
            f"Processing finished with status: {status.value}",
            final_status=status.value,
        )
        structured_logger.clear_context()
