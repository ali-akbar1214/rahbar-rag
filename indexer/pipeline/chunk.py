"""Stage 3: Chunk. Structure-aware, with overlap."""

from __future__ import annotations

import re

from .models import Chunk, Document

HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+|(?:\d+\.)+\d*\s+|[A-Z0-9\.\s]{3,35}\b(?:Policy|Regulation|Rules|Section|Clause)\b|Clause\s+\d+[\.\d]*).*",
    re.MULTILINE,
)


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` characters/tokens, with `overlap` characters/tokens shared between neighbours.
    Every chunk retains structure-aware section heading context, page number, doc_version,
    and superseded status.
    """
    chunks: list[Chunk] = []
    chunk_counter = 0

    current_section = "General Overview"

    for page_obj in doc.pages:
        page_num = page_obj.page
        text = page_obj.text.strip()
        if not text:
            continue

        # Split page text into structural paragraph blocks
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

        current_buffer = ""

        for para in paragraphs:
            # Check if this paragraph starts with or is a section/clause heading
            first_line = para.splitlines()[0].strip()
            is_heading = (
                bool(HEADING_PATTERN.match(first_line))
                and len(first_line) <= 80
                and (first_line.startswith("#") or not first_line.endswith("."))
            )
            if is_heading:
                # If buffer is non-empty, flush it before changing section
                if current_buffer:
                    chunk_counter += 1
                    cid = f"{doc.source}-p{page_num}-{chunk_counter:04d}"
                    chunks.append(
                        Chunk(
                            id=cid,
                            text=current_buffer.strip(),
                            source=doc.source,
                            section=current_section,
                            page=page_num,
                            doc_version=doc.doc_version,
                            superseded=doc.superseded,
                        )
                    )
                    # Prepare overlap from end of buffer
                    overlap_text = current_buffer[-overlap:] if len(current_buffer) > overlap else ""
                    current_buffer = overlap_text

                current_section = first_line.lstrip("#").strip()

            # Sentence splitting within paragraph
            sentences = re.split(r"(?<=[.!?])\s+", para)

            for sentence in sentences:
                if not sentence.strip():
                    continue

                candidate = (current_buffer + " " + sentence).strip() if current_buffer else sentence.strip()

                if len(candidate) <= size:
                    current_buffer = candidate
                else:
                    if current_buffer:
                        chunk_counter += 1
                        cid = f"{doc.source}-p{page_num}-{chunk_counter:04d}"
                        chunks.append(
                            Chunk(
                                id=cid,
                                text=current_buffer.strip(),
                                source=doc.source,
                                section=current_section,
                                page=page_num,
                                doc_version=doc.doc_version,
                                superseded=doc.superseded,
                            )
                        )
                        # Carry over overlap
                        overlap_tail = current_buffer[-overlap:] if len(current_buffer) > overlap else ""
                        current_buffer = (overlap_tail + " " + sentence).strip()
                    else:
                        # Single sentence exceeds chunk size; hard split with overlap
                        start = 0
                        while start < len(sentence):
                            end = start + size
                            part = sentence[start:end]
                            chunk_counter += 1
                            cid = f"{doc.source}-p{page_num}-{chunk_counter:04d}"
                            chunks.append(
                                Chunk(
                                    id=cid,
                                    text=part.strip(),
                                    source=doc.source,
                                    section=current_section,
                                    page=page_num,
                                    doc_version=doc.doc_version,
                                    superseded=doc.superseded,
                                )
                            )
                            start = end - overlap if (end - overlap) > start else end

        if current_buffer:
            chunk_counter += 1
            cid = f"{doc.source}-p{page_num}-{chunk_counter:04d}"
            chunks.append(
                Chunk(
                    id=cid,
                    text=current_buffer.strip(),
                    source=doc.source,
                    section=current_section,
                    page=page_num,
                    doc_version=doc.doc_version,
                    superseded=doc.superseded,
                )
            )

    return chunks
