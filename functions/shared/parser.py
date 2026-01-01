"""Document parsing utilities.

Handles PDF and Markdown file parsing.
"""

from pathlib import Path


def parse_pdf(content: bytes) -> str:
    """Extract text from PDF content.

    Args:
        content: Raw PDF bytes

    Returns:
        Extracted text content
    """
    # TODO: Implement PDF parsing with PyMuPDF
    raise NotImplementedError("PDF parsing not yet implemented")


def parse_markdown(content: bytes) -> str:
    """Parse Markdown content.

    Args:
        content: Raw Markdown bytes

    Returns:
        Markdown text content
    """
    return content.decode("utf-8")


def detect_file_type(filename: str) -> str:
    """Detect document type from filename.

    Args:
        filename: Name of the file

    Returns:
        File type: 'pdf', 'markdown', or 'unknown'
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    elif suffix in (".md", ".markdown"):
        return "markdown"
    else:
        return "unknown"
