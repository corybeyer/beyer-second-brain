"""Text chunking utilities.

Splits document content into manageable chunks for processing.
"""


def chunk_by_heading(text: str, max_chunk_size: int = 2000) -> list[dict]:
    """Split text by headings (Markdown or detected sections).

    Args:
        text: Full document text
        max_chunk_size: Maximum characters per chunk

    Returns:
        List of chunk dictionaries with 'section' and 'text' keys
    """
    # TODO: Implement heading-based chunking
    raise NotImplementedError("Heading-based chunking not yet implemented")


def chunk_by_size(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[dict]:
    """Split text into fixed-size chunks with overlap.

    Args:
        text: Full document text
        chunk_size: Target characters per chunk
        overlap: Characters to overlap between chunks

    Returns:
        List of chunk dictionaries with 'position' and 'text' keys
    """
    # TODO: Implement size-based chunking
    raise NotImplementedError("Size-based chunking not yet implemented")
