# -*- coding: utf-8 -*-
import os
import requests
import re
import urllib.parse
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def _sanitize_filename(name: str) -> str:
    """Dosya adi temizleme: gecersiz karakter, bos isim ve Windows reserved name kontrolu."""
    import hashlib
    # Gecersiz karakterleri kaldir
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = re.sub(r'\s+', '_', name).strip('_')
    # Windows reserved file names
    _RESERVED = {'CON','PRN','AUX','NUL','COM1','COM2','COM3','COM4',
                 'COM5','COM6','COM7','COM8','COM9','LPT1','LPT2',
                 'LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9'}
    if name.lower().endswith('.pdf'):
        base = name[:-4]
        if not base or base.upper() in _RESERVED:
            base = 'document_' + hashlib.md5(name.encode()).hexdigest()[:8]
        return base[:90] + '.pdf'
    if not name or name.upper() in _RESERVED:
        name = 'document_' + hashlib.md5(name.encode()).hexdigest()[:8]
    return name[:100]

def search_semantic_scholar(query: str, limit: int = 5) -> list:
    import time
    results = []
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query)}&limit={limit}&fields=title,url,year,authors,openAccessPdf"
    headers = {"User-Agent": "VeFa-Academic-Bot/1.0 (mailto:test@example.com)"}
    
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for item in data.get("data", []):
                    oa_pdf = item.get("openAccessPdf")
                    if oa_pdf and oa_pdf.get("url"):
                        pdf_url = oa_pdf.get("url")
                        title = item.get("title", "Bilinmeyen_Makale")
                        year = item.get("year", "")
                        # Extract first author
                        authors = item.get("authors", [])
                        author = authors[0].get("name", "Anonim") if authors else "Anonim"
                        filename = _sanitize_filename(f"{year}_{author}_{title}.pdf")
                        results.append({
                            "title": title,
                            "url": pdf_url,
                            "filename": filename,
                            "source": "Semantic Scholar"
                        })
                break  # Başarılı olursa döngüden çık
            elif r.status_code == 429:
                logger.warning(f"Semantic Scholar API hız sınırına takıldı (429). 3 saniye bekleniyor... ({attempt+1}/3)")
                time.sleep(3)
            else:
                logger.warning(f"Semantic Scholar başarısız: {r.status_code}")
                break
        except Exception as e:
            logger.warning(f"Semantic Scholar bağlantı hatası: {e}")
            break
    return results

def search_openalex(query: str, limit: int = 5) -> list:
    results = []
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": limit,
        "sort": "relevance_score:desc",
        "select": "title,authorships,publication_year,open_access",
        "mailto": "academic@vefa.app",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("results", []):
                oa = item.get("open_access", {})
                pdf_url = oa.get("oa_url")
                if pdf_url:
                    title = item.get("title", "Bilinmeyen_Makale")
                    year = item.get("publication_year", "")
                    authors = item.get("authorships", [])
                    author_name = "Anonim"
                    if authors and authors[0].get("author"):
                        author_name = authors[0]["author"].get("display_name", "Anonim")
                    
                    filename = _sanitize_filename(f"{year}_{author_name}_{title}.pdf")
                    results.append({
                        "title": title,
                        "url": pdf_url,
                        "filename": filename,
                        "source": "OpenAlex"
                    })
    except Exception as e:
        logger.warning(f"OpenAlex aramasi basarisiz: {e}")
    return results

