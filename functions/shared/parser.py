"""Document parsing utilities.

Handles PDF file parsing using PyMuPDF.
"""

from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF


@dataclass
class PageContent:
    """Content from a single PDF page."""

    page_num: int
    text: str
    headings: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Parsed document with structure information."""

    filename: str
    title: str | None
    author: str | None
    page_count: int
    pages: list[PageContent]
    metadata: dict

    @property
    def full_text(self) -> str:
        """Get all text concatenated."""
        return "\n\n".join(page.text for page in self.pages)


def parse_pdf(content: bytes, filename: str = "document.pdf") -> ParsedDocument:
    """Extract text and structure from PDF content.

    Args:
        content: Raw PDF bytes
        filename: Original filename for reference

    Returns:
        ParsedDocument with text, structure, and metadata
    """
    doc = fitz.open(stream=content, filetype="pdf")

    # Extract metadata
    metadata = doc.metadata or {}
    title = metadata.get("title") or None
    author = metadata.get("author") or None

    # Extract text from each page
    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")

        # Try to identify headings (larger font sizes, bold text)
        headings = _extract_headings(page)

        pages.append(PageContent(
            page_num=page_num,
            text=text.strip(),
            headings=headings,
        ))

    doc.close()

    return ParsedDocument(
        filename=filename,
        title=title,
        author=author,
        page_count=len(pages),
        pages=pages,
        metadata=metadata,
    )


def _extract_headings(page: fitz.Page) -> list[str]:
    """Extract potential headings from a page based on font size.

    Args:
        page: PyMuPDF page object

    Returns:
        List of text that appears to be headings
    """
    headings = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    for block in blocks:
        if block.get("type") != 0:  # Skip non-text blocks
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font_size = span.get("size", 12)
                text = span.get("text", "").strip()
                flags = span.get("flags", 0)

                # Heuristic: larger fonts or bold text might be headings
                is_bold = flags & 2 ** 4  # Bold flag
                is_large = font_size >= 14

                if text and (is_bold or is_large) and len(text) < 200:
                    headings.append(text)

    return headings


def detect_file_type(filename: str) -> str:
    """Detect document type from filename.

    Args:
        filename: Name of the file

    Returns:
        File type: 'pdf' or 'unknown'
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    else:
        return "unknown"
