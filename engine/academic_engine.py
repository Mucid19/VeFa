# -*- coding: utf-8 -*-
"""
VeFa - Akademik Üretim ve Denetim Motoru
Çok dilli (Türkçe, Arapça, İngilizce) yapay zeka entegrasyonu (Gemini, OpenAI, Ollama),
canlı akademik veritabanı taraması (CrossRef & Semantic Scholar) ve otomatik sanitization.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from engine.turkish_prompts import LANG_CONFIGS, SYSTEM_PROMPT, get_prompts_for_language
from engine.turkish_docx_generator import generate_turkish_academic_docx

logger = logging.getLogger("VeFaEngine")


# Lines matching these patterns are near-certainly AI conversational leakage
# (self-introduction, chat-style preamble, or the model echoing back its own
# instructions) rather than actual academic content. Weaker/local models are
# far more prone to this than frontier cloud models, so this list is tuned
# against real leaked output rather than hypothetical examples.
_LEAKAGE_LINE_PATTERNS = [
    r'^\s*here[\'’]?s?\s+(is\s+)?the\b',
    r'^\s*it appears that\b',
    r'^\s*it seems (that|like)\b',
    r'^\s*you (mentioned|mention|are discussing|are asking)\b',
    r'^\s*i would (recommend|suggest)\b',
    r'^\s*i recommend (exploring|the following)\b',
    r'^\s*as an? (senior |esteemed |)?academic (expert|writer)\b',
    r'^\s*a (very )?(esteemed|senior|high-level)\b.*\bexpert\b',
    r'^\s*bir\s+(yüksek seviye|üst düzey|senior)?\s*akademik uzman(dır|ım)\b',
    r'akademik uzmandır.{0,60}(analiz edeceğim|yazacağım|inceleyeceğim)',
    r'hakkındaki (tezinize|tezine|notunuza|makalenize)\b',
    r'^\s*(işte|i\u015fte)\s+(metin|özet|abstract|sonuç)',
    r'^\s*tüm metni eksiksiz şekilde\b',
    r'^\s*t[uü]m metni.*yeniden yaz\b',
    r'^\s*metin:\s*$',
    r'^\s*text:\s*$',
    r'^\s*to further analyze this topic\b',
    r'^\s*genel olarak,?\s*tezinizin\b',
    r'^\s*kaynakları gözden geçirerek\b',
    r'^\s*kaynaklardan anladığım kadarıyla\b',
    r'^\s*içeriğin özetlenmesi:?\s*$',
    r'^\s*(işte|aşağıda) (özet|metin|bölüm)\s*:?\s*$',
]
_LEAKAGE_LINE_RE = re.compile('|'.join(_LEAKAGE_LINE_PATTERNS), flags=re.IGNORECASE)


def strip_ai_conversational_leakage(text: str) -> str:
    """
    Removes lines that are AI conversational preamble, self-introduction, or
    an echo of our own correction-prompt instructions — as opposed to actual
    academic content. This is defense-in-depth on top of prompt instructions,
    since weaker/local models frequently ignore "don't do this" instructions.
    """
    if not text:
        return text
    kept = [line for line in text.splitlines() if not _LEAKAGE_LINE_RE.search(line)]
    return "\n".join(kept)


def sanitize_turkish_text(text: str, language: str = "tr") -> str:
    """
    Remove AI conversational fluff, strip meta-notes (Word count: X),
    convert bold headings to Markdown # headers, and enforce strict target language academic terminology.
    """
    if not text:
        return ""

    text = strip_ai_conversational_leakage(text)

    # Remove markdown code fence wrappers if present
    text = re.sub(r'^```markdown\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)

    # Remove AI conversational introductory sentences & meta notes (English, Turkish, Arabic)
    text = re.sub(r'^(Here (are|is)|Below is|İşte|Aşağıda|Harika|Memnuniyetle|Tabii|Pekala|إليك|فيما يلي).*?:\s*\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*(Word count|Target word count|Total words|Note):\s*.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\[?(Word count|Target word count|Total words):\s*.*?\]?', '', text, flags=re.IGNORECASE)

    # Convert bold heading lines (**1. GİRİŞ**, **1.1. Problem Tanımı:**) into Markdown # headings
    def _bold_heading_replacer(match):
        raw_num = match.group(1).strip()
        title = match.group(2).strip().rstrip(':')
        clean_num = raw_num.rstrip('.')
        
        dots = clean_num.count('.')
        if dots == 0:
            return f"\n# {clean_num}. {title}\n"
        elif dots == 1:
            return f"\n## {clean_num}. {title}\n"
        else:
            return f"\n### {clean_num}. {title}\n"

    text = re.sub(r'^\s*(?:\*\*)?(\d+(?:\.\d+)*\.?)\s+([^*#\n]+)(?:\*\*)?:?\s*$', _bold_heading_replacer, text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\*\*(\d+(?:\.\d+)*\.?)\s+([^*]+)\*\*:?\s*$', _bold_heading_replacer, text, flags=re.MULTILINE)

    # Remove bullet points from full prose paragraphs
    def _clean_prose_bullets(line):
        line_s = line.strip()
        if re.match(r'^[\*\-\+]\s+[A-ZÇĞİÖŞÜa-zçğıöşü\u0600-\u06FF]', line_s) and len(line_s) > 80 and line_s.endswith('.'):
            return re.sub(r'^[\*\-\+]\s+', '', line_s)
        return line

    lines = [ _clean_prose_bullets(l) for l in text.splitlines() ]
    text = "\n".join(lines)

    # Enforce Section Titles based on target language
    lang = language.lower()
    cfg = LANG_CONFIGS.get(lang, LANG_CONFIGS["tr"])

    if lang == "ar":
        replacements = {
            r'^#\s*(1\.\s*BÖLÜM:\s*GİRİŞ|GİRİŞ|CHAPTER 1:\s*INTRODUCTION|INTRODUCTION)\b': f"# {cfg['intro']}",
            r'^#\s*(2\.\s*BÖLÜM:\s*LİTERATÜR TARAMASI|LİTERATÜR TARAMASI|CHAPTER 2:\s*LITERATURE REVIEW|LITERATURE REVIEW)\b': f"# {cfg['lit_review']}",
            r'^#\s*(3\.\s*BÖLÜM:\s*YÖNTEM VE METODOLOJİ|YÖNTEM VE METODOLOJİ|CHAPTER 3:\s*METHODOLOGY|METHODOLOGY)\b': f"# {cfg['methodology']}",
            r'^#\s*(4\.\s*BÖLÜM:\s*BULGULAR VE ANALİZ|BULGULAR VE ANALİZ|CHAPTER 4:\s*RESULTS AND ANALYSIS|RESULTS)\b': f"# {cfg['results']}",
            r'^#\s*(5\.\s*BÖLÜM:\s*TARTIŞMA VE DEĞERLENDİRME|TARTIŞMA VE DEĞERLENDİRME|CHAPTER 5:\s*DISCUSSION|DISCUSSION)\b': f"# {cfg['discussion']}",
            r'^#\s*(6\.\s*BÖLÜM:\s*SONUÇ VE ÖNERİLER|SONUÇ VE ÖNERİLER|CHAPTER 6:\s*CONCLUSION AND RECOMMENDATIONS|CONCLUSION)\b': f"# {cfg['conclusion']}",
            r'^#\s*(KAYNAKÇA|BIBLIYOGRAFYA|REFERENCES|BIBLIOGRAPHY)\b': f"# {cfg['references']}",
            r'^#\s*(ÖZET|ABSTRACT)\b': f"# {cfg['abstract']}",
            r'\b(Anahtar Kelimeler|Keywords):\s*': f"{cfg['keywords']}: ",
            r'\bet al\.?(?=[\s,;:\)]|$)': 'وآخرون',
            r'\bsome scholars that\b': 'ويرى بعض الباحثين أن',
            r'\bimplementation of a comprehensive plan to preserve\b': 'تنفيذ خطة شاملة للحفاظ على',
            r'\bimplementation of policies and programs that promote\b': 'تنفيذ السياسات والبرامج التي تعزز',
            r'\bimplementation of\b': 'تنفيذ',
            r'\bthe role of\b': 'دور',
            r'\bpreserving\b': 'الحفاظ على',
            r'\bcultural heritage\b': 'التراث الثقافي',
            r'\binterfaith dialogue\b': 'الحوار بين الأديان',
            r'\bAPPROACHES QUALITATIVE quantitative\b': 'المناهج النوعية والكمية',
            r'\btechnikas ANALYTICAL TWO\b': 'التقنيات التحليلية',
            r'\bRetrieved from\b': 'مأخوذ من',
            r'\bJournal of Islamic Studies\b': 'مجلة الدراسات الإسلامية',
            r'\bJournal of Cultural Heritage\b': 'مجلة التراث الثقافي',
            r'\bJournal of Cultural Preservation\b': 'مجلة الحفاظ على التراث',
            r'\bJournal of Historical Studies\b': 'مجلة الدراسات التاريخية',
            r'\bJournal of Heritage Studies\b': 'مجلة دراسات التراث',
            r'\bJournal of Islamic Education\b': 'مجلة التربية الإسلامية',
            r'\bJournal of\b': 'مجلة',
            r'\bThe role of\b': 'دور',
            r'\bThe significance of\b': 'أهمية',
            r'\bThe importance of\b': 'أهمية',
            r'\bHanefî kültürünün yaşatılması\b': 'إحياء الثقافة الحنفية',
            r'\bHanefî kültürü\b': 'الثقافة الحنفية',
            r'\bAzamiye Külliyesi\b': 'الكلية الأعظمية',
            r'\bIrak\'ta\b': 'في العراق',
            r'\bIrak\b': 'العراق',
            r'\bGeçmişi ve bugünü\b': 'ماضيها وحاضرها',
            r'\bnin rolü\b': 'ودورها',
            r'\bTarihsel ve sosyo-kültürel boyutlar\b': 'الأبعاد التاريخية والاجتماعية والثقافية',
        }

        def _clean_arabic_latin_leftovers(line):
            # Clean explicit metadata fluff and LLM conversational notes
            if re.match(r'^\s*(Word count|Target word count|Here is the|Please note|Note:|translator note:)\b.*$', line, flags=re.IGNORECASE):
                return ""
            # Fix space after AL- prefix (e.g. "ال لحم" -> "اللحم")
            line = re.sub(r'\bال\s+([\u0600-\u06FF])', r'ال\1', line)
            # Remove random non-Arabic non-Latin hallucinations (Thai, Cyrillic, Chinese)
            line = re.sub(r'[\u0E00-\u0E7F\u0400-\u04FF\u4E00-\u9FFF]', '', line)
            return line

        lines = [ _clean_arabic_latin_leftovers(l) for l in text.splitlines() ]
        lines = [ l for l in lines if l is not None ]
        text = "\n".join(lines)
    elif lang == "en":
        replacements = {
            r'^#\s*(1\.\s*BÖLÜM:\s*GİRİŞ|GİRİŞ|الفصل الأول:\s*المقدمة)\b': f"# {cfg['intro']}",
            r'^#\s*(2\.\s*BÖLÜM:\s*LİTERATÜR TARAMASI|LİTERATÜR TARAMASI|الفصل الثاني:\s*الدراسات السابقة)\b': f"# {cfg['lit_review']}",
            r'^#\s*(3\.\s*BÖLÜM:\s*YÖNTEM VE METODOLOJİ|YÖNTEM VE METODOLOJİ|الفصل الثالث:\s*منهجية البحث)\b': f"# {cfg['methodology']}",
            r'^#\s*(4\.\s*BÖLÜM:\s*BULGULAR VE ANALİZ|BULGULAR VE ANALİZ|الفصل الرابع:\s*عرض النتائج وتحليلها)\b': f"# {cfg['results']}",
            r'^#\s*(5\.\s*BÖLÜM:\s*TARTIŞMA VE DEĞERLENDİRME|TARTIŞMA VE DEĞERLENDİRME|الفصل الخامس:\s*مناقشة النتائج)\b': f"# {cfg['discussion']}",
            r'^#\s*(6\.\s*BÖLÜM:\s*SONUÇ VE ÖNERİLER|SONUÇ VE ÖNERİLER|الفصل السادس:\s*الخاتمة والتوصيات)\b': f"# {cfg['conclusion']}",
            r'^#\s*(KAYNAKÇA|BIBLIYOGRAFYA|المصادر والمراجع|المراجع)\b': f"# {cfg['references']}",
            r'^#\s*(ÖZET|الملخص)\b': f"# {cfg['abstract']}",
            r'\b(Anahtar Kelimeler|الكلمات المفتاحية):\s*': f"{cfg['keywords']}: ",
        }
    else: # Default Turkish
        replacements = {
            r'\bet al\.?(?=[\s,;:\)]|$)': 've ark.',
            r'\bVol\.\b': 'Cilt',
            r'\bNo\.\b': 'Sayı',
            r'\bpp\.\b': 's.',
            r'\bAccessed on:\b': 'Erişim tarihi:',
            r'\bRetrieved from\b': 'Erişim adresi:',
            r'^#\s*(CHAPTER 1:\s*INTRODUCTION|INTRODUCTION|الفصل الأول:\s*المقدمة)\b': f"# {cfg['intro']}",
            r'^#\s*(CHAPTER 2:\s*LITERATURE REVIEW|LITERATURE REVIEW|الفصل الثاني:\s*الدراسات السابقة)\b': f"# {cfg['lit_review']}",
            r'^#\s*(CHAPTER 3:\s*METHODOLOGY|METHODOLOGY|الفصل الثالث:\s*منهجية البحث)\b': f"# {cfg['methodology']}",
            r'^#\s*(CHAPTER 4:\s*RESULTS AND ANALYSIS|RESULTS|الفصل الرابع:\s*عرض النتائج وتحليلها)\b': f"# {cfg['results']}",
            r'^#\s*(CHAPTER 5:\s*DISCUSSION|DISCUSSION|الفصل الخامس:\s*مناقشة النتائج)\b': f"# {cfg['discussion']}",
            r'^#\s*(CHAPTER 6:\s*CONCLUSION|CONCLUSION|الفصل السادس:\s*الخاتمة والتوصيات)\b': f"# {cfg['conclusion']}",
            r'^#\s*(REFERENCES|BIBLIOGRAPHY|المصادر والمراجع|المراجع)\b': f"# {cfg['references']}",
            r'^#\s*(ABSTRACT|الملخص)\b': f"# {cfg['abstract']}",
            r'\b(Keywords|الكلمات المفتاحية):\s*': f"{cfg['keywords']}: ",
        }

    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text, flags=re.MULTILINE | re.IGNORECASE)

    if lang == "ar":
        def _clean_arabic_latin_leftovers(line):
            if line.startswith('#'):
                return line
            if re.search(r'[\u0600-\u06FF]', line):
                def _strip_latin_if_not_url(m):
                    w = m.group(0)
                    if w.lower() in ['http', 'https', 'doi', 'org', 'com', 'pdf', 'n.d']:
                        return w
                    return ''
                line = re.sub(r'[A-Za-z\u00C0-\u024F\-\']+', _strip_latin_if_not_url, line)
                # Clean orphaned commas and punctuation left behind by stripped Latin words!
                line = re.sub(r'([,\u060C\.]\s*){2,}', ' ', line)
                line = re.sub(r'\s+[,,\u060C\.](\s+|$)', ' ', line)
                line = re.sub(r'^\s*[,,\u060C\.]+\s*', '', line)
                line = re.sub(r'\s+', ' ', line).strip()
            return line

        lines = [ _clean_arabic_latin_leftovers(l) for l in text.splitlines() ]
        text = "\n".join(lines)

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# English stopwords common enough that their presence (several at once, in a
# long ASCII-only sentence with no Turkish-specific letters) is a strong
# signal that the model drifted into English mid-paragraph. Turkish uses the
# Latin alphabet too, so — unlike Arabic — we can't just strip foreign-script
# words; we have to detect whole drifted SENTENCES instead.
_EN_STOPWORDS = {
    "the", "and", "of", "is", "are", "in", "to", "for", "that", "with",
    "this", "from", "was", "were", "have", "has", "been", "which", "their",
    "its", "these", "those", "however", "therefore", "because", "between",
    "among", "through", "such", "also", "not", "but", "as", "by", "an",
    "study", "research", "role", "significance", "importance",
}
_TR_SPECIFIC_CHARS = set("çğıİöşüÇĞÖŞÜ")


def _looks_like_english_sentence(sentence: str) -> bool:
    s = sentence.strip()
    if len(s) < 40:
        return False
    if any(ch in _TR_SPECIFIC_CHARS for ch in s):
        return False
    words = re.findall(r"[A-Za-z']+", s)
    if len(words) < 6:
        return False
    stop_hits = sum(1 for w in words if w.lower() in _EN_STOPWORDS)
    return stop_hits >= 3


def _looks_like_chinese_sentence(sentence: str) -> bool:
    # Check for CJK Unified Ideographs (Chinese, Japanese, Korean characters)
    # Even a few characters indicate a severe hallucination/drift since this is a Turkish app.
    cjk_chars = re.findall(r'[\u4e00-\u9fff]', sentence)
    return len(cjk_chars) >= 3


def detect_language_drift(text: str, language: str) -> List[str]:
    """
    Scan generated text for sentences that appear to have drifted into
    English even though the target language is Turkish. Citation/URL/DOI
    lines, headings, and [[fn:...]] footnote-marker contents are skipped to
    avoid flagging legitimate English article titles/citations. Returns the
    list of suspect sentences (empty list = no drift detected).
    """
    if language != "tr" or not text:
        return []

    # Footnote markers may legitimately contain English bibliographic info
    # (author names, English article titles) — strip them before scanning so
    # they can't trigger a false-positive "drifted to English" correction.
    text_without_footnotes = re.sub(r'\[\[fn:.*?\]\]', ' ', text, flags=re.DOTALL)

    suspects = []
    for sentence in re.split(r'(?<=[.!?])\s+', text_without_footnotes):
        line = sentence.strip()
        if not line or line.startswith('#') or line.startswith('|'):
            continue
        if 'http' in line.lower() or 'doi' in line.lower() or line.startswith('**'):
            continue
        if _looks_like_english_sentence(line) or _looks_like_chinese_sentence(line):
            suspects.append(line)
    return suspects


def ensure_ollama_running(ollama_host: str = "http://localhost:11434") -> bool:
    """Check if Ollama server is responding. If not, automatically launch Ollama app in background."""
    import requests, subprocess, shutil, time
    base_url = ollama_host.rstrip('/')
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=2)
        if r.status_code == 200:
            return True  # Already running!
    except Exception:
        pass

    # Try to start Ollama automatically on Windows
    ollama_exec = shutil.which("ollama")
    if not ollama_exec:
        appdata_path = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama app.exe"
        if appdata_path.exists():
            ollama_exec = str(appdata_path)

    if ollama_exec:
        try:
            creation_flags = 0x08000000 if os.name == 'nt' else 0  # CREATE_NO_WINDOW
            if "ollama app.exe" in str(ollama_exec).lower():
                subprocess.Popen([str(ollama_exec)], creationflags=creation_flags)
            else:
                subprocess.Popen([str(ollama_exec), "serve"], creationflags=creation_flags)
            
            # Wait up to 5 seconds for Ollama server to initialize
            for _ in range(10):
                time.sleep(0.5)
                try:
                    r = requests.get(f"{base_url}/api/tags", timeout=1)
                    if r.status_code == 200:
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    return False


class AcademicEngine:
    def __init__(self, provider: str = "gemini", api_key: Optional[str] = None, model_name: Optional[str] = None, ollama_host: str = "http://localhost:11434"):
        self.provider = provider.lower()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        self.ollama_host = ollama_host.rstrip('/')

        if self.provider == "gemini":
            if not self.api_key:
                raise ValueError("Gemini API Key bulunamadı! Lütfen geçerli bir Gemini/Google API Key girin.")
            self.model_name = self.model_name or "gemini-3.1-pro-preview"
            self._init_gemini()
        elif self.provider == "openai":
            if not self.api_key:
                raise ValueError("OpenAI API Key bulunamadı! Lütfen geçerli bir OpenAI API Key girin.")
            self.model_name = self.model_name or "gpt-4o-mini"
            self._init_openai()
        elif self.provider == "ollama":
            self.model_name = self.model_name or "llama3"
            ensure_ollama_running(self.ollama_host)
            self.llm_func = self._call_ollama
        else:
            raise ValueError(f"Desteklenmeyen sağlayıcı: {provider}")

    def _init_gemini(self):
        """Initialize Gemini client."""
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            self.llm_func = self._call_gemini_new_sdk
        except ImportError:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.genai_legacy = genai
                self.llm_func = self._call_gemini_legacy_sdk
            except ImportError:
                raise ImportError("google-genai veya google-generativeai paketi bulunamadı! Lütfen `pip install google-genai` çalıştırın.")

    def _call_gemini_new_sdk(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        sys_p = system_prompt or SYSTEM_PROMPT
        raw_model = (self.model_name or "gemini-3.1-pro-preview").strip()
        fallback_models = [raw_model, "gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        seen = set()
        models_to_try = [m for m in fallback_models if m and not (m in seen or seen.add(m))]

        last_err = None
        for m in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=f"{sys_p}\n\n{prompt}"
                )
                try:
                    if response and response.text:
                        return response.text
                except (ValueError, AttributeError) as resp_err:
                    # Gemini safety filter veya recitation engeli
                    logger.warning(f"Gemini response.text erisim hatasi (safety/recitation): {resp_err}")
                    last_err = resp_err
                    continue
            except Exception as e:
                last_err = e
                continue
        raise last_err or RuntimeError("Gemini API isteği başarısız oldu. Lütfen API anahtarınızı kontrol edin.")

    def _call_gemini_legacy_sdk(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        sys_p = system_prompt or SYSTEM_PROMPT
        raw_model = (self.model_name or "gemini-3.1-pro-preview").strip()
        fallback_models = [raw_model, "gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        seen = set()
        models_to_try = [m for m in fallback_models if m and not (m in seen or seen.add(m))]

        last_err = None
        for m in models_to_try:
            try:
                model = self.genai_legacy.GenerativeModel(m)
                response = model.generate_content(f"{sys_p}\n\n{prompt}")
                try:
                    if response and response.text:
                        return response.text
                except (ValueError, AttributeError) as resp_err:
                    logger.warning(f"Gemini legacy response.text erisim hatasi: {resp_err}")
                    last_err = resp_err
                    continue
            except Exception as e:
                last_err = e
                continue
        raise last_err or RuntimeError("Gemini API isteği başarısız oldu. Lütfen API anahtarınızı kontrol edin.")

    def _init_openai(self):
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
            self.llm_func = self._call_openai
        except ImportError:
            raise ImportError("openai paketi bulunamadı! Lütfen `pip install openai` çalıştırın.")

    def _call_openai(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        sys_p = system_prompt or SYSTEM_PROMPT
        raw_model = (self.model_name or "gpt-4o-mini").strip()
        fallback_models = [raw_model, "gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        seen = set()
        models_to_try = [m for m in fallback_models if m and not (m in seen or seen.add(m))]

        last_err = None
        for m in models_to_try:
            try:
                response = self.client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.4
                )
                if response and response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content
            except Exception as e:
                last_err = e
                continue
        raise last_err or RuntimeError("OpenAI API isteği başarısız oldu. Lütfen API anahtarınızı kontrol edin.")

    def _call_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        import requests
        sys_p = system_prompt or SYSTEM_PROMPT
        base_url = self.ollama_host.rstrip('/')

        # Smart Model Auto-Match: check models installed in Ollama (e.g. llama3 -> llama3.1)
        target_model = self.model_name
        try:
            r_tags = requests.get(f"{base_url}/api/tags", timeout=3)
            if r_tags.status_code == 200:
                installed = [m.get("name", "") for m in r_tags.json().get("models", [])]
                installed_clean = [m.split(":")[0] for m in installed]
                
                if target_model in installed or f"{target_model}:latest" in installed:
                    pass
                elif target_model.split(":")[0] in installed_clean:
                    idx = installed_clean.index(target_model.split(":")[0])
                    target_model = installed[idx]
                elif target_model in ["llama3", "llama3.1"] and any("llama3" in m for m in installed):
                    for m in installed:
                        if "llama3" in m:
                            target_model = m
                            break
                elif installed:
                    target_model = installed[0]
        except Exception:
            pass

        url = f"{base_url}/api/generate"
        payload = {
            "model": target_model,
            "system": sys_p,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.4
            }
        }
        try:
            resp = requests.post(url, json=payload, timeout=3000)  # Uzun süren işlemler için timeout artırıldı (300 -> 3000)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama sunucusuna bağlanılamadı ({self.ollama_host})! Lütfen Ollama uygulamasının çalıştığından ve modelin indirildiğinden emin olun. Hata: {str(e)}")

    def generate_full_thesis(
        self,
        topic: str,
        academic_level: str = "Yüksek Lisans Tezi",
        target_words: int = 5000,
        author: str = "Araştırmacı",
        advisor: str = "Prof. Dr. Danışman",
        institution: str = "T.C. İSTANBUL ÜNİVERSİTESİ",
        faculty: str = "LİSANSÜSTÜ EĞİTİM ENSTİTÜSÜ",
        city: str = "İstanbul",
        include_english_abstract: bool = True,
        use_live_search: bool = False,
        include_cover_page: bool = True,
        language: str = "tr",
        progress_callback: Optional[Callable[[float, str, str], None]] = None,
        custom_sections: Optional[List[Dict[str, str]]] = None,
        provided_sources: Optional[str] = None,
        strict_sources_only: bool = False,
        citation_style: str = "apa",
        include_lists: bool = True,
        qa_level: str = "fast",
        include_deep_search: bool = False,
        pdf_paths: Optional[List[Path]] = None,
        use_advanced_rag: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute full academic writing pipeline in chosen target language.
        Returns dictionary with paths to exported .docx and .md files, and section contents.
        pdf_paths: original uploaded PDF/TXT/MD file paths (if any). When given,
            the RAG index is built by reading each file's FULL text, so
            relevant-passage retrieval isn't limited by provided_sources'
            per-prompt character cap — this matters most with many (50-100+)
            uploaded files, where naive truncation would otherwise silently
            drop most of each document before it's ever considered.

        custom_sections: optional ordered list of {"title": "..."} dicts. When given,
            these titles REPLACE the fixed Giriş/Literatür/Yöntem/Bulgular/Tartışma/Sonuç
            structure entirely, so a thesis with a bespoke chapter plan (e.g. "Tarihsel
            Arka Plan", "Azamiye Külliyesi Yapısı", ...) can be produced.
        provided_sources: optional raw bibliography/source text supplied by the user
            (e.g. extracted PDF text via engine.pdf_sources.build_sources_from_pdfs).
            When given, it is injected into every section prompt and the references
            section is forced to use ONLY these sources instead of letting the model
            invent a bibliography.
        strict_sources_only: when True, every section prompt is instructed to use
            ONLY the material in provided_sources — no outside/general knowledge —
            and to explicitly say so when the sources don't cover a subtopic. Live
            search is force-disabled in this mode since mixing "only these sources"
            with live-fetched external articles would contradict the instruction.
        citation_style: "apa" (default, in-text "(Yazar, Yıl)") or "footnote" —
            when "footnote", the model is instructed to mark every citation as
            [[fn:kaynak bilgisi]], which turkish_docx_generator.py then renders
            as a REAL Word footnote (superscript number + note text at the
            bottom of the page) instead of literal bracket text. This matches
            the dipnot convention standard in İlahiyat/fıkıh theses.
        include_lists: when True (default), three YÖK-required supplementary
            pages are appended after the TOC — Kısaltmalar (LLM-generated),
            Şekiller Listesi (scanned from markdown) and Tablolar Listesi
            (scanned from markdown). Set to False to skip all three.
        qa_level: "fast" (skip QA), "standard" (Verifier + Thread + Skeptic),
            or "deep" (all 19 agents with auto-correction). Default is "fast".
        include_deep_search: when True, arXiv + OpenAlex deep search is
            performed before writing starts. Open-access PDFs are downloaded
            and their text is injected into section prompts. Adds ~1-2 minutes.
        """
        lang_config = LANG_CONFIGS.get(language, LANG_CONFIGS["tr"])
        prompts = get_prompts_for_language(language)
        language_name = lang_config["name"]

        if citation_style == "footnote":
            if language == "ar":
                citation_note = (
                    " هام جداً بخصوص التوثيق: لا تستخدم أسلوب APA داخل النص مثل (المؤلف، السنة). "
                    "بدلاً من ذلك، ضع علامة الحاشية بالضبط بهذا الشكل مباشرة بعد كل معلومة تحتاج توثيقاً: "
                    "[[fn:معلومات المصدر الكاملة]]. مثال: '...كما ورد في الروايات[[fn:السرخسي، المبسوط، ج3، ص45.]].' "
                    "لا تكتب أبداً (المؤلف، السنة) بين قوسين."
                )
            elif language == "en":
                citation_note = (
                    " IMPORTANT CITATION RULE: Do NOT use in-text APA style like (Author, Year). "
                    "Instead, place a footnote marker in exactly this form right after any claim that "
                    "needs a citation: [[fn:full source information]]. Example: '...as noted in the "
                    "literature[[fn:Smith, 2020, p. 45.]].' Never write (Author, Year) in parentheses."
                )
            else:
                citation_note = (
                    " ÇOK ÖNEMLİ ATIF KURALI: Metin içinde APA stili (Yazar, Yıl) formatını KULLANMA. "
                    "Bunun yerine, atıf gereken her yerde tam olarak şu formatta bir dipnot işareti koy: "
                    "[[fn:kaynağın tam bilgisi]]. Örnek: '...belirtilmiştir[[fn:es-Serahsî, el-Mebsût, "
                    "C. 3, s. 45.]].' Asla parantez içinde (Yazar, Yıl) yazma."
                )
            lang_config = dict(lang_config)
            lang_config["system_instruction"] = lang_config["system_instruction"] + citation_note

        # Kaynak kontrolu: manuel metin VEYA klasordeki PDF'ler yeterlidir
        has_text_source = bool(provided_sources and provided_sources.strip())
        has_pdf_source  = bool(pdf_paths and len(pdf_paths) > 0)
        if strict_sources_only and not has_text_source and not has_pdf_source:
            logger.warning(
                "strict_sources_only=True ancak ne kaynak metni ne de PDF dosyasi var! "
                "Halusinasyon riskini onlemek icin islem durduruluyor."
            )
            raise ValueError(
                "\u274c Strict RAG modu aktif ancak hi\u00e7bir kaynak sa\u011flanmad\u0131. "
                "Mod 1 ile PDF indirin veya 'Kendi Kayna\u011f\u0131n\u0131z' alan\u0131na kaynak girin."
            )

        if strict_sources_only and use_live_search:
            logger.info("strict_sources_only aktif: use_live_search devre dışı bırakıldı (çelişkiyi önlemek için).")
            use_live_search = False

        sections_output = {}
        full_markdown_parts = []

        from engine.job_tracker import update_job_status, is_job_cancelled, reset_cancel_flag
        reset_cancel_flag()
        update_job_status(status="running", step="Akademik Yazım Başlatılıyor", progress=0.01, topic=topic, mode="Mod 1")

        def report(pct: float, stage: str, detail: str = ""):
            if is_job_cancelled():
                raise RuntimeError("İşlem kullanıcı tarafından iptal edildi.")
            update_job_status(status="running", step=f"{stage} - {detail}", progress=pct/100.0, topic=topic, mode="Mod 1")
            if progress_callback:
                progress_callback(pct, stage, detail)

        def call_llm(prompt_text: str) -> str:
            try:
                return self.llm_func(prompt_text, system_prompt=lang_config["system_instruction"])
            except Exception:
                return self.llm_func(prompt_text)

        language_warnings = []

        def call_llm_clean(prompt_text: str, section_label: str = "") -> str:
            """
            Calls the LLM, sanitizes the result, and — for Turkish output —
            checks whether the model drifted into English mid-paragraph. If
            it did, asks the model once to rewrite the section fully in
            Turkish rather than silently shipping mixed-language text.
            """
            raw = call_llm(prompt_text)
            cleaned = sanitize_turkish_text(raw, language=language)
            drift = detect_language_drift(cleaned, language)
            if not drift:
                return cleaned

            logger.info(f"Dil kaymasi tespit edildi ({section_label}): {len(drift)} cumle. Duzeltme deneniyor...")
            fix_prompt = (
                "Asagidaki akademik metinde bazi cumleler yanlislikla farkli bir dilde (Ingilizce/Cince vb.) kalmis:\n\n"
                + "\n".join(f"- {d}" for d in drift[:8])
                + "\n\nTUM METNI EKSIKSIZ SEKILDE %100 TURKCE OLARAK YENIDEN YAZ. "
                "Icerik, anlam ve uzunluk ayni kalsin, sadece dili duzelt. "
                "Baslik/tablo yapisini koru. [[fn:...]] seklindeki dipnot isaretlerini "
                "ICLERINDEKI METINLE BIRLIKTE AYNEN KORU, degistirme veya cevirme. "
                "Baska hicbir not veya aciklama ekleme.\n\nMETIN:\n"
                + cleaned
            )
            try:
                fixed = call_llm(fix_prompt)
                fixed_clean = sanitize_turkish_text(fixed, language=language)
                still_drifting = detect_language_drift(fixed_clean, language)
                if still_drifting:
                    language_warnings.append(
                        f"\u26a0\ufe0f '{section_label}' bolumunde duzeltme sonrasi hala yabanci dil (Ingilizce/Cince) kalmis olabilir, elle kontrol edin."
                    )
                return fixed_clean
            except Exception as e:
                logger.warning(f"Dil kaymasi duzeltilemedi ({section_label}): {e}")
                language_warnings.append(
                    f"\u26a0\ufe0f '{section_label}' bolumunde yabanci dil tespit edildi ama otomatik duzeltme basarisiz oldu, elle kontrol edin."
                )
                return cleaned

        # Step 0: Optional Live Academic Search (CrossRef & Semantic Scholar)
        live_search_context = ""
        if use_live_search:
            report(3, "Canlı Akademik Tarama", "CrossRef ve Semantic Scholar veritabanlarında güncel makaleler taranıyor...")
            try:
                from engine.academic_search import fetch_live_academic_context
                live_search_context = fetch_live_academic_context(topic, max_items=10)
                if live_search_context:
                    report(4, "Canlı Makaleler Bulundu", "Bulunan akademik makaleler literatür ve kaynakçaya eklendi.")
                    if language == "tr":
                        live_search_context += (
                            "\n\n(NOT: Yukarıdaki makale başlıkları/özetleri İngilizce olabilir — bu normaldir, "
                            "olduğu gibi bırak. Ama SEN yazacağın tüm cümleleri, yorumları ve analizleri "
                            "KESİNLİKLE %100 TÜRKÇE yaz. Tek bir İngilizce cümle bile yazma.)"
                        )
            except Exception as e:
                logger.warning(f"Live search error: {e}")

        # Step 0.5 (optional): Derin Akademik Arama — arXiv + OpenAlex PDF
        if include_deep_search and not strict_sources_only:
            report(5, "Derin Arama", "arXiv ve OpenAlex tık taranıyor, açık erişim PDF'ler indiriliyor...")
            try:
                from engine.deep_search import fetch_deep_search_context
                from pathlib import Path as _Path
                _pdf_dir = _Path("output_drafts") / "deep_search_pdfs"
                def _ds_cb(msg: str):
                    report(6, "Derin Arama", msg[:80])
                deep_ctx = fetch_deep_search_context(
                    topic=topic,
                    language=language,
                    max_results=10,
                    download_pdfs=True,
                    pdf_dir=_pdf_dir,
                    report_callback=_ds_cb,
                )
                if deep_ctx:
                    live_search_context = (live_search_context + "\n\n" + deep_ctx).strip()
                    report(7, "Derin Arama Tamamlandı",
                           f"{len(deep_ctx)} karakter ek bağlam oluşturuldu")
                    logger.info(f"Derin arama bağlamı: {len(deep_ctx)} karakter")
            except Exception as e:
                logger.warning(f"Derin arama hatası (devam ediliyor): {e}")


        # Sources block: injected into section prompts and used to force a
        # non-hallucinated references list when the user supplies their own
        # bibliography/documents (e.g. classical fıkıh sources or uploaded PDFs
        # not indexed by CrossRef).
        sources_block = ""
        if provided_sources and provided_sources.strip():
            if strict_sources_only:
                if language == "ar":
                    sources_block = (
                        "\n\nمصادر إلزامية (استخدم هذه المصادر فقط ولا شيء غيرها. "
                        "ممنوع منعاً باتاً استخدام أي معلومة من معرفتك العامة أو من الإنترنت. "
                        "إذا لم تغطِ هذه المصادر جزئية معينة، صرّح بذلك صراحة بدلاً من الاختلاق):\n"
                        f"{provided_sources.strip()}\n"
                    )
                elif language == "en":
                    sources_block = (
                        "\n\nMANDATORY SOURCES (use ONLY the material below — no outside "
                        "or general knowledge, no invented facts. If these sources do not "
                        "cover a subtopic, explicitly say so instead of fabricating content):\n"
                        f"{provided_sources.strip()}\n"
                    )
                else:
                    sources_block = (
                        "\n\nZORUNLU KAYNAKLAR (SADECE aşağıdaki materyali kullan — genel "
                        "bilgi, internetten hatırladığın bilgi veya tahmin KULLANMA. Bu "
                        "kaynaklar bir alt konuyu kapsamıyorsa, uydurmak yerine bunu açıkça "
                        "belirt):\n"
                        f"{provided_sources.strip()}\n"
                    )
            else:
                if language == "ar":
                    sources_block = f"\n\nالمصادر المرجعية المتاحة (استرشد بها، ولا تخترع مصادر أخرى):\n{provided_sources.strip()}\n"
                elif language == "en":
                    sources_block = f"\n\nAVAILABLE REFERENCE SOURCES (ground your writing in these; do not invent others):\n{provided_sources.strip()}\n"
                else:
                    sources_block = f"\n\nKULLANILABİLİR KAYNAKLAR (bunlara dayanarak yaz, başka kaynak uydurma):\n{provided_sources.strip()}\n"

        # Build RAG Index — prefer indexing the FULL original PDF text (via
        # pdf_paths) so relevant-passage retrieval draws from complete
        # documents rather than the already-capped provided_sources string
        # (which stays bounded on purpose, since it's injected directly into
        # every prompt without RAG filtering).
        rag_index = None
        if use_advanced_rag and pdf_paths:
            try:
                from engine.rag_engine import build_rag_index_from_pdfs
                rag_index = build_rag_index_from_pdfs(pdf_paths, max_chars_per_pdf=None)
                logger.info(f"RAG indeksi (tam PDF metninden) başarıyla hazırlandı: {len(rag_index.chunks)} pasaj.")
            except Exception as rag_err:
                logger.warning(f"RAG indeksi (PDF'lerden) oluşturulamadı: {rag_err}")
                language_warnings.append(
                    f"⚠️ 'Gelişmiş RAG' açıktı ama kurulamadı ({rag_err}) — PDF'ler yalnızca kısaltılmış "
                    "özet olarak kullanıldı, tam metin taraması yapılamadı. 'pip install chromadb' ile "
                    "kurabilirsiniz."
                )
                rag_index = None
        elif not use_advanced_rag and pdf_paths:
            logger.info("Gelişmiş RAG kapalı, PDF'ler sadece özet olarak kullanılacak.")

        if rag_index is None and provided_sources:
            try:
                from engine.rag_engine import LocalRAGIndex
                rag_index = LocalRAGIndex()
                source_blocks = provided_sources.split("--- KAYNAK BELGE METNİ ")
                for sb in source_blocks:
                    if not sb.strip():
                        continue
                    m_fn = re.match(r'^\[(.*?)\] ---\n(.*)', sb, re.DOTALL)
                    if m_fn:
                        fn_name, fn_text = m_fn.group(1), m_fn.group(2)
                        rag_index.add_document(fn_name, fn_text)
                    else:
                        rag_index.add_document("Genel Kaynak", sb)
                logger.info(f"RAG indeksi (metin kaynağından, PDF yolu verilmedi) hazırlandı: {len(rag_index.chunks)} pasaj.")
            except Exception as rag_err:
                logger.warning(f"RAG indeksi oluşturulamadı: {rag_err}")

        def _enrich_with_rag(sec_label: str, p_text: str) -> str:
            if not rag_index or not rag_index.chunks:
                return p_text
            rag_ctx = rag_index.format_retrieved_context(f"{topic} {sec_label}", top_k=10, max_chars=35000)
            if rag_ctx:
                # Promptun en sonuna RAG ekleniyor. RAG icerigi Arapca/Ingilizce vs. olacagi icin
                # LLM cogu zaman "Language Drift" yasayip Cince veya kendi diline donebilir.
                # Bunu engellemek icin RAG bitiminde DIL uyarisini siddetle tekrar etmeliyiz.
                return p_text + (
                    f"\n\n--- BU BOLUM ICIN AKILLI RAG ILE CEKILEN EN ILGILI PASAJLAR ---\n"
                    f"{rag_ctx}\n\n"
                    f"DIKKAT VE ONEMLI HATIRLATMA: Yukaridaki RAG pasajlari farkli dillerde (Arapca, Ingilizce vb.) olabilir. "
                    f"Ancak sen KESINLIKLE %100 TURKCE yazmak zorundasin! Yabanci dildeki metni (ornegin Cince, Arapca, Ingilizce) "
                    f"asla kopyalama, sadece anla ve sentezleyerek TURKCE akademik bir dille anlat. Yabanci dilde hicbir cumle/kelime uretme."
                )
            return p_text

        def _apply_phase2(section_text: str, section_label: str, target_word_count: int) -> str:
            """Apply Phase 2 QA agents (StyleEnforcer + DepthAnalyzer) to a section if deep mode."""
            if qa_level != "deep":
                return section_text
            try:
                from engine.qa_agents import run_style_enforcer, run_depth_analyzer
                # Style check & fix
                style_result = run_style_enforcer(
                    section_text=section_text,
                    section_label=section_label,
                    language=language,
                    llm_func=self.llm_func,
                    system_instruction=lang_config.get("system_instruction", ""),
                )
                corrected = style_result.get("corrected_text", section_text)
                if style_result.get("issues_count", 0) > 0:
                    logger.info(f"StyleEnforcer ({section_label}): {style_result['issues_count']} düzeltme yapıldı.")
                
                # Depth check
                depth_result = run_depth_analyzer(
                    section_text=corrected,
                    section_label=section_label,
                    target_words=target_word_count,
                    language=language,
                    llm_func=self.llm_func,
                    system_instruction=lang_config.get("system_instruction", ""),
                )
                if depth_result.get("needs_rewrite") and depth_result.get("expanded_text"):
                    corrected = depth_result["expanded_text"]
                    logger.info(f"DepthAnalyzer ({section_label}): Bölüm genişletildi (skor: {depth_result.get('depth_score', '?')}).")
                
                return corrected
            except Exception as e:
                logger.warning(f"Faz 2 QA hatası ({section_label}): {e}")
                return section_text

        report(5, "Anahat Oluşturuluyor", f"Akademik tez planı ({language_name}) oluşturuluyor...")
        if custom_sections:
            section_titles_list = "\n".join(f"{i+1}. {s['title']}" for i, s in enumerate(custom_sections))
            outline_prompt = prompts["custom_outline"].format(
                topic=topic,
                academic_level=academic_level,
                target_words=target_words,
                section_titles=section_titles_list
            )
        else:
            outline_prompt = prompts["outline"].format(
                topic=topic,
                academic_level=academic_level,
                target_words=target_words,
                language_name=language_name
            )
        if live_search_context:
            outline_prompt += f"\n\nLİTERATÜR VE MAKALELER / LITERATURE:\n{live_search_context}"
        if sources_block:
            outline_prompt += sources_block

        phase1_report = {}
        outline = call_llm_clean(outline_prompt, section_label="Anahat")
        sections_output["outline"] = outline

        # Phase 1 QA: Topic Analysis & Outline Critique (deep mode only)
        if qa_level == "deep":
            report(8, "Faz 1 QA", "Konu analizi ve taslak eleştirisi yapılıyor...")
            try:
                from engine.qa_agents import run_phase1_agents
                rag_ctx = ""
                if rag_index and rag_index.chunks:
                    rag_ctx = rag_index.format_retrieved_context(topic, top_k=10, max_chars=20000)
                phase1_report = run_phase1_agents(
                    topic=topic,
                    outline=outline,
                    language=language,
                    llm_func=self.llm_func,
                    rag_context=rag_ctx,
                    system_instruction=lang_config.get("system_instruction", ""),
                    report_callback=lambda msg: report(9, "Faz 1 QA", msg),
                )
                # If outline critic suggested improvements, use the improved outline
                improved = phase1_report.get("outline_critic", {}).get("improved_outline", "")
                if improved and len(improved) > len(outline) * 0.5:
                    logger.info("Outline critic tarafından iyileştirilmiş taslak kullanılıyor.")
                    outline = improved
                    sections_output["outline"] = outline
                    sections_output["outline_original"] = sections_output.get("outline", "")
                report(10, "Faz 1 QA Tamamlandı", "Konu analizi ve taslak eleştirisi tamamlandı.")
            except Exception as e:
                logger.warning(f"Faz 1 QA hatası (devam ediliyor): {e}")

        # Step 2: Generate Abstract (Özet)
        report(15, "Özet Hazırlanıyor", f"{language_name} Özet metni hazırlanıyor...")
        abstract_prompt = prompts["abstract"].format(
            topic=topic,
            academic_level=academic_level
        )
        abstract_text = call_llm_clean(abstract_prompt, section_label="Özet")
        sections_output["abstract"] = abstract_text
        full_markdown_parts.append(abstract_text)

        # Step 2.5: Generate English Abstract if requested
        if include_english_abstract and language != "en":
            report(18, "English Abstract Hazırlanıyor", "İngilizce Abstract (Özet) metni hazırlanıyor...")
            eng_abstract_prompt = prompts.get("english_abstract", "").format(
                topic=topic,
                academic_level=academic_level
            )
            if eng_abstract_prompt:
                raw_eng_abstract = call_llm(eng_abstract_prompt)
                sections_output["english_abstract"] = raw_eng_abstract
                full_markdown_parts.append(raw_eng_abstract)

        if custom_sections:
            # --- Custom chapter plan pipeline ---
            n = len(custom_sections)
            base_pct = 20
            pct_span = 68  # progress goes from ~20% to ~88% across custom chapters
            for idx, sec in enumerate(custom_sections):
                sec_title = sec["title"]
                sec_key = sec.get("key") or f"section_{idx+1}"
                word_count = max(100, int(target_words / n))
                pct = base_pct + int(pct_span * (idx + 1) / n)
                report(pct, f"{idx+1}. Bölüm: {sec_title} Yazılıyor", f"{sec_title} ({language_name}) kaleme alınıyor...")
                p_custom = prompts["custom_section"].format(
                    section_title=sec_title,
                    topic=topic,
                    academic_level=academic_level,
                    word_count=word_count,
                    outline=outline,
                    sources_block=sources_block
                )
                if live_search_context:
                    p_custom += f"\n\nLİTERATÜR VE MAKALELER:\n{live_search_context}"
                p_custom = _enrich_with_rag(sec_title, p_custom)
                sec_text = call_llm_clean(p_custom, section_label=sec_title)
                sec_text = _apply_phase2(sec_text, sec_title, word_count)
                sections_output[sec_key] = sec_text
                full_markdown_parts.append(sec_text)
        else:
            # --- Fixed Giriş/Literatür/Yöntem/Bulgular/Tartışma/Sonuç pipeline ---
            word_allocations = {
                "introduction": max(75, int(target_words * 0.15)),
                "literature_review": max(150, int(target_words * 0.30)),
                "methodology": max(75, int(target_words * 0.15)),
                "results": max(100, int(target_words * 0.20)),
                "discussion": max(50, int(target_words * 0.10)),
                "conclusion": max(50, int(target_words * 0.10)),
            }

            # Step 3: Section 1 - Introduction
            report(25, "1. Bölüm: Giriş Yazılıyor", f"Giriş bölümü ({language_name}) kaleme alınıyor...")
            p_intro = prompts["introduction"].format(
                topic=topic,
                academic_level=academic_level,
                word_count=word_allocations["introduction"],
                outline=outline
            )
            if sources_block:
                p_intro += sources_block
            p_intro = _enrich_with_rag("Giriş", p_intro)
            sec_intro = call_llm_clean(p_intro, section_label="Giriş")
            sec_intro = _apply_phase2(sec_intro, "Giriş", word_allocations["introduction"])
            sections_output["introduction"] = sec_intro
            full_markdown_parts.append(sec_intro)

            # Step 4: Section 2 - Literature Review
            report(40, "2. Bölüm: Literatür Taraması Yazılıyor", f"Literatür Taraması ({language_name}) oluşturuluyor...")
            p_lit = prompts["literature_review"].format(
                topic=topic,
                academic_level=academic_level,
                word_count=word_allocations["literature_review"],
                outline=outline
            )
            if live_search_context:
                p_lit += f"\n\nLİTERATÜR VE MAKALELER:\n{live_search_context}"
            if sources_block:
                p_lit += sources_block
            p_lit = _enrich_with_rag("Literatür Taraması", p_lit)

            sec_lit = call_llm_clean(p_lit, section_label="Literatür Taraması")
            sec_lit = _apply_phase2(sec_lit, "Literatür Taraması", word_allocations["literature_review"])
            sections_output["literature_review"] = sec_lit
            full_markdown_parts.append(sec_lit)

            # Step 5: Section 3 - Methodology
            report(55, "3. Bölüm: Yöntem Yazılıyor", f"Yöntem bölümü ({language_name}) belirleniyor...")
            p_meth = prompts["methodology"].format(
                topic=topic,
                academic_level=academic_level,
                word_count=word_allocations["methodology"],
                outline=outline
            )
            if sources_block:
                p_meth += sources_block
            p_meth = _enrich_with_rag("Yöntem", p_meth)
            sec_meth = call_llm_clean(p_meth, section_label="Yöntem")
            sec_meth = _apply_phase2(sec_meth, "Yöntem", word_allocations["methodology"])
            sections_output["methodology"] = sec_meth
            full_markdown_parts.append(sec_meth)

            # Step 6: Section 4 - Results
            report(70, "4. Bölüm: Bulgular ve Analiz Yazılıyor", f"Bulgular bölümü ({language_name}) üretiliyor...")
            p_res = prompts["results"].format(
                topic=topic,
                academic_level=academic_level,
                word_count=word_allocations["results"],
                outline=outline
            )
            if sources_block:
                p_res += sources_block
            p_res = _enrich_with_rag("Bulgular ve Analiz", p_res)
            sec_res = call_llm_clean(p_res, section_label="Bulgular")
            sec_res = _apply_phase2(sec_res, "Bulgular", word_allocations["results"])
            sections_output["results"] = sec_res
            full_markdown_parts.append(sec_res)

            # Step 7: Section 5 - Discussion
            report(80, "5. Bölüm: Tartışma Yazılıyor", f"Tartışma bölümü ({language_name}) yazılıyor...")
            p_disc = prompts["discussion"].format(
                topic=topic,
                academic_level=academic_level,
                word_count=word_allocations["discussion"],
                outline=outline
            )
            if sources_block:
                p_disc += sources_block
            p_disc = _enrich_with_rag("Tartışma", p_disc)
            sec_disc = call_llm_clean(p_disc, section_label="Tartışma")
            sec_disc = _apply_phase2(sec_disc, "Tartışma", word_allocations["discussion"])
            sections_output["discussion"] = sec_disc
            full_markdown_parts.append(sec_disc)

            # Step 8: Section 6 - Conclusion
            report(88, "6. Bölüm: Sonuç ve Öneriler Yazılıyor", f"Sonuç bölümü ({language_name}) kaleme alınıyor...")
            p_conc = prompts["conclusion"].format(
                topic=topic,
                academic_level=academic_level,
                word_count=word_allocations["conclusion"],
                outline=outline
            )
            if sources_block:
                p_conc += sources_block
            p_conc = _enrich_with_rag("Sonuç ve Öneriler", p_conc)
            sec_conc = call_llm_clean(p_conc, section_label="Sonuç")
            sec_conc = _apply_phase2(sec_conc, "Sonuç", word_allocations["conclusion"])
            sections_output["conclusion"] = sec_conc
            full_markdown_parts.append(sec_conc)

        # Step 9: References (Kaynakça)
        report(93, "Kaynakça Derleniyor", f"Akademik kaynakça ({language_name}) hazırlanıyor...")
        if provided_sources and provided_sources.strip():
            # Force the model to compile the bibliography ONLY from the user's
            # own source list, instead of letting it invent citations.
            p_ref = prompts["references_strict"].format(
                topic=topic,
                sources_block=provided_sources.strip()
            )
        else:
            p_ref = prompts["references"].format(
                topic=topic,
                topic_summary=f"{topic} akademik çalışma"
            )
            if live_search_context:
                p_ref += f"\n\nLİTERATÜR VE DOİ NUMARALARI:\n{live_search_context}"

        sec_ref = call_llm_clean(p_ref, section_label="Kaynakça")
        sections_output["references"] = sec_ref
        full_markdown_parts.append(sec_ref)

        # Merge Full Markdown
        full_markdown_text = "\n\n---\n\n".join(full_markdown_parts)

        # Step 9.4: QA Agents — 3 levels: fast (skip), standard (3 agents), deep (19 agents)
        qa_report = {}
        if qa_level == "standard":
            report(92, "QA Analizi (Standart)", "Verifier, Thread ve Skeptic ajanları çalışıyor...")
            try:
                from engine.qa_agents import run_all_qa
                def _qa_cb(msg: str):
                    report(92, "QA Analizi", msg)
                qa_report = run_all_qa(
                    full_markdown=full_markdown_text,
                    topic=topic,
                    language=language,
                    llm_func=self.llm_func,
                    system_instruction=lang_config.get("system_instruction", ""),
                    report_callback=_qa_cb,
                )
                logger.info("QA ajanları (standart) tamamlandı")
            except Exception as e:
                logger.warning(f"QA ajan hatası (devam ediliyor): {e}")
                qa_report = {}

        elif qa_level == "deep":
            report(90, "QA Analizi (Derin — 19 Ajan)", "Tüm QA ajanları paralel çalışıyor...")
            try:
                from engine.qa_agents import run_all_qa_deep
                def _qa_deep_cb(msg: str):
                    report(91, "Derin QA", msg)
                deep_result = run_all_qa_deep(
                    full_markdown=full_markdown_text,
                    topic=topic,
                    language=language,
                    llm_func=self.llm_func,
                    system_instruction=lang_config.get("system_instruction", ""),
                    report_callback=_qa_deep_cb,
                )
                # Apply Phase 4 corrections (ReadabilityOptimizer + FinalProofreader)
                final_text = deep_result.get("phase4", {}).get("final_text", "")
                if final_text and len(final_text) > len(full_markdown_text) * 0.5:
                    full_markdown_text = final_text
                    logger.info("Faz 4 düzeltmeleri uygulandı (ReadabilityOptimizer + FinalProofreader).")
                
                # Build qa_report compatible with existing quality_dict structure
                phase3 = deep_result.get("phase3", {})
                qa_report = {
                    "verifier": phase3.get("verifier", {}),
                    "thread_report": phase3.get("thread_report", ""),
                    "skeptic_report": phase3.get("skeptic_report", ""),
                    "combined_md": deep_result.get("combined_md", ""),
                    # Extended agent reports (keys match run_phase3_agents output)
                    "transition_report": phase3.get("transition_report", ""),
                    "citation_balance_report": phase3.get("citation_report", ""),
                    "argument_map_report": phase3.get("argument_report", ""),
                    "methodology_audit_report": phase3.get("methodology_report", ""),
                    "abstract_validation_report": phase3.get("abstract_report", ""),
                    "terminology_report": phase3.get("terminology_report", ""),
                    "statistics_report": phase3.get("statistics_report", ""),
                    "readability_report": deep_result.get("phase4", {}).get("readability_report", ""),
                    "proofreader_report": deep_result.get("phase4", {}).get("proofreader_report", ""),
                    "phase1_report": phase1_report,
                }
                logger.info("Derin QA analizi (19 ajan) tamamlandı")
            except Exception as e:
                logger.warning(f"Derin QA hatası (devam ediliyor): {e}")
                qa_report = {}

        # Step 9.5 (pre-export): Scan figures/tables; generate abbreviations
        abbr_list = None
        figures = None
        tables = None
        if include_lists:
            report(93.5, "Liste Sayfaları Hazırlanıyor", "Kısaltmalar, Şekiller ve Tablolar listeleniyor...")
            try:
                from engine.figure_table_scanner import scan_figures, scan_tables
                figures = scan_figures(full_markdown_text)
                tables = scan_tables(full_markdown_text)
                logger.info(f"Şekil sayısı: {len(figures)}, Tablo sayısı: {len(tables)}")
            except Exception as e:
                logger.warning(f"Figure/table tarama hatası: {e}")
                figures = []
                tables = []

            try:
                from engine.abbreviations import extract_abbreviations_via_llm
                abbr_list = extract_abbreviations_via_llm(
                    topic=topic,
                    full_markdown=full_markdown_text,
                    language=language,
                    llm_func=self.llm_func,
                    system_instruction=lang_config.get("system_instruction", "")
                )
            except Exception as e:
                logger.warning(f"Kısaltma çıkarım hatası: {e}")
                abbr_list = []

        # Step 9.5: Quality Score
        report(94, "Kalite Kontrolü", "Belge otomatik olarak puanlanıyor...")
        from engine.quality_gate import calculate_quality_score
        quality = calculate_quality_score(full_markdown_text, target_words, language_warnings)
        quality_dict = {
            "overall_score": quality.overall_score,
            "word_count_score": quality.word_count_score,
            "structure_score": quality.structure_score,
            "citation_score": quality.citation_score,
            "repetition_score": quality.repetition_score,
            "language_score": quality.language_score,
            "formatting_score": quality.formatting_score,
            "suggestions": quality.suggestions,
            "stats": quality.stats,
            # QA agent reports (standard + deep)
            "qa_verifier": qa_report.get("verifier", {}),
            "qa_thread": qa_report.get("thread_report", ""),
            "qa_skeptic": qa_report.get("skeptic_report", ""),
            "qa_combined_md": qa_report.get("combined_md", ""),
            # Extended deep QA agent reports
            "qa_transition": qa_report.get("transition_report", ""),
            "qa_citation_balance": qa_report.get("citation_balance_report", ""),
            "qa_argument_map": qa_report.get("argument_map_report", ""),
            "qa_methodology_audit": qa_report.get("methodology_audit_report", ""),
            "qa_abstract_validation": qa_report.get("abstract_validation_report", ""),
            "qa_terminology": qa_report.get("terminology_report", ""),
            "qa_statistics": qa_report.get("statistics_report", ""),
            "qa_readability": qa_report.get("readability_report", ""),
            "qa_proofreader": qa_report.get("proofreader_report", ""),
            "qa_phase1": qa_report.get("phase1_report", {}),
            "qa_level": qa_level,
        }

        # Step 10: Export to Word (.docx) and Markdown (.md)
        output_dir = Path("output_drafts")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r'[^\w\s-]', '', topic[:20]).strip().replace(' ', '_')
        
        docx_filename = f"VeFa_Tez_{safe_topic}_{timestamp}.docx"
        md_filename = f"VeFa_Tez_{safe_topic}_{timestamp}.md"

        docx_path = str(output_dir / docx_filename)
        md_path = str(output_dir / md_filename)

        # Save MD
        with open(md_path, "w", encoding="utf-8-sig") as f:
            f.write(full_markdown_text)

        # Save DOCX
        metadata = {
            "title": topic,
            "author": author,
            "advisor": advisor,
            "institution": institution,
            "faculty": faculty,
            "academic_level": academic_level,
            "year": datetime.now().year,
            "city": city,
            "language": language
        }
        generate_turkish_academic_docx(
            full_markdown_text,
            docx_path,
            metadata=metadata,
            include_cover_page=include_cover_page,
            abbr_list=abbr_list,
            figures=figures,
            tables=tables,
        )

        report(100, "Tamamlandı", "Akademik tez ve Word belgesi başarıyla hazırlandı.")

        update_job_status(
            status="completed",
            step="Tamamlandı",
            progress=1.0,
            topic=topic,
            mode="Mod 1",
            docx_path=docx_path,
            md_path=md_path,
            language_warnings=language_warnings,
            quality_score=quality_dict
        )

        return {
            "docx_path": docx_path,
            "md_path": md_path,
            "sections": sections_output,
            "full_markdown": full_markdown_text,
            "language_warnings": language_warnings,
            "quality_score": quality_dict
        }
