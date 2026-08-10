# -*- coding: utf-8 -*-
"""
VeFa - Derin Akademik Arama Modülü
arXiv, OpenAlex ve CrossRef API'leri üzerinden açık erişim kaynakları bulur,
PDF/metin içeriklerini indirir ve tez pipeline'ına besler.

İNDİRİLEBİLEN KAYNAKLAR:
  arXiv     → Fizik, mat, CS, ekonomi ağırlıklı — tam PDF açık erişim
  OpenAlex  → 250M+ makale meta verisi; open-access olanlar için PDF URL verir
  PubMed    → Tıp/biyoloji; PubMed Central açık erişim makaleleri

İNDİRİLEMEYENLER (etik/teknik sebep):
  Elsevier, Springer, Wiley  → Ücretli; lisans gerekiyor
  DİA, İSAM                  → Kapalı sistem
  Google Scholar              → Resmi API yok
"""

import re
import time
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Ortak HTTP başlığı —礼儀 olarak mail adresi bildiriyoruz
_HEADERS = {
    "User-Agent": "VeFa-AcademicAssistant/2.0 (mailto:academic@vefa.app)"
}
_TIMEOUT = 10  # saniye


# ============================================================
# arXiv Arama
# ============================================================

def search_arxiv(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """
    arXiv Atom API üzerinden makale arar.
    Döndürdüğü her sonuç: title, authors, year, abstract, pdf_url, source
    """
    import xml.etree.ElementTree as ET

    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    results = []
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return results
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(r.text)
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("atom:summary", "", ns) or "").strip()[:300]
            authors = [
                a.findtext("atom:name", "", ns)
                for a in entry.findall("atom:author", ns)
            ]
            published = entry.findtext("atom:published", "", ns)
            year = int(published[:4]) if published else None
            # PDF link
            pdf_url = ""
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href", "")
            arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1]
            if title:
                results.append({
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "abstract": summary,
                    "pdf_url": pdf_url,
                    "doi": f"arXiv:{arxiv_id}",
                    "source": "arXiv",
                })
    except Exception as e:
        logger.warning(f"arXiv arama hatası: {e}")
    return results


# ============================================================
# OpenAlex Arama
# ============================================================

def search_openalex(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """
    OpenAlex API'si (250M+ makale) üzerinden arama yapar.
    Açık erişim makaleler için doğrudan PDF URL döndürür.
    """
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
        "sort": "relevance_score:desc",
        "select": "title,authorships,publication_year,primary_location,open_access,doi,abstract_inverted_index",
        "mailto": "academic@vefa.app",
    }
    results = []
    try:
        r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return results
        data = r.json()
        for item in data.get("results", []):
            title = item.get("title") or ""
            if not title:
                continue
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in item.get("authorships", [])
                if a.get("author")
            ]
            year = item.get("publication_year")
            doi = (item.get("doi") or "").replace("https://doi.org/", "")
            # Açık erişim PDF URL
            oa = item.get("open_access", {})
            pdf_url = oa.get("oa_url") or ""
            # Özet (inverted index → düz metin)
            inv = item.get("abstract_inverted_index") or {}
            abstract = _reconstruct_abstract(inv)[:300]
            results.append({
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "pdf_url": pdf_url,
                "doi": doi,
                "source": "OpenAlex",
            })
    except Exception as e:
        logger.warning(f"OpenAlex arama hatası: {e}")
    return results


def _reconstruct_abstract(inv_index: dict) -> str:
    """OpenAlex ters-dizin sözlüğünden düz metin özet oluşturur."""
    if not inv_index:
        return ""
    try:
        max_pos = max(pos for positions in inv_index.values() for pos in positions)
        words = [""] * (max_pos + 1)
        for word, positions in inv_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(w for w in words if w)
    except Exception:
        return ""


# ============================================================
# PDF İndirme
# ============================================================