def search_arxiv(query: str, limit: int = 5) -> list:
    results = []
    import xml.etree.ElementTree as ET
    
    # ArXiv'de daha kesin sonuçlar için boşlukları AND ile birleştiriyoruz (ör: all:Iraq+AND+all:Hanafi)
    words = [w for w in query.split() if len(w) > 2]
    if not words: return []
    arxiv_query = "+AND+".join(f"all:{urllib.parse.quote(w)}" for w in words)
    
    url = f"http://export.arxiv.org/api/query?search_query={arxiv_query}&start=0&max_results={limit}"
    try:
        headers = {"User-Agent": "VeFa-Academic-Bot/1.0"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            # ArXiv XML namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns):
                title = entry.find('atom:title', ns).text.strip()
                title = re.sub(r'\s+', ' ', title)
                author_elem = entry.find('atom:author/atom:name', ns)
                author = author_elem.text if author_elem is not None else "Anonim"
                published = entry.find('atom:published', ns)
                year = published.text[:4] if published is not None and published.text else ""
                
                # Find PDF link
                pdf_url = None
                for link in entry.findall('atom:link', ns):
                    if link.attrib.get('title') == 'pdf':
                        pdf_url = link.attrib.get('href')
                        break
                
                if pdf_url:
                    filename = _sanitize_filename(f"{year}_{author}_{title}.pdf")
                    results.append({
                        "title": title,
                        "url": pdf_url + ".pdf" if not pdf_url.endswith('.pdf') else pdf_url,
                        "filename": filename,
                        "source": "ArXiv"
                    })
    except Exception as e:
        logger.warning(f"ArXiv aramasi basarisiz: {e}")
    return results

def search_duckduckgo(query: str, limit: int = 5) -> list:
    results = []
    try:
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        from ddgs import DDGS
        with DDGS() as ddgs:
            # Daha kesin PDF linkleri için ext:pdf kullanıyoruz
            search_query = f"{query} ext:pdf"
            ddgs_results = ddgs.text(search_query, max_results=limit)
            
            for item in ddgs_results:
                title = item.get("title", "Genel_Web_Makalesi")
                # Remove invalid chars from title early to avoid path issues
                title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
                url = item.get("href", "")
                
                # Sıkı endswith yerine linkin içinde .pdf geçip geçmediğine bak
                if ".pdf" in url.lower():
                    filename = _sanitize_filename(f"{title}.pdf")
                    results.append({
                        "title": title,
                        "url": url,
                        "filename": filename,
                        "source": "Genel Web (PDF)"
                    })
    except ImportError:
        logger.warning("duckduckgo_search kütüphanesi yüklü değil. 'pip install ddgs' ile kurabilirsiniz.")
    except Exception as e:
        logger.warning(f"DuckDuckGo aramasi basarisiz: {e}")
    return results

def search_archive_org(query: str, limit: int = 5) -> list:
    """
    İnternet Arşivi (archive.org) üzerinde arama yapar.
    Shamela ve diğer İslami kitap koleksiyonlarına erişim sağlar.
    """
    results = []
    try:
        # archive.org Advanced Search API
        params = {
            "q": f"{query} AND mediatype:texts AND format:pdf",
            "fl[]": ["identifier", "title", "creator", "year"],
            "rows": limit * 2,
            "output": "json",
            "sort[]": "downloads desc"
        }
        r = requests.get(
            "https://archive.org/advancedsearch.php",
            params=params, timeout=15,
            headers={"User-Agent": "VeFa-Academic-Bot/1.0"}
        )
        if r.status_code != 200:
            return results
        data = r.json()
        docs = data.get("response", {}).get("docs", [])
        for doc in docs[:limit]:
            identifier = doc.get("identifier", "")
            title = doc.get("title", identifier)
            creator = doc.get("creator", "")
            year = str(doc.get("year", ""))
            if not identifier:
                continue
            # Archive.org PDF URL: https://archive.org/download/{id}/{id}.pdf
            pdf_url = f"https://archive.org/download/{identifier}/{identifier}.pdf"
            name_parts = [p for p in [year, creator, title] if p]
            filename = _sanitize_filename("_".join(name_parts)[:90] + ".pdf")
            results.append({
                "title": title,
                "url": pdf_url,
                "filename": filename,
                "source": "Archive.org (Şamela/İslami)"
            })
    except Exception as e:
        logger.warning(f"Archive.org arama hatasi: {e}")
    return results


def search_noor_islamhouse(query: str, limit: int = 5) -> list:
    """
    IslamHouse.com üzerinde arama yapar (doğrudan PDF indirme destekli).
    Türkçe, Arapça ve çok dilli İslami akademik içerik sağlar.
    """
    results = []
    try:
        # IslamHouse arama API (JSON formatı)
        params = {
            "q": query,
            "lang": "ar",   # Arapça öncelikli
            "category": "book",
            "per_page": limit
        }
        r = requests.get(
            "https://islamhouse.com/ar/api/search/",
            params=params, timeout=15,
            headers={"User-Agent": "VeFa-Academic-Bot/1.0"}
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get("results", []) or data.get("data", [])
            for item in items[:limit]:
                title = item.get("title", item.get("name", "IslamHouse_Kitabi"))
                pdf_url = item.get("pdf_url") or item.get("file_url") or item.get("url", "")
                if not pdf_url or ".pdf" not in pdf_url.lower():
                    continue
                filename = _sanitize_filename(f"{title}.pdf")
                results.append({
                    "title": title,
                    "url": pdf_url,
                    "filename": filename,
                    "source": "IslamHouse.com"
                })
    except Exception as e:
        logger.warning(f"IslamHouse arama hatasi: {e}")

    # Noor-Book.com DuckDuckGo aramasıyla da destekle
    if len(results) < limit:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                noor_query = f"site:noor-book.com {query} pdf"
                noor_results = ddgs.text(noor_query, max_results=limit)
                for item in (noor_results or []):
                    url = item.get("href", "")
                    if ".pdf" in url.lower() or "noor-book.com" in url:
                        title = item.get("title", "Noor_Kitabi")
                        filename = _sanitize_filename(f"{title}.pdf")
                        results.append({
                            "title": title,
                            "url": url,
                            "filename": filename,
                            "source": "Noor-Book.com"
                        })
        except Exception as e:
            logger.warning(f"Noor-Book arama hatasi: {e}")
    return results[:limit]


def search_and_download(query: str, num_files: int, sources: list, progress_cb=None) -> tuple:
    """
    Belirtilen kaynaklarda arama yapar ve PDF'leri VeFa_Indirilen_Kaynaklar dizinine indirir.
    Dönen değer: (indirilen_dosya_yollari_listesi, hatalar_listesi)
    """
    download_dir = Path("VeFa_Indirilen_Kaynaklar")
    download_dir.mkdir(exist_ok=True)
    
    all_links = []
    
    if progress_cb:
        progress_cb(f"🔎 '{query}' için kaynaklar taranıyor...", 10)
        
    if "Semantic Scholar" in sources:
        all_links.extend(search_semantic_scholar(query, limit=num_files*2))
    if "OpenAlex" in sources:
        all_links.extend(search_openalex(query, limit=num_files*2))
    if "ArXiv" in sources:
        all_links.extend(search_arxiv(query, limit=num_files*2))
    if "Genel Web (PDF)" in sources:
        all_links.extend(search_duckduckgo(query, limit=num_files*2))
    if "Archive.org (Şamela)" in sources:
        all_links.extend(search_archive_org(query, limit=num_files*2))
    if "IslamHouse / Noor-Book" in sources:
        all_links.extend(search_noor_islamhouse(query, limit=num_files*2))

        
    # Deduplicate by url
    seen_urls = set()
    unique_links = []
    for item in all_links:
        if item["url"] not in seen_urls:
            unique_links.append(item)
            seen_urls.add(item["url"])
            
    # Sınırla
    unique_links = unique_links[:num_files]
    
    if not unique_links:
        return [], ["Hiçbir açık erişimli PDF kaynağı bulunamadı. Lütfen farklı anahtar kelimeler deneyin."]
        
    downloaded_paths = []
    errors = []
    
    for idx, item in enumerate(unique_links):
        if progress_cb:
            pct = 10 + int((idx / len(unique_links)) * 90)
            progress_cb(f"📥 {item['source']} üzerinden indiriliyor: {item['title'][:40]}...", pct)
            
        pdf_path = download_dir / item["filename"]
        
        # Eğer zaten inmişse atla
        if pdf_path.exists() and pdf_path.stat().st_size > 10000:
            downloaded_paths.append(str(pdf_path))
            continue
            
        try:
            headers = {"User-Agent": "VeFa-Academic-Bot/1.0"}
            r = requests.get(item["url"], headers=headers, timeout=30, stream=True)
            if r.status_code == 200:
                content_type = r.headers.get("Content-Type", "")
                if "pdf" in content_type.lower() or r.url.endswith(".pdf"):
                    with open(pdf_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    if pdf_path.stat().st_size > 10000: # En az 10KB
                        downloaded_paths.append(str(pdf_path))
                    else:
                        pdf_path.unlink(missing_ok=True)
                        errors.append(f"{item['title']} - Dosya bozuk veya paywall arkasında. |URL:{item['url']}|")
                else:
                    errors.append(f"{item['title']} - Gelen içerik PDF değil (Muhtemelen giriş sayfası). |URL:{item['url']}|")
            else:
                errors.append(f"{item['title']} - Sunucu hatası ({r.status_code}). |URL:{item['url']}|")
        except Exception as e:
            errors.append(f"{item['title']} - Bağlantı hatası: {str(e)} |URL:{item['url']}|")
            
    if progress_cb:
        progress_cb(f"✅ İndirme tamamlandı. Toplam {len(downloaded_paths)} dosya başarılı.", 100)
        
    return downloaded_paths, errors

def agentic_search_and_download(
    topic_and_headings: str,
    num_files: int,
    sources: list,
    provider: str,
    api_key: str,
    model_name: str,
    progress_cb=None
) -> tuple:
    """
    LLM kullanarak girilen konu ve baslik metninden 3-5 adet Ingilizce akademik arama sorgusu cikarir.
    Sonrasinda bu sorgularin her birini aratip, tek bir havuzda toplar ve indirir.
    """
    from engine.academic_engine import AcademicEngine
    import re
    
    queries = []
    if progress_cb:
        progress_cb("🤖 Ajan Modu: Konu ve başlıklar analiz ediliyor...", 5)
        
    try:
        engine = AcademicEngine(provider=provider, api_key=api_key, model_name=model_name)
        prompt = f"""You are an expert academic research librarian.
Based on the following thesis topic and syllabus/headings, generate exactly 4 distinct, highly relevant, and broad English search queries that can be used to search academic databases (like ArXiv, Semantic Scholar, OpenAlex). 
Do NOT use quotes. Keep the queries between 2 and 5 words. Return ONLY the queries, one per line.

TEXT:
{topic_and_headings}
"""
        try:
            response = engine.llm_func(prompt, system_prompt="You are an academic search specialist.")
        except TypeError:
            response = engine.llm_func(prompt)
        import re as _re
        _preamble_re = _re.compile(
            r'^\s*(here (are|is)|based on|these are|below are|i (have|generated|will)|'
            r'the following|sure,|okay,|certainly)',
            flags=_re.IGNORECASE
        )
        for line in response.splitlines():
            line = line.strip(" -*1234567890.\"'")
            if not line:
                continue
            if _preamble_re.match(line):
                continue
            word_count = len(line.split())
            if word_count < 1 or word_count > 8:
                # Genuine queries are short (the prompt asks for 2-5 words);
                # anything longer is almost certainly a leaked explanatory
                # sentence rather than an actual query.
                continue
            queries.append(line)
    except Exception as e:
        logger.error(f"Agentic LLM extraction failed: {e}")
        if progress_cb:
            progress_cb(f"⚠️ Yapay zeka sorgu üretemedi ({e}), basit aramaya geçiliyor...", 8)
    
    if not queries:
        # Fallback if LLM fails
        queries = [topic_and_headings[:50]]
        
    queries = list(set(queries))[:5] # Max 5 unique queries
    
    all_links = []
    
    # Calculate how many to fetch per query (we over-fetch to ensure we get num_files good ones)
    per_query_limit = max(3, (num_files * 2) // len(queries))
    
    for i, q in enumerate(queries):
        if progress_cb:
            progress_cb(f"🤖 Sorgu {i+1}/{len(queries)}: '{q}' taranıyor...", 10 + int(40 * (i/len(queries))))
            
        if "Semantic Scholar" in sources:
            all_links.extend(search_semantic_scholar(q, limit=per_query_limit))
        if "OpenAlex" in sources:
            all_links.extend(search_openalex(q, limit=per_query_limit))
        if "ArXiv" in sources:
            all_links.extend(search_arxiv(q, limit=per_query_limit))
        if "Genel Web (PDF)" in sources:
            all_links.extend(search_duckduckgo(q, limit=per_query_limit))
            
    # Deduplicate by url
    seen_urls = set()
    unique_links = []
    for item in all_links:
        if item["url"] and item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_links.append(item)
            
    if progress_cb:
        progress_cb(f"📥 Havuz oluşturuldu ({len(unique_links)} aday bulundu). Dosyalar indiriliyor...", 50)
        
    # Sort to prioritize PDFs if possible, then download up to num_files
    downloaded_files = []
    errors = []
    download_dir = Path("VeFa_Indirilen_Kaynaklar")
    download_dir.mkdir(exist_ok=True)
    
    # Attempt to download
    for idx, item in enumerate(unique_links):
        if len(downloaded_files) >= num_files:
            break
        
        if progress_cb:
            pct = 50 + int(50 * (len(downloaded_files) / num_files))
            progress_cb(f"📥 İndiriliyor ({len(downloaded_files)+1}/{num_files}): {item['title'][:40]}...", pct)
            
        url = item["url"]
        filename = item["filename"]
        target_path = download_dir / filename
        
        if target_path.exists():
            downloaded_files.append(str(target_path))
            continue
            
        try:
            headers = {"User-Agent": "VeFa-Academic-Bot/1.0"}
            r = requests.get(url, headers=headers, stream=True, timeout=30)
            if r.status_code == 200:
                # Content-Type kontrolu (stream=True iken r.content tum dosyayi RAM'e yukler)
                content_type = r.headers.get('Content-Type', '')
                is_pdf_header = 'application/pdf' in content_type or url.lower().endswith('.pdf')
                # Magic byte kontrolu: sadece ilk 512 byte'i cek
                first_chunk = next(r.iter_content(chunk_size=512), b'')
                is_pdf_magic = first_chunk[:4] == b'%PDF'
                if is_pdf_header or is_pdf_magic:
                    with open(target_path, 'wb') as f:
                        f.write(first_chunk)
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    downloaded_files.append(str(target_path))
                else:
                    errors.append(f"PDF formatinda degil: {url}")
            else:
                errors.append(f"HTTP {r.status_code}: {url}")
        except Exception as e:
            errors.append(f"Baglanti hatasi: {url} -> {str(e)[:50]}")
            
    return downloaded_files, errors
