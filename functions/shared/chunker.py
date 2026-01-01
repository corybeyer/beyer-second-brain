"""Text chunking utilities.

Splits document content into manageable chunks for processing.
"""

from dataclasses import dataclass

from .parser import ParsedDocument


@dataclass
class Chunk:
    """A chunk of text from a document."""

    text: str
    position: int  # Chunk index within document
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None  # Heading or section name if available
    embedding: list[float] | None = None  # OpenAI embedding (1536 dims)
    id: int | None = None  # Database ID (set after storage)


def chunk_document(
    doc: ParsedDocument,
    max_chunk_size: int = 2000,
    overlap: int = 200,
) -> list[Chunk]:
    """Chunk a parsed document intelligently.

    Uses page boundaries when possible, falls back to size-based
    chunking for large pages.

    Args:
        doc: ParsedDocument from parser
        max_chunk_size: Maximum characters per chunk
        overlap: Characters to overlap between chunks

    Returns:
        List of Chunk objects
    """
    chunks = []
    position = 0

    for page in doc.pages:
        if not page.text.strip():
            continue

        # If page fits in one chunk, use it as-is
        if len(page.text) <= max_chunk_size:
            section = page.headings[0] if page.headings else None
            chunks.append(Chunk(
                text=page.text,
                position=position,
                page_start=page.page_num,
                page_end=page.page_num,
                section=section,
            ))
            position += 1
        else:
            # Split large pages into smaller chunks
            page_chunks = chunk_by_size(
                page.text,
                chunk_size=max_chunk_size,
                overlap=overlap,
            )
            for chunk_text in page_chunks:
                chunks.append(Chunk(
                    text=chunk_text,
                    position=position,
                    page_start=page.page_num,
                    page_end=page.page_num,
                    section=page.headings[0] if page.headings else None,
                ))
                position += 1

    return chunks


def chunk_by_size(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> list[str]:
    """Split text into fixed-size chunks with overlap.

    Tries to break at sentence boundaries when possible.

    Args:
        text: Full text to chunk
        chunk_size: Target characters per chunk
        overlap: Characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # Last chunk
            chunks.append(text[start:].strip())
            break

        # Try to find a good break point (sentence end)
        break_point = _find_break_point(text, start, end)
        chunks.append(text[start:break_point].strip())

        # Move start back by overlap amount
        start = break_point - overlap
        if start < 0:
            start = 0

    return chunks


def _find_break_point(text: str, start: int, end: int) -> int:
    """Find a good break point near the end position.

    Prefers sentence endings (. ! ?) then paragraph breaks.

    Args:
        text: Full text
        start: Start of current chunk
        end: Ideal end position

    Returns:
        Best break point position
    """
    # Look for sentence endings in the last 20% of the chunk
    search_start = start + int((end - start) * 0.8)
    search_text = text[search_start:end]

    # Try sentence endings
    for char in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
        idx = search_text.rfind(char)
        if idx != -1:
            return search_start + idx + len(char)

    # Try paragraph break
    idx = search_text.rfind("\n\n")
    if idx != -1:
        return search_start + idx + 2

    # Try any newline
    idx = search_text.rfind("\n")
    if idx != -1:
        return search_start + idx + 1

    # Fall back to word boundary
    idx = search_text.rfind(" ")
    if idx != -1:
        return search_start + idx + 1

    # No good break point, just use end
    return end
