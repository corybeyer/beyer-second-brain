"""Azure Functions app using v2 programming model.

Requires AzureWebJobsFeatureFlags=EnableWorkerIndexing app setting.
"""

import json
import logging
import azure.functions as func

from shared.parser import detect_file_type, parse_pdf
from shared.chunker import chunk_document

app = func.FunctionApp()


@app.blob_trigger(
    arg_name="blob",
    path="documents/{name}",
    connection="AzureWebJobsStorage"
)
def ingest_document(blob: func.InputStream) -> None:
    """Process uploaded document.

    Args:
        blob: Input stream from blob trigger
    """
    filename = blob.name or "unknown"
    logging.info(f"Processing blob: {filename}, Size: {blob.length} bytes")

    # Detect file type
    file_type = detect_file_type(filename)
    if file_type != "pdf":
        logging.warning(f"Unsupported file type: {file_type} for {filename}")
        return

    # Read content
    content = blob.read()
    logging.info(f"Read {len(content)} bytes from {filename}")

    # Parse PDF
    try:
        doc = parse_pdf(content, filename)
        logging.info(f"Parsed PDF: {doc.page_count} pages")
        logging.info(f"Title: {doc.title or 'Unknown'}")
        logging.info(f"Author: {doc.author or 'Unknown'}")

        # Chunk document
        chunks = chunk_document(doc, max_chunk_size=2000, overlap=200)
        logging.info(f"Created {len(chunks)} chunks")

        # Log chunk summary for exploration
        for i, chunk in enumerate(chunks[:3]):  # Log first 3 chunks
            logging.info(f"Chunk {i}: page {chunk.page_start}, "
                        f"section='{chunk.section}', "
                        f"length={len(chunk.text)} chars")

        # Log structure for schema design
        structure = {
            "filename": doc.filename,
            "title": doc.title,
            "author": doc.author,
            "page_count": doc.page_count,
            "chunk_count": len(chunks),
            "metadata": doc.metadata,
        }
        logging.info(f"Document structure: {json.dumps(structure, indent=2)}")

        # TODO: Store in Azure SQL once schema is defined
        logging.info("Database storage pending - schema not yet defined")

    except Exception as e:
        logging.error(f"Failed to parse {filename}: {e}")
        raise

    logging.info(f"Completed processing: {filename}")
