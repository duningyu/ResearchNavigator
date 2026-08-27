"""PDF text extraction and structure-aware chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    pages: tuple[ParsedPage, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass(frozen=True, slots=True)
class ParsedChunk:
    section: str
    page_start: int
    page_end: int
    chunk_index: int
    text: str


_SECTION_NAMES = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "related work": "Related Work",
    "method": "Method",
    "methods": "Method",
    "experiments": "Experiments",
    "results": "Results",
    "limitations": "Limitations",
    "conclusion": "Conclusion",
    "future work": "Future Work",
    "appendix": "Appendix",
}


def parse_pdf(data: bytes) -> ParsedDocument:
    reader = PdfReader(BytesIO(data))
    pages: list[ParsedPage] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        pages.append(ParsedPage(page_number=index, text=text))
    return ParsedDocument(pages=tuple(pages))


def _detect_section(text: str, current: str = "Unknown") -> str:
    for line in text.splitlines()[:8]:
        normalized = re.sub(r"^\d+(?:\.\d+)*\s*", "", line.strip().lower()).rstrip(":")
        if normalized in _SECTION_NAMES:
            return _SECTION_NAMES[normalized]
    return current


def chunk_document(
    document: ParsedDocument,
    *,
    max_chars: int = 1_500,
    overlap_chars: int = 160,
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    current_section = "Unknown"
    chunk_index = 0
    for page in document.pages:
        current_section = _detect_section(page.text, current_section)
        text = page.text.strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start + max_chars // 2:
                    end = boundary
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    ParsedChunk(
                        section=current_section,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        chunk_index=chunk_index,
                        text=chunk_text,
                    )
                )
                chunk_index += 1
            if end >= len(text):
                break
            start = max(end - overlap_chars, start + 1)
    return chunks
