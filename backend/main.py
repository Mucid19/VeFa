import sys
import os
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from engine.resource_downloader import search_and_download, agentic_search_and_download
from engine.academic_engine import AcademicEngine
from engine.job_tracker import update_job_status, get_job_status, reset_cancel_flag
from engine.academic_reviewer import extract_text_from_file, audit_and_fix_thesis
from engine.turkish_docx_generator import generate_turkish_academic_docx

app = FastAPI(title="VeFa API", description="Akademik Tez & Makale Asistanı API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    agent_mode: bool = False
    provider: str = "Gemini"
    api_key: str = ""
    model_name: str = "gemini-1.5-pro"
    
@app.post("/api/search")
def search_academic_sources(req: SearchRequest):
    # Orijinal motoru kullanarak tüm özellikleri aktifleştiriyoruz (İndirme + Hata Raporlama + Agent)
    sources = ["Semantic Scholar", "OpenAlex", "ArXiv", "Genel Web (PDF)"]
    
    # Callback fonksiyonu (terminale yazdirmayalim ki encoding sorunu olmasin)
    def p_cb(msg, pct):
        pass

    if req.agent_mode and req.api_key:
        downloaded, errors = agentic_search_and_download(
            topic_and_headings=req.query,
            num_files=req.limit,
            sources=sources,
            provider=req.provider,
            api_key=req.api_key,
            model_name=req.model_name,
            progress_cb=p_cb
        )
    else:
        # Eski sistemin normal arama-indirme motorunu kullan (daha çok sonuç bulur ve indirir)
        downloaded, errors = search_and_download(
            query=req.query,
            num_files=req.limit,
            sources=sources,
            progress_cb=p_cb
        )
        
    # Frontend'in okuyabileceği formata çevir
    results = []
    for p in downloaded:
        results.append({
            "title": os.path.basename(p),
            "url": "file://" + str(Path(p).absolute()),
            "status": "İndirildi"
        })
        
    for e in errors:
        url_part = "#"
        if "|URL:" in e:
            parts = e.split("|URL:")
            e_text = parts[0].strip()
            url_part = parts[1].replace("|", "").strip()
        else:
            e_text = e

        results.append({
            "title": e_text.split(' - ')[0] if ' - ' in e_text else e_text,
            "url": url_part,
            "status": "HATA: " + e_text
        })

    return {
        "status": "success",
        "results": results,
        "total_downloaded": len(downloaded),
        "total_errors": len(errors)
    }

class GenerateRequest(BaseModel):
    topic: str
    academic_level: str = "Yüksek Lisans Tezi"
    language: str = "tr"
    target_words: int = 5000
    provider: str = "Ollama"
    api_key: str = ""
    model_name: str = "deepseek-r1:14b"
    ollama_host: str = "http://localhost:11434"

def run_thesis_generation(req: GenerateRequest):
    reset_cancel_flag()
    update_job_status(status="running", step="Akademik Tez Üretimi Başlatılıyor", progress=0.01, topic=req.topic, is_new_job=True)
    try:
        engine = AcademicEngine(
            provider=req.provider.lower() if req.provider != "Ollama (Yerel)" else "ollama",
            api_key=req.api_key,
            model_name=req.model_name,
            ollama_host=req.ollama_host
        )
        engine.generate_full_thesis(
            topic=req.topic,
            academic_level=req.academic_level,
            target_words=req.target_words,
            language=req.language,
            use_live_search=False,
            include_lists=True,
            use_advanced_rag=False
        )
    except Exception as e:
        update_job_status(status="error", error=str(e))

@app.post("/api/generate")
def start_generation(req: GenerateRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_thesis_generation, req)
    return {"status": "started"}

def run_mod3_review(file_path: str, file_name: str, target_lang: str, provider: str, api_key: str, model_name: str, ollama_host: str):
    reset_cancel_flag()
    update_job_status(status="running", step="Dosya okunuyor...", progress=0.1, topic=f"Dosya İşleme: {file_name}", mode="Mod 3", is_new_job=True)
    try:
        with open(file_path, "rb") as f:
            raw_bytes = f.read()
            
        extracted_text = extract_text_from_file(raw_bytes, file_name)
        
        def _report_prog(pct, step, msg=""):
            update_job_status(status="running", step=step, progress=pct, mode="Mod 3")
            
        prov_key = "ollama" if provider == "Ollama (Yerel)" else provider.lower()
        engine_inst = AcademicEngine(provider=prov_key, api_key=api_key, model_name=model_name, ollama_host=ollama_host)
        
        cleaned_md, audit_report = audit_and_fix_thesis(
            extracted_text,
            llm_func=engine_inst.llm_func,
            target_language=target_lang,
            fix_language=True,
            fix_yok_formatting=True,
            fix_citations=True,
            progress_callback=_report_prog
        )
        
        output_dir = Path("output_drafts")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rev_docx_path = str(output_dir / f"VeFa_Mod3_{timestamp}.docx")
        
        metadata = {
            "title": file_name,
            "author": "Yazar",
            "academic_level": "Akademik Çeviri/Denetim",
            "year": datetime.now().year,
            "language": target_lang if target_lang != "same" else "tr"
        }
        generate_turkish_academic_docx(
            cleaned_md,
            rev_docx_path,
            metadata=metadata,
            include_cover_page=True,
            include_yok_frontmatter=True,
            abbr_list=None,
            figures=None,
            tables=None,
        )
        
        update_job_status(
            status="completed",
            step="Tamamlandı",
            progress=1.0,
            topic=f"Dosya Çevirisi: {file_name}",
            mode="Mod 3",
            docx_path=rev_docx_path
        )
    except Exception as e:
        update_job_status(status="error", error=str(e))
    finally:
        # Cleanup uploaded temp file
        if os.path.exists(file_path):
            os.remove(file_path)

@app.post("/api/review")
async def start_review(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...), 
    target_lang: str = Form("same"),
    provider: str = Form("Ollama (Yerel)"),
    api_key: str = Form(""),
    model_name: str = Form("deepseek-r1:14b"),
    ollama_host: str = Form("http://localhost:11434")
):
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / file.filename
    
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
        
    background_tasks.add_task(run_mod3_review, str(file_path), file.filename, target_lang, provider, api_key, model_name, ollama_host)
    return {"status": "started"}

@app.get("/api/status")
def get_status():
    status = get_job_status()
    return {"status": status}
    
@app.get("/api/download")
def download_file(path: str):
    if os.path.exists(path):
        return FileResponse(path, filename=os.path.basename(path))
    return {"error": "File not found"}