def download_pdf(pdf_url: str, dest_path: Path, timeout: int = 20) -> bool:
    """
    Açık erişim PDF'ini indirir. Başarılı olursa True döner.
    Sadece gerçek PDF içeriği kabul edilir (min 10 KB).
    """
    if not pdf_url or not pdf_url.startswith("http"):
        return False
    try:
        r = requests.get(pdf_url, headers=_HEADERS, timeout=timeout, stream=True)
        if r.status_code != 200:
            return False
        content_type = r.headers.get("Content-Type", "")
        if "pdf" not in content_type and "octet-stream" not in content_type:
            # arXiv zaman zaman HTML redirect döner
            if "html" in content_type:
                return False
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > 5 * 1024 * 1024:  # 5 MB üst sınır
                break
        if len(content) < 10 * 1024:  # 10 KB'dan küçükse geçersiz
            return False
        dest_path.write_bytes(content)
        return True
    except Exception as e:
        logger.warning(f"PDF indirme hatası ({pdf_url}): {e}")
        return False


# ============================================================
# PDF → Metin Çıkarma
# ============================================================

def extract_text_from_pdf(pdf_path: Path, max_chars: int = 8000) -> str:
    """
    İndirilen PDF'den metin çıkarır (pypdf kullanır).
    pypdf yüklü değilse ham byte üzerinde basit metin arar.
    """
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                pass
        text = " ".join(parts)
        return text[:max_chars]
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"pypdf okuma hatası: {e}")

    # Fallback: binary içinden ASCII metin ara
    try:
        raw = pdf_path.read_bytes()
        text = raw.decode("latin-1", errors="ignore")
        printable = re.sub(r"[^\x20-\x7E\n]", " ", text)
        printable = re.sub(r" {3,}", " ", printable)
        return printable[:max_chars]
    except Exception:
        return ""


# ============================================================
# Ana Derin Arama Fonksiyonu
# ============================================================

