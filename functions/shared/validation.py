"""Document validation utilities.

Enforces cost controls and input contracts from System Behavior spec.
"""

from dataclasses import dataclass
from enum import Enum


class ValidationError(Exception):
    """Raised when document validation fails."""

    pass


class ProcessingStatus(Enum):
    """Document processing states for lifecycle tracking."""

    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    EXTRACTING = "EXTRACTING"
    COMPLETE = "COMPLETE"
    PARSE_FAILED = "PARSE_FAILED"
    EXTRACT_FAILED = "EXTRACT_FAILED"


# Cost control limits (from CLAUDE.md System Behavior)
MAX_FILE_SIZE_BYTES = 250 * 1024 * 1024  # 250 MB - increased for large textbooks
MAX_PAGES = 1000
MAX_CHUNKS_PER_SOURCE = 500
MAX_CHUNK_SIZE = 4000  # chars
MIN_TEXT_LENGTH = 100  # Minimum chars to consider document valid


# PDF magic bytes (PDF files start with %PDF-)
PDF_MAGIC_BYTES = b"%PDF-"


@dataclass
class ValidationResult:
    """Result of document validation."""

    is_valid: bool
    error_message: str | None = None


def validate_file_size(size_bytes: int) -> ValidationResult:
    """Validate file size is within limits.

    Args:
        size_bytes: File size in bytes

    Returns:
        ValidationResult with status and error message if invalid
    """
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return ValidationResult(
            is_valid=False,
            error_message=f"File size {size_bytes:,} bytes exceeds limit of {MAX_FILE_SIZE_BYTES:,} bytes",
        )
    return ValidationResult(is_valid=True)


def validate_pdf_magic_bytes(content: bytes) -> ValidationResult:
    """Validate file is actually a PDF by checking magic bytes.

    Args:
        content: First bytes of the file

    Returns:
        ValidationResult with status and error message if invalid
    """
    if not content.startswith(PDF_MAGIC_BYTES):
        return ValidationResult(
            is_valid=False,
            error_message="File does not have valid PDF magic bytes (not a real PDF)",
        )
    return ValidationResult(is_valid=True)


def validate_page_count(page_count: int) -> ValidationResult:
    """Validate page count is within limits.

    Args:
        page_count: Number of pages in document

    Returns:
        ValidationResult with status and error message if invalid
    """
    if page_count > MAX_PAGES:
        return ValidationResult(
            is_valid=False,
            error_message=f"Page count {page_count} exceeds limit of {MAX_PAGES}",
        )
    return ValidationResult(is_valid=True)


def validate_chunk_count(chunk_count: int) -> ValidationResult:
    """Validate chunk count is within limits.

    Args:
        chunk_count: Number of chunks created

    Returns:
        ValidationResult with status and error message if invalid
    """
    if chunk_count > MAX_CHUNKS_PER_SOURCE:
        return ValidationResult(
            is_valid=False,
            error_message=f"Chunk count {chunk_count} exceeds limit of {MAX_CHUNKS_PER_SOURCE}",
        )
    return ValidationResult(is_valid=True)


def validate_minimum_text(text: str) -> ValidationResult:
    """Validate document has sufficient text content.

    Catches scanned PDFs or documents with no extractable text.

    Args:
        text: Full extracted text from document

    Returns:
        ValidationResult with status and error message if invalid
    """
    # Count actual text characters (not whitespace)
    text_length = len(text.strip())

    if text_length < MIN_TEXT_LENGTH:
        return ValidationResult(
            is_valid=False,
            error_message=f"Extracted text ({text_length} chars) below minimum ({MIN_TEXT_LENGTH} chars). "
            "Document may be scanned/image-based or corrupted.",
        )
    return ValidationResult(is_valid=True)


def validate_chunk_positions(chunks: list) -> ValidationResult:
    """Validate chunk positions are sequential starting from 0.

    Args:
        chunks: List of Chunk objects

    Returns:
        ValidationResult with status and error message if invalid
    """
    positions = [c.position for c in chunks]
    expected = list(range(len(chunks)))

    if positions != expected:
        return ValidationResult(
            is_valid=False,
            error_message=f"Chunk positions not sequential: got {positions}, expected {expected}",
        )
    return ValidationResult(is_valid=True)
