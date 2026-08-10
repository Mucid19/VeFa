#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABOUTME: OCR motoru — EasyOCR kullanarak taranmış PDF'lerden metin çıkarır
ABOUTME: Gemini ile kitap adı, yazar, cilt no tespiti yapar
ABOUTME: Türkçe ve Arapça için optimize edilmiştir
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple, Callable

logger = logging.getLogger(__name__)


# EasyOCR kısıtlaması: Arapça yalnızca şu dillerle uyumludur:
_AR_COMPATIBLE = {"ar", "fa", "ur", "ug", "en"}
# Latin-script diller (tr, en, de, vb.) kendi aralarında uyumlu
_LATIN_LANGS    = {"tr", "en", "de", "fr", "es", "it", "pt"}

# Singleton cache: dil kombinasyonu → reader
_readers: dict = {}

def _get_reader(languages: List[str] = None):
    """
    EasyOCR reader'ı yükle.
    Arapça + Türkçe gibi uyumsuz kombinasyonlar için ayrı reader oluşturur.
    Cache: aynı dil seti için reader tekrar yüklenmez.
    """
    langs = sorted(set(languages or ["ar", "en"]))
    key   = tuple(langs)
    if key not in _readers:
        import easyocr
        logger.info(f"EasyOCR reader yükleniyor: {langs}")
        _readers[key] = easyocr.Reader(langs, gpu=False, verbose=False)
    return _readers[key]


def _split_languages(languages: List[str]):
    """
    Dil listesini EasyOCR uyumlu gruplara böl.
    Arapça grubu: ar + (fa, ur, ug, en kesişimi)
    Latin grubu : geri kalanlar + en
    Döner: list of lang_list (her biri ayrı reader için)
    """
    langs = set(languages or ["ar", "en"])
    ar_group    = langs & _AR_COMPATIBLE
    latin_group = (langs - _AR_COMPATIBLE) | {"en"}  # en her zaman ekle

    groups = []
    if ar_group:
        groups.append(sorted(ar_group))
    if latin_group - {"en"} or (not ar_group):  # sadece en varsa ayrı reader açma
        latin_only = sorted(latin_group)
        if latin_only not in groups:
            groups.append(latin_only)
    # Tekrarlıyı çıkar
    seen = []
    for g in groups:
        if g not in seen:
            seen.append(g)
    return seen


# ---------------------------------------------------------------------------
# PDF → görüntü → OCR metin
# ---------------------------------------------------------------------------