def deep_academic_search(
    topic: str,
    language: str = "tr",
    max_results: int = 10,
    download_pdfs: bool = True,
    pdf_dir: Optional[Path] = None,
    report_callback=None,  # (msg: str) → None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Konuya göre arXiv + OpenAlex'te derin arama yapar.
    Açık erişim PDF'leri indirir ve metinlerini çıkarır.

    Döner:
        (sonuç_listesi, zengin_bağlam_metni)

    sonuç_listesi elemanları:
        title, authors, year, abstract, pdf_url, doi, source,
        pdf_path (indirildiyse), full_text (çıkarıldıysa)

    zengin_bağlam_metni:
        LLM'e doğrudan beslenecek özet + tam metin karışımı
    """
    def _report(msg: str):
        logger.info(msg)
        if report_callback:
            try:
                report_callback(msg)
            except Exception:
                pass

    # İngilizce arama terimi daha geniş sonuç verir
    search_query = topic

    _report(f"🔍 Derin arama başlatılıyor: '{topic[:60]}'")

    # --- Paralel arama (sırayla, timeout korumalı) ---
    arxiv_results = []
    openalex_results = []

    try:
        _report("  📡 arXiv sorgulanıyor...")
        arxiv_results = search_arxiv(search_query, max_results=max_results // 2 + 2)
        _report(f"  ✅ arXiv: {len(arxiv_results)} sonuç")
    except Exception as e:
        logger.warning(f"arXiv sorgusu başarısız: {e}")

    time.sleep(0.5)  # API礼儀

    try:
        _report("  📡 OpenAlex sorgulanıyor (250M+ makale)...")
        openalex_results = search_openalex(search_query, max_results=max_results // 2 + 2)
        _report(f"  ✅ OpenAlex: {len(openalex_results)} sonuç")
    except Exception as e:
        logger.warning(f"OpenAlex sorgusu başarısız: {e}")

    # Birleştir ve tekrarı kaldır
    all_results = _deduplicate(arxiv_results + openalex_results, max_results)
    _report(f"  📚 Toplam benzersiz sonuç: {len(all_results)}")

    # --- PDF indirme ---
    if download_pdfs and pdf_dir:
        pdf_dir = Path(pdf_dir)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        for idx, item in enumerate(all_results):
            if not item.get("pdf_url"):
                continue
            if downloaded >= 5:  # En fazla 5 PDF indir
                break
            safe_name = re.sub(r"[^\w\-]", "_", item["title"][:40]) + f"_{idx}.pdf"
            dest = pdf_dir / safe_name
            _report(f"  ⬇️  PDF indiriliyor: {item['title'][:50]}...")
            ok = download_pdf(item["pdf_url"], dest)
            if ok:
                item["pdf_path"] = str(dest)
                text = extract_text_from_pdf(dest, max_chars=6000)
                item["full_text"] = text
                downloaded += 1
                _report(f"  ✅ İndirildi ({dest.stat().st_size // 1024} KB, {len(text)} karakter metin)")
            else:
                _report(f"  ⚠️  İndirilemedi (kısıtlı erişim veya ağ hatası)")
            time.sleep(0.3)

    # --- Zengin bağlam metni oluştur ---
    context = _build_context(all_results, topic, language)
    return all_results, context


def _deduplicate(results: List[Dict], max_n: int) -> List[Dict]:
    """Başlığa göre tekrarları kaldır, max_n kadar döndür."""
    seen = set()
    out = []
    for item in results:
        key = re.sub(r"\s+", " ", (item.get("title") or "").lower().strip())[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(item)
            if len(out) >= max_n:
                break
    return out


def _build_context(results: List[Dict], topic: str, language: str) -> str:
    """LLM'e beslenecek bağlam metnini oluşturur."""
    if not results:
        return ""

    lang_header = {
        "tr": "### DERİN AKADEMİK ARAMA SONUÇLARI (arXiv + OpenAlex):\n",
        "ar": "### نتائج البحث الأكاديمي العميق (arXiv + OpenAlex):\n",
        "en": "### DEEP ACADEMIC SEARCH RESULTS (arXiv + OpenAlex):\n",
    }.get(language, "### DEEP ACADEMIC SEARCH RESULTS:\n")

    lines = [lang_header]
    for idx, item in enumerate(results, 1):
        authors = item.get("authors", [])
        authors_str = ", ".join(str(a) for a in authors[:3])
        if len(authors) > 3:
            authors_str += " et al."
        year = item.get("year", "")
        doi = item.get("doi", "")
        src = item.get("source", "")

        line = f"{idx}. **{item['title']}** ({year}). {authors_str}{'' if authors_str.endswith('.') else '.'} [{src}]"
        if doi:
            line += f" — {doi}"
        lines.append(line)

        abstract = item.get("abstract", "")
        if abstract:
            lines.append(f"   *Özet:* {abstract[:200]}")

        full_text = item.get("full_text", "")
        if full_text and len(full_text) > 200:
            lines.append(f"   *Tam metin (ilk 400 karakter):* {full_text[:400]}...")

        lines.append("")

    return "\n".join(lines)


# ============================================================
# Sadece bağlam metni döndüren kısa yardımcı (akademik_engine için)
# ============================================================

def fetch_deep_search_context(
    topic: str,
    language: str = "tr",
    max_results: int = 8,
    download_pdfs: bool = True,
    pdf_dir: Optional[Path] = None,
    report_callback=None,
) -> str:
    """
    deep_academic_search'i çağırır, sadece zengin bağlam metnini döndürür.
    """
    try:
        _, context = deep_academic_search(
            topic=topic,
            language=language,
            max_results=max_results,
            download_pdfs=download_pdfs,
            pdf_dir=pdf_dir,
            report_callback=report_callback,
        )
        return context
    except Exception as e:
        logger.warning(f"Derin arama başarısız: {e}")
        return ""
