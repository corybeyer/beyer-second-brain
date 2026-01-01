"""Shared utilities for Azure Functions.

Exports:
- Parser: PDF parsing with PyMuPDF
- Chunker: Text chunking with page boundaries
- Validation: Input validation and processing states
- Logging: Structured JSON logging
"""

from .chunker import Chunk, chunk_by_size, chunk_document
from .logging_utils import StructuredLogger, structured_logger
from .parser import PageContent, ParsedDocument, detect_file_type, parse_pdf
from .validation import (
    MAX_CHUNK_SIZE,
    MAX_CHUNKS_PER_SOURCE,
    MAX_FILE_SIZE_BYTES,
    MAX_PAGES,
    MIN_TEXT_LENGTH,
    ProcessingStatus,
    ValidationError,
    ValidationResult,
    validate_chunk_count,
    validate_chunk_positions,
    validate_file_size,
    validate_minimum_text,
    validate_page_count,
    validate_pdf_magic_bytes,
)

__all__ = [
    # Parser
    "PageContent",
    "ParsedDocument",
    "parse_pdf",
    "detect_file_type",
    # Chunker
    "Chunk",
    "chunk_document",
    "chunk_by_size",
    # Validation
    "ProcessingStatus",
    "ValidationError",
    "ValidationResult",
    "validate_file_size",
    "validate_pdf_magic_bytes",
    "validate_page_count",
    "validate_chunk_count",
    "validate_minimum_text",
    "validate_chunk_positions",
    "MAX_FILE_SIZE_BYTES",
    "MAX_PAGES",
    "MAX_CHUNKS_PER_SOURCE",
    "MAX_CHUNK_SIZE",
    "MIN_TEXT_LENGTH",
    # Logging
    "StructuredLogger",
    "structured_logger",
]