def ocr_pdf(
    pdf_path: Path,
    max_pages: int = 50,
    languages: List[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Taranmış bir PDF'den EasyOCR ile metin çıkarır.
    Arapça + Türkçe gibi uyumsuz kombinasyonlarda otomatik ayrı pass yapar.
    """
    import fitz  # PyMuPDF

    pdf_path    = Path(pdf_path)
    lang_groups = _split_languages(languages or ["ar", "en"])
    logger.info(f"OCR dil grupları: {lang_groups}")

    doc         = fitz.open(str(pdf_path))
    total_pages = min(len(doc), max_pages)
    pages_text  = []

    for page_num in range(total_pages):
        try:
            page = doc[page_num]
            mat  = fitz.Matrix(200 / 72, 200 / 72)
            pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
            img_bytes = pix.tobytes("png")

            import numpy as np
            import cv2
            nparr  = np.frombuffer(img_bytes, np.uint8)
            img_np = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            img_np = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

            # Her dil grubu için ayrı pass, sonuçları birleştir
            combined_lines = []
            for lang_group in lang_groups:
                reader  = _get_reader(lang_group)
                results = reader.readtext(img_np, detail=0, paragraph=True)
                combined_lines.extend(str(r) for r in results)

            pages_text.append("\n".join(combined_lines))

            if progress_cb:
                progress_cb(page_num + 1, total_pages)

        except Exception as e:
            logger.warning(f"Sayfa {page_num+1} OCR hatası: {e}")
            pages_text.append("")

    doc.close()
    return "\n\n".join(pages_text)


def ocr_pdf_cover(
    pdf_path: Path,
    cover_pages: int = 3,
    languages: List[str] = None,
) -> str:
    """
    Yalnızca ilk birkaç sayfayı (kapak) OCR ile okur — metadata tespiti için.
    Çok daha hızlıdır.
    """
    return ocr_pdf(pdf_path, max_pages=cover_pages, languages=languages)


# ---------------------------------------------------------------------------
# Gemini ile kitap metadata tespiti
# ---------------------------------------------------------------------------

def detect_book_metadata(
    cover_text: str,
    filename: str,
    llm_func: Optional[Callable] = None,
) -> dict:
    """
    OCR ile elde edilen kapak metninden kitap bilgilerini çıkarır.

    Returns:
        {
            "title": str,       # Kitap/dergi adı
            "author": str,      # Yazar/müellif
            "volume": int|None, # Cilt numarası
            "edition": str,     # Baskı bilgisi
            "confidence": float # 0.0 - 1.0
        }
    """
    if not cover_text or not cover_text.strip():
        return _fallback_metadata(filename)

    prompt = f"""Aşağıdaki metin bir kitabın kapak sayfasından OCR ile çıkarılmıştır.
Dosya adı: {filename}

OCR METNİ:
{cover_text[:3000]}

Lütfen aşağıdaki bilgileri JSON formatında çıkar. 
ÇOK ÖNEMLİ: Eğer kitap adı veya yazar adı Arapça ise, KESİNLİKLE Türkçe okunuşuyla (çevirisiyle veya transliterasyonuyla) yazmalısın. Örnek: "المبسوط" -> "El-Mebsut", "السرخسي" -> "es-Serahsi". Çıktıda Arapça harf BULUNMAMALIDIR!

- title: Kitabın tam adı (Sadece Türkçe harflerle)
- author: Yazar/Müellif adı (Sadece Türkçe harflerle)
- volume: Cilt numarası (sadece sayı olarak, yoksa null)
- edition: Baskı bilgisi (yoksa null)
- confidence: Tespit güvenilirliği 0.0-1.0 arası

Sadece JSON döndür, başka açıklama ekleme:
{{"title": "...", "author": "...", "volume": null, "edition": null, "confidence": 0.9}}"""

    # LLM fonksiyonu varsa kullan
    if llm_func:
        try:
            import json, re
            raw = llm_func(prompt)
            # JSON bloğu çıkar
            json_match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                # Alanları temizle
                data["title"]  = _clean_str(data.get("title", ""))
                data["author"] = _clean_str(data.get("author", ""))
                data["volume"] = _parse_volume(data.get("volume"))
                data["confidence"] = float(data.get("confidence", 0.5))
                if data["title"]:
                    return data
        except Exception as e:
            logger.warning(f"LLM metadata tespiti başarısız: {e}")

    # LLM yoksa kural tabanlı çıkar
    return _rule_based_metadata(cover_text, filename)


def _clean_str(s) -> str:
    if not s or not isinstance(s, str):
        return ""
    return s.strip().strip('"').strip("'")


def _parse_volume(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        import re
        m = re.search(r'\d+', str(v))
        return int(m.group()) if m else None


def _rule_based_metadata(text: str, filename: str) -> dict:
    """Regex ile temel bilgileri çıkar."""
    import re

    # Cilt tespiti: "Cilt 3", "ج3", "v.3", "Vol. 3", "الجزء الثالث" gibi
    volume = None
    cilt_patterns = [
        r'[Cc]ilt\s*:?\s*(\d+)',
        r'[Vv]ol\.?\s*(\d+)',
        r'[Cc]\\.',
        r'ج\s*(\d+)',
        r'الجزء\s+(\w+)',
    ]
    for pat in cilt_patterns:
        m = re.search(pat, text)
        if m:
            try:
                volume = int(m.group(1))
            except (ValueError, IndexError):
                pass
            break

    # Dosya adından volume çekmeye çalış
    if volume is None:
        m = re.search(r'[-_\s](\d+)(?:\.pdf)?$', filename, re.IGNORECASE)
        if m:
            volume = int(m.group(1))

    # Basit başlık: metnin ilk anlamlı satırı
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 5]
    title = lines[0] if lines else Path(filename).stem

    return {
        "title": title[:80],
        "author": "",
        "volume": volume,
        "edition": None,
        "confidence": 0.3,
    }


def _fallback_metadata(filename: str) -> dict:
    """OCR metni yoksa dosya adından metadata çıkar."""
    import re
    stem = Path(filename).stem
    # Parantez, tire, alt çizgi temizle
    title = re.sub(r'[\(\)\[\]_-]+', ' ', stem).strip()
    title = re.sub(r'\s+', ' ', title)

    # Cilt tespiti
    volume = None
    m = re.search(r'(?:v|cilt|vol|c)\.?\s*(\d+)', title, re.IGNORECASE)
    if not m:
        m = re.search(r'[-\s](\d+)$', title)
    if m:
        try:
            volume = int(m.group(1))
        except (ValueError, IndexError):
            pass

    return {
        "title": title[:80],
        "author": "",
        "volume": volume,
        "edition": None,
        "confidence": 0.1,
    }
