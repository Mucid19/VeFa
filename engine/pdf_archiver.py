#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABOUTME: PDF Arşivleyici — OCR ile okunan PDF'leri yeniden adlandırır ve klasörler
ABOUTME: Aynı kitabın ciltlerini tek klasörde toplar
ABOUTME: Dosyalar taşınmaz, arşiv klasörüne kopyalanır (orijinaller korunur)
"""

import logging
import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable

logger = logging.getLogger(__name__)

# Arapça rakamlar → Latin
_ARABIC_NUMS = {
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
}

# Arapça ordinal → sayı (cilt tespiti için)
_AR_ORDINALS = {
    'الأول': 1, 'الثاني': 2, 'الثالث': 3, 'الرابع': 4, 'الخامس': 5,
    'السادس': 6, 'السابع': 7, 'الثامن': 8, 'التاسع': 9, 'العاشر': 10,
    'الحادي عشر': 11, 'الثاني عشر': 12,
}


def _normalize_arabic_digits(s: str) -> str:
    for ar, lat in _ARABIC_NUMS.items():
        s = s.replace(ar, lat)
    return s


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """Dosya adı için güvenli karakter seti."""
    # Windows yasak karakterleri kaldır
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    # Çoklu boşluk temizle
    name = re.sub(r'\s+', ' ', name).strip()
    # Uzunluk sınırla
    return name[:max_len]


def _build_folder_key(title: str) -> str:
    """Aynı kitabın farklı ciltlerini eşleştirmek için normalize edilmiş anahtar."""
    key = title.lower().strip()
    # Cilt/volume ifadelerini çıkar
    key = re.sub(r'\b(cilt|vol|volume|جزء|الجزء)\b.*', '', key, flags=re.IGNORECASE)
    key = re.sub(r'\s*[-–—]\s*\d+\s*$', '', key)
    key = re.sub(r'\s+', ' ', key).strip()
    return key


def _build_archive_filename(metadata: dict) -> str:
    """
    Metadata'dan dosya adı üret:
    - "Kitap Adı - Cilt 3.pdf"
    - "Kitap Adı.pdf" (cilt yoksa)
    """
    title = _sanitize_filename(metadata.get("title", "Bilinmeyen Kitap"))
    author = _sanitize_filename(metadata.get("author", ""))
    volume = metadata.get("volume")

    # Eğer yazar varsa başlığa ekle
    if author and author not in title:
        base = f"{title} - {author}"
    else:
        base = title

    if volume is not None:
        base = f"{base} - Cilt {volume}"

    return base


def _build_folder_name(metadata: dict) -> str:
    """Klasör adı: Kitap Adı (yazar varsa ekle)."""
    title = _sanitize_filename(metadata.get("title", "Bilinmeyen Kitap"))
    author = _sanitize_filename(metadata.get("author", ""))
    if author and author not in title:
        return f"{title} — {author}"
    return title


# ---------------------------------------------------------------------------
# Ana arşivleme fonksiyonu
# ---------------------------------------------------------------------------

def archive_pdfs(
    pdf_paths: List[Path],
    output_dir: Path,
    llm_func: Optional[Callable] = None,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    use_ocr: bool = True,
    ocr_languages: List[str] = None,
) -> Tuple[List[Dict], List[str]]:
    """
    PDF dosyalarını OCR ile okuyup akıllıca yeniden adlandırır ve klasörler.

    Args:
        pdf_paths: İşlenecek PDF dosyaları
        output_dir: Arşiv çıktı klasörü
        llm_func: Opsiyonel LLM fonksiyonu (Gemini metadata tespiti için)
        progress_cb: (mesaj, işlenen, toplam) callback
        use_ocr: True ise EasyOCR çalıştırılır, False ise sadece dosya adından metadata
        ocr_languages: EasyOCR dil kodları

    Returns:
        (results, errors)
        results: [{"original": ..., "new_name": ..., "folder": ..., "metadata": {...}}]
        errors: Hatalı dosyalar listesi
    """
    from engine.ocr_engine import ocr_pdf_cover, detect_book_metadata

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    errors = []
    total = len(pdf_paths)

    # Önce tüm dosyaların metadata'sını topla (gruplama için)
    all_metadata: List[Tuple[Path, dict]] = []

    for idx, pdf_path in enumerate(pdf_paths):
        pdf_path = Path(pdf_path)
        filename = pdf_path.name

        if progress_cb:
            progress_cb(f"📖 OCR: {filename}", idx + 1, total)

        try:
            cover_text = ""
            if use_ocr:
                # Önce normal metin okumayı dene
                try:
                    import fitz
                    doc = fitz.open(str(pdf_path))
                    sample_pages = []
                    for i in range(min(3, len(doc))):
                        t = doc[i].get_text().strip()
                        if t:
                            sample_pages.append(t)
                    doc.close()
                    cover_text = "\n".join(sample_pages)
                except Exception:
                    pass

                # Normal metin yeterli değilse OCR uygula
                if len(cover_text.strip()) < 50:
                    cover_text = ocr_pdf_cover(
                        pdf_path,
                        cover_pages=3,
                        languages=ocr_languages or ["tr", "ar", "en"],
                    )

            metadata = detect_book_metadata(cover_text, filename, llm_func)
            metadata["_source_path"] = pdf_path
            all_metadata.append((pdf_path, metadata))

        except Exception as e:
            logger.error(f"Metadata tespiti başarısız [{filename}]: {e}")
            errors.append(f"'{filename}': {e}")
            # Fallback metadata
            from engine.ocr_engine import _fallback_metadata
            fallback = _fallback_metadata(filename)
            fallback["_source_path"] = pdf_path
            all_metadata.append((pdf_path, fallback))

    # Grup eşleştirmesi: aynı kitabın ciltlerini bir arada say
    folder_counts: Dict[str, int] = {}
    for _, meta in all_metadata:
        key = _build_folder_key(meta.get("title", ""))
        folder_counts[key] = folder_counts.get(key, 0) + 1

    # Dosyaları arşivle
    used_names: Dict[str, int] = {}  # çakışma önleme

    for idx, (pdf_path, metadata) in enumerate(all_metadata):
        filename = pdf_path.name

        if progress_cb:
            progress_cb(f"📁 Düzenleniyor: {filename}", idx + 1, total)

        try:
            folder_key = _build_folder_key(metadata.get("title", ""))
            folder_name = _build_folder_name(metadata)

            # Birden fazla cilt varsa klasör oluştur, tek dosyaysa kök dizine at
            if folder_counts.get(folder_key, 1) > 1 or metadata.get("volume") is not None:
                dest_folder = output_dir / _sanitize_filename(folder_name)
            else:
                dest_folder = output_dir

            dest_folder.mkdir(parents=True, exist_ok=True)

            new_name = _build_archive_filename(metadata)

            # Çakışma önle
            name_key = str(dest_folder / new_name)
            if name_key in used_names:
                used_names[name_key] += 1
                new_name = f"{new_name} ({used_names[name_key]})"
            else:
                used_names[name_key] = 1

            dest_path = dest_folder / f"{new_name}.pdf"

            # Kopyala (orijinal korunur)
            shutil.copy2(str(pdf_path), str(dest_path))

            results.append({
                "original": str(pdf_path),
                "original_name": filename,
                "new_name": f"{new_name}.pdf",
                "folder": str(dest_folder.relative_to(output_dir)) if dest_folder != output_dir else ".",
                "metadata": metadata,
            })

            logger.info(f"✅ {filename} → {dest_folder.name}/{new_name}.pdf")

        except Exception as e:
            logger.error(f"Arşivleme hatası [{filename}]: {e}")
            errors.append(f"'{filename}': {e}")

    return results, errors


# ---------------------------------------------------------------------------
# Sonuç raporu
# ---------------------------------------------------------------------------

def build_archive_report(results: List[Dict], errors: List[str]) -> str:
    """Markdown formatında arşivleme raporu üret."""
    lines = [f"## 📚 Arşivleme Raporu\n"]
    lines.append(f"**Başarılı:** {len(results)} dosya  |  **Hatalı:** {len(errors)} dosya\n")
    lines.append("---\n")

    # Klasörlere göre grupla
    by_folder: Dict[str, List[Dict]] = {}
    for r in results:
        folder = r["folder"]
        by_folder.setdefault(folder, []).append(r)

    for folder, items in sorted(by_folder.items()):
        folder_display = folder if folder != "." else "_(kök dizin)_"
        lines.append(f"### 📁 {folder_display}\n")
        for item in sorted(items, key=lambda x: x["new_name"]):
            conf = item["metadata"].get("confidence", 0)
            conf_icon = "🟢" if conf >= 0.7 else "🟡" if conf >= 0.4 else "🔴"
            lines.append(f"- {conf_icon} `{item['original_name']}` → **{item['new_name']}**")
        lines.append("")

    if errors:
        lines.append("---\n")
        lines.append("### ⚠️ Hatalar\n")
        for e in errors:
            lines.append(f"- {e}")

    return "\n".join(lines)
