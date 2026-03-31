import json
import re
from pathlib import Path

import docx
import pdfplumber

from planner.utils import chunk_text


class SyllabusExtractionError(RuntimeError):
    pass


def extract_pdf_text(path):
    text_parts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
    except Exception as exc:
        raise SyllabusExtractionError(f"Failed to read PDF: {exc}") from exc
    return "\n\n".join(text_parts)


def extract_docx_text(path):
    try:
        document = docx.Document(path)
    except Exception as exc:
        raise SyllabusExtractionError(f"Failed to read DOCX: {exc}") from exc
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def clean_extracted_text(text):
    cleaned = re.sub(r"\r", "\n", text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def split_into_chunks(text, max_chars=4000):
    chunks = chunk_text(text, max_chars=max_chars)
    return [
        {
            "chunk_id": index,
            "text": chunk,
            "page_hint": None,
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def extract_document_text(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = extract_pdf_text(path)
    elif suffix == ".docx":
        text = extract_docx_text(path)
    else:
        raise SyllabusExtractionError("Unsupported syllabus file type.")
    cleaned = clean_extracted_text(text)
    if not cleaned:
        raise SyllabusExtractionError("The uploaded syllabus does not contain extractable text.")
    return cleaned


def write_extracted_cache(source_file, text, chunks, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_file": source_file,
        "text": text,
        "chunks": chunks,
    }
    target_path = output_dir / f"{Path(source_file).stem}.json"
    target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target_path
