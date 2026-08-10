# -*- coding: utf-8 -*-
"""
VeFa - Arka Plan İş Takipçi ve Otomatik Yeniden Bağlanma Modülü
Bu modül, kullanıcı tarayıcıyı kapatsa veya yeni sekme açsa dahi
çalışmakta olan tez üretimi veya dosya çevirisi işlemlerinin durumunu
diskte persistent olarak saklar ve Streamlit açıldığında otomatik kurtarır.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

JOB_FILE = Path(".vefa_state/current_job.json")


def update_job_status(
    status: str,  # 'running', 'completed', 'error'
    step: str = "",
    progress: float = 0.0,
    topic: str = "",
    mode: Optional[str] = None,
    docx_path: Optional[str] = None,
    md_path: Optional[str] = None,
    error: Optional[str] = None,
    is_new_job: bool = False,
    **kwargs
):
    """
    Write or update global job state file.
    """
    global CANCEL_FLAG
    if is_new_job or (progress is not None and progress <= 0.05):
        CANCEL_FLAG = False

    if CANCEL_FLAG and status == "running":
        return

    JOB_FILE.parent.mkdir(parents=True, exist_ok=True)

    if is_new_job:
        # A brand-new job must never inherit a previous job's docx_path,
        # md_path, topic, or error — otherwise a stale file from an
        # earlier (unrelated) generation can leak into the new job's
        # status/banner while it is still running or if it errors out.
        existing = {}
    else:
        # Preserve existing paths if not provided
        existing = get_job_status() or {}

    data = existing.copy() # Inherit all previous keys (unless this is a new job)
    data.update({
        "status": status,
        "step": step or existing.get("step", ""),
        "progress": progress if progress is not None else existing.get("progress", 0.0),
        "topic": topic or existing.get("topic", "Akademik Çalışma"),
        "mode": mode if mode is not None else existing.get("mode", "Mod 1"),
        "docx_path": docx_path or existing.get("docx_path"),
        "md_path": md_path or existing.get("md_path"),
        "error": error,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    # Overwrite/add custom kwargs
    for k, v in kwargs.items():
        data[k] = v
        
    try:
        with open(JOB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_job_status() -> Optional[Dict[str, Any]]:
    """
    Read global job state file if exists. Automatically clears stale jobs if no update for > 15 minutes.
    """
    if not JOB_FILE.exists():
        return None
    try:
        with open(JOB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data and data.get("status") == "running" and "updated_at" in data:
            try:
                last_updated = datetime.strptime(data["updated_at"], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - last_updated).total_seconds() > 900:  # 15 mins timeout
                    clear_job()
                    return None
            except Exception:
                pass
        return data
    except Exception:
        return None


CANCEL_FLAG = False

def reset_cancel_flag():
    global CANCEL_FLAG
    CANCEL_FLAG = False

def cancel_job():
    """
    Mark global job as cancelled and delete state file.
    """
    global CANCEL_FLAG
    CANCEL_FLAG = True
    if JOB_FILE.exists():
        try:
            os.remove(JOB_FILE)
        except Exception:
            pass

def is_job_cancelled() -> bool:
    """
    Check if the current job was cancelled.
    """
    global CANCEL_FLAG
    return CANCEL_FLAG

def clear_job():
    """
    Clear global job state file.
    """
    global CANCEL_FLAG
    CANCEL_FLAG = False
    if JOB_FILE.exists():
        try:
            os.remove(JOB_FILE)
        except Exception:
            pass
