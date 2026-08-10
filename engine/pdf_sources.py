#!/usr/bin/env python3
"""
ABOUTME: Builds a "sources_block" string for AcademicEngine from user-uploaded PDF files
ABOUTME: so section generation can be grounded in the user's own documents instead of the
ABOUTME: model's internal knowledge or live web search.
"""

import logging
from pathlib import Path
from typing import List, Tuple, Optional

from engine.utils.document_reader import read_document

logger = logging.getLogger(__name__)


def _try_ocr_fallback(path: Path, max_chars: int) -> str:
    """EasyOCR ile taranmış PDF'den metin çıkar (fallback)."""
    try:
        from engine.ocr_engine import ocr_pdf
        logger.info(f"OCR fallback başlatılıyor: {path.name}")
        text = ocr_pdf(path, max_pages=30)
        if len(text) > max_chars:
            text = text[:max_chars]
        return text.strip()
    except ImportError:
        logger.warning("easyocr kurulu değil — OCR fallback atlandı. Kurmak için: pip install easyocr opencv-python")
        return ""
    except Exception as e:
        logger.warning(f"OCR fallback hatası [{path.name}]: {e}")
        return ""


def build_sources_from_pdfs(
    pdf_paths: List[Path],
    max_chars_per_pdf: Optional[int] = None,
    max_total_chars: int = 180000,
    use_ocr_fallback: bool = True,
) -> Tuple[str, List[str]]:
    """
    Read a list of PDF (or txt/md) files and return a single combined text block
    suitable for injection into AcademicEngine's provided_sources parameter.

    Dynamically calculates per-pdf character budget based on number of files so
    that even if 100+ PDFs are uploaded, EVERY file is sampled and represented.

    If a PDF yields no text (scanned image), automatically retries with EasyOCR
    when use_ocr_fallback=True and easyocr is installed.

    Returns:
        (combined_text, warnings) — warnings lists any files that failed to
        read or had to be truncated.
    """
    blocks = []
    warnings = []
    total_chars = 0
    num_files = max(1, len(pdf_paths))

    # Dynamically allocate budget per PDF so all files are included
    if max_chars_per_pdf is None:
        per_pdf_budget = max(1500, max_total_chars // num_files)
    else:
        per_pdf_budget = max_chars_per_pdf

    for path in pdf_paths:
        path = Path(path)
        name = path.name
        try:
            text = read_document(path, max_chars=per_pdf_budget)
        except Exception as e:
            logger.warning(f"PDF kaynağı okunamadı: {name} — {e}")
            warnings.append(f"'{name}' okunamadı: {e}")
            continue

        text = text.strip()

        # --- OCR FALLBACK ---
        if not text and use_ocr_fallback and path.suffix.lower() == ".pdf":
            logger.info(f"Normal metin boş, OCR deneniyor: {name}")
            text = _try_ocr_fallback(path, per_pdf_budget)
            if text:
                warnings.append(f"'{name}' taranmış görüntü — OCR ile okundu ({len(text):,} karakter).")
            else:
                warnings.append(f"'{name}' içinden metin çıkarılamadı (OCR de başarısız — görüntü kalitesi düşük olabilir).")
                continue
        elif not text:
            warnings.append(f"'{name}' içinden metin çıkarılamadı (taranmış görüntü/OCR gerektiriyor olabilir).")
            continue

        remaining_budget = max_total_chars - total_chars
        if remaining_budget <= 0:
            warnings.append(f"'{name}' toplam kaynak boyutu sınırı nedeniyle atlandı.")
            continue
        if len(text) > remaining_budget:
            text = text[:remaining_budget]
            warnings.append(f"'{name}' toplam kaynak boyutu sınırı nedeniyle kısaltıldı.")

        block = f"--- KAYNAK BELGE METNİ [{name}] ---\n{text}\n--- KAYNAK SONU ---\n"
        blocks.append(block)
        total_chars += len(text)

        if total_chars >= max_total_chars:
            break

    combined = "\n".join(blocks)
    return combined, warnings

