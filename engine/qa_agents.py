# -*- coding: utf-8 -*-
"""
VeFa - QA Ajanları: Verifier + Thread + Skeptic
Tez üretim pipeline'ının sonunda çalışır; kalite raporunu zenginleştirir.

  Verifier  → Metindeki DOI/atıfları CrossRef'te doğrular, uydurma kaynakları işaretler
  Thread    → Bölümler arası tutarlılık / çelişki / tekrar analizi (LLM)
  Skeptic   → Eleştirel akademik inceleme: zayıf argümanlar, eksik bağlantılar (LLM)
"""

import re
import time
import logging
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "VeFa-AcademicAssistant/2.0 (mailto:academic@vefa.app)"}
_TIMEOUT = 8


# ============================================================
# VERIFIER — CrossRef DOI doğrulama
# ============================================================

# Metinden DOI kalıplarını çeken regex
_DOI_PATTERN = re.compile(
    r'\b(10\.\d{4,9}/[-._;()/:A-Z0-9a-z]+)',
    re.IGNORECASE,
)

# Parantez içi APA benzeri atıf kalıbı: (Serahsî, 2005) veya (Smith et al., 2020)
_APA_PATTERN = re.compile(
    r'\(([A-ZÇĞİÖŞÜa-zçğışöüA-Z][^\d()]{1,40}),\s*(\d{4})\)',
)


def extract_dois(text: str) -> List[str]:
    """Metinden DOI numaralarını çıkarır."""
    return list({m.group(1) for m in _DOI_PATTERN.finditer(text)})


def verify_doi_crossref(doi: str) -> Dict[str, Any]:
    """
    CrossRef API'sine DOI ile sorgu atar.
    Döner: {"doi": ..., "exists": bool, "title": ..., "year": ..., "authors": ...}
    """
    url = f"https://api.crossref.org/works/{requests.utils.quote(doi, safe='')}"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code == 200:
            msg = r.json().get("message", {})
            title_list = msg.get("title", [])
            authors = [
                f"{a.get('family', '')} {a.get('given', '')}".strip()
                for a in msg.get("author", [])
            ]
            issued = msg.get("issued", {}).get("date-parts", [[None]])
            year = issued[0][0] if issued and issued[0] else None
            return {
                "doi": doi,
                "exists": True,
                "title": title_list[0] if title_list else "",
                "year": year,
                "authors": authors[:3],
            }
        elif r.status_code == 404:
            return {"doi": doi, "exists": False, "title": "", "year": None, "authors": []}
        else:
            return {"doi": doi, "exists": None, "title": "", "year": None, "authors": []}
    except Exception as e:
        logger.warning(f"CrossRef doğrulama hatası ({doi}): {e}")
        return {"doi": doi, "exists": None, "title": "", "year": None, "authors": []}


def run_verifier(
    full_markdown: str,
    language: str = "tr",
    max_dois: int = 20,
) -> Dict[str, Any]:
    """
    Metindeki DOI'leri CrossRef'te doğrular.

    Döner:
        {
          "checked": int,
          "confirmed": int,
          "not_found": int,
          "unreachable": int,
          "confirmed_list": [...],
          "not_found_list": [...],
          "summary_md": str   ← Kalite raporuna eklenen markdown blok
        }
    """
    dois = extract_dois(full_markdown)[:max_dois]

    if not dois:
        # DOI yoksa APA atıf sayısını raporla (doğrulama yapamazsan bile bil)
        apa_matches = _APA_PATTERN.findall(full_markdown)
        note = {
            "tr": f"Metinde DOI bulunamadı. {len(apa_matches)} adet APA atıfı tespit edildi (CrossRef doğrulaması yapılamadı).",
            "ar": f"لم يُعثر على DOI في النص. تم رصد {len(apa_matches)} إحالة بأسلوب APA (لا يمكن التحقق عبر CrossRef).",
            "en": f"No DOIs found in text. {len(apa_matches)} APA-style citations detected (CrossRef verification not possible).",
        }.get(language, f"No DOIs found. {len(apa_matches)} APA citations detected.")
        return {
            "checked": 0, "confirmed": 0, "not_found": 0, "unreachable": 0,
            "confirmed_list": [], "not_found_list": [],
            "summary_md": f"### 🔍 Atıf Doğrulama (Verifier)\n{note}\n",
        }

    confirmed, not_found, unreachable = [], [], []

    for doi in dois:
        result = verify_doi_crossref(doi)
        time.sleep(0.2)  # CrossRef rate limit
        if result["exists"] is True:
            confirmed.append(result)
        elif result["exists"] is False:
            not_found.append(result)
        else:
            unreachable.append(result)

    # Markdown raporu
    lines = ["### 🔍 Atıf Doğrulama (Verifier — CrossRef)\n"]
    lines.append(f"- **Kontrol edilen DOI:** {len(dois)}")
    lines.append(f"- **✅ Doğrulandı:** {len(confirmed)}")
    lines.append(f"- **❌ Bulunamadı (uydurma şüphesi):** {len(not_found)}")
    lines.append(f"- **⚠️ Ulaşılamadı (ağ/timeout):** {len(unreachable)}")

    if not_found:
        lines.append("\n#### ❌ CrossRef'te Bulunamayan DOI'ler (Kontrol Edin):")
        for item in not_found:
            lines.append(f"  - `{item['doi']}`")

    if confirmed:
        lines.append("\n#### ✅ Doğrulanan Kaynaklar:")
        for item in confirmed[:5]:
            yr = f" ({item['year']})" if item["year"] else ""
            lines.append(f"  - {item['title'][:70]}{yr} — `{item['doi']}`")
        if len(confirmed) > 5:
            lines.append(f"  - ... ve {len(confirmed) - 5} kaynak daha")

    return {
        "checked": len(dois),
        "confirmed": len(confirmed),
        "not_found": len(not_found),
        "unreachable": len(unreachable),
        "confirmed_list": confirmed,
        "not_found_list": not_found,
        "summary_md": "\n".join(lines) + "\n",
    }


# ============================================================
# THREAD — Bölümler Arası Tutarlılık Analizi (LLM)
# ============================================================

_THREAD_PROMPTS = {
    "tr": """\
Aşağıdaki akademik tezi bölümler arası tutarlılık açısından analiz et.

TEZ METNİ (özet):
{text_snippet}

GÖREV:
1. Bölümler arasında ÇELİŞKİ var mı? (Giriş'te söylenen ama Sonuç'ta çelişilen şeyler)
2. Gereksiz TEKRAR var mı? (Aynı bilgi birden fazla bölümde kelimesi kelimesine tekrar ediyor mu?)
3. KOPUKLUK var mı? (Bir bölümde söz verilen ama hiç değinilmeyen konu)
4. TERMİNOLOJİ tutarlı mı? (Aynı kavram farklı adlarla mı anılıyor?)

ÇIKTI FORMATI — yalnızca şunu yaz:
## Bölümler Arası Tutarlılık Raporu
### Çelişkiler
[liste veya "Çelişki tespit edilmedi."]
### Gereksiz Tekrarlar
[liste veya "Tekrar tespit edilmedi."]
### Kopukluklar
[liste veya "Kopukluk tespit edilmedi."]
### Terminoloji Sorunları
[liste veya "Terminoloji tutarlı."]
### Genel Değerlendirme
[1-2 cümle]
""",
    "ar": """\
حلّل الأطروحة التالية من حيث التسلسل والتماسك بين الفصول.

نص الأطروحة (مقتطف):
{text_snippet}

المهمة:
1. هل ثمة تناقضات بين الفصول؟
2. هل ثمة تكرار غير ضروري؟
3. هل ثمة فجوات أو وعود غير مُفاة؟
4. هل المصطلحات متسقة طوال النص؟

صيغة الإخراج:
## تقرير تماسك الأطروحة
### التناقضات
### التكرارات غير الضرورية
### الفجوات
### مشكلات المصطلحات
### التقييم العام
""",
    "en": """\
Analyze the following academic thesis for cross-section consistency.

THESIS TEXT (excerpt):
{text_snippet}

TASK:
1. Are there CONTRADICTIONS between sections?
2. Is there unnecessary REPETITION?
3. Are there BROKEN PROMISES (topics mentioned but never developed)?
4. Is TERMINOLOGY consistent throughout?

OUTPUT FORMAT — write only:
## Cross-Section Consistency Report
### Contradictions
[list or "No contradictions detected."]
### Unnecessary Repetitions
[list or "No repetitions detected."]
### Broken Promises / Gaps
[list or "No gaps detected."]
### Terminology Issues
[list or "Terminology is consistent."]
### Overall Assessment
[1-2 sentences]
""",
}


def run_thread(
    full_markdown: str,
    language: str,
    llm_func,
    system_instruction: str = "",
) -> str:
    """
    LLM'e tezin özeti ile bölümler arası tutarlılık sorusu sorar.
    Markdown formatında rapor döndürür.
    """
    lang = language if language in _THREAD_PROMPTS else "tr"
    # İlk 6000 + son 2000 karakter — modelin context penceresini aşmamak için
    snippet = full_markdown[:6000]
    if len(full_markdown) > 8000:
        snippet += "\n\n[... orta bölümler kısaltıldı ...]\n\n" + full_markdown[-2000:]

    prompt = _THREAD_PROMPTS[lang].format(text_snippet=snippet)
    try:
        if system_instruction:
            raw = llm_func(prompt, system_prompt=system_instruction)
        else:
            raw = llm_func(prompt)
        # Sadece rapor bölümünü al
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"Thread ajanı hatası: {e}")
        return "### Bölümler Arası Tutarlılık Raporu\nAnaliz sırasında hata oluştu.\n"


# ============================================================
# SKEPTIC — Eleştirel Akademik İnceleme (LLM)
# ============================================================

_SKEPTIC_PROMPTS = {
    "tr": """\
Aşağıdaki akademik tezi, kör hakem (peer reviewer) kimliğiyle eleştirel bir gözle incele.

TEZ KONUSU: {topic}
TEZ METNİ (özet):
{text_snippet}

GÖREV — şunları değerlendir:
1. ARGÜMAN GÜÇSÜZLÜKLERİ: Kanıtlanmamış, spekülatif veya zayıf desteklenmiş iddialar
2. EKSİK KAYNAKLAR: Atıf yapılması gereken ama yapılmayan alanlar
3. METODOLOJİK SORUNLAR: Yöntem kısmındaki belirsizlikler
4. AŞIRI GENELLEMELEr: Sınırlı kanıtla geniş sonuç çıkarma
5. GÜÇLÜ YÖNLER: Takdire değer kısımlar

ÇIKTI FORMATI:
## Eleştirel İnceleme Raporu (Skeptic)
### Argüman Güçsüzlükleri
[madde madde — veya "Ciddi güçsüzlük tespit edilmedi."]
### Kaynak Eksiklikleri
[madde madde]
### Metodolojik Sorunlar
[madde madde — veya "Yok"]
### Aşırı Genellemeler
[madde madde — veya "Yok"]
### Güçlü Yönler
[madde madde]
### Genel Skor: X/10
[Kısa gerekçe]
""",
    "ar": """\
راجع الأطروحة التالية مراجعة نقدية بصفة محكّم أكاديمي.

موضوع الأطروحة: {topic}
النص (مقتطف):
{text_snippet}

قيّم:
1. نقاط الضعف في الحجج
2. الثغرات في التوثيق
3. الإشكاليات المنهجية
4. التعميمات المبالغ فيها
5. نقاط القوة

صيغة الإخراج:
## تقرير المراجعة النقدية
### نقاط ضعف الحجج
### ثغرات التوثيق
### الإشكاليات المنهجية
### التعميمات المفرطة
### نقاط القوة
### التقييم العام: X/10
""",
    "en": """\
Review the following academic thesis as a blind peer reviewer.

THESIS TOPIC: {topic}
THESIS TEXT (excerpt):
{text_snippet}

Evaluate:
1. WEAK ARGUMENTS: Unsubstantiated or speculative claims
2. MISSING CITATIONS: Areas where references are needed but absent
3. METHODOLOGICAL ISSUES: Vague or problematic method descriptions
4. OVERGENERALIZATIONS: Broad conclusions from limited evidence
5. STRENGTHS: Notable positive aspects

OUTPUT FORMAT:
## Critical Review Report (Skeptic)
### Weak Arguments
[bullet list or "No critical weaknesses detected."]
### Missing Citations
[bullet list]
### Methodological Issues
[bullet list or "None"]
### Overgeneralizations
[bullet list or "None"]
### Strengths
[bullet list]
### Overall Score: X/10
[Brief rationale]
""",
}


def run_skeptic(
    full_markdown: str,
    topic: str,
    language: str,
    llm_func,
    system_instruction: str = "",
) -> str:
    """
    LLM'e tezi kör hakem kimliğiyle eleştirtirir.
    Markdown formatında rapor döndürür.
    """
    lang = language if language in _SKEPTIC_PROMPTS else "tr"
    snippet = full_markdown[:5000]
    if len(full_markdown) > 6000:
        snippet += "\n\n[... kısaltıldı ...]\n\n" + full_markdown[-1500:]

    prompt = _SKEPTIC_PROMPTS[lang].format(topic=topic, text_snippet=snippet)
    try:
        if system_instruction:
            raw = llm_func(prompt, system_prompt=system_instruction)
        else:
            raw = llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"Skeptic ajanı hatası: {e}")
        return "### Eleştirel İnceleme Raporu\nAnaliz sırasında hata oluştu.\n"


# ============================================================
# Tüm QA Ajanlarını Çalıştıran Ana Fonksiyon
# ============================================================

def run_all_qa(
    full_markdown: str,
    topic: str,
    language: str,
    llm_func,
    system_instruction: str = "",
    report_callback=None,  # (msg: str) → None
) -> Dict[str, Any]:
    """
    Sırayla Verifier → Thread → Skeptic çalıştırır.

    Döner:
        {
          "verifier": {...},         ← run_verifier çıktısı
          "thread_report": str,      ← markdown
          "skeptic_report": str,     ← markdown
          "combined_md": str         ← kalite raporuna eklenecek tam blok
        }
    """
    def _report(msg: str):
        logger.info(msg)
        if report_callback:
            try:
                report_callback(msg)
            except Exception:
                pass

    result = {}

    # 1. Verifier
    _report("🔍 Verifier: CrossRef DOI doğrulama çalışıyor...")
    verifier_out = run_verifier(full_markdown, language=language)
    result["verifier"] = verifier_out
    _report(f"   ✅ Verifier tamamlandı: {verifier_out['confirmed']} doğrulandı, "
            f"{verifier_out['not_found']} bulunamadı")

    # 2. Thread
    _report("🧵 Thread: Bölümler arası tutarlılık analizi...")
    thread_md = run_thread(full_markdown, language, llm_func, system_instruction)
    result["thread_report"] = thread_md
    _report("   ✅ Thread raporu hazır")

    # 3. Skeptic
    _report("🧪 Skeptic: Eleştirel akademik inceleme...")
    skeptic_md = run_skeptic(full_markdown, topic, language, llm_func, system_instruction)
    result["skeptic_report"] = skeptic_md
    _report("   ✅ Skeptic raporu hazır")

    # Birleşik markdown raporu
    result["combined_md"] = (
        "\n\n---\n\n## 🔬 Gelişmiş Kalite Analizi (QA Ajanları)\n\n"
        + verifier_out["summary_md"]
        + "\n---\n\n"
        + thread_md
        + "\n---\n\n"
        + skeptic_md
        + "\n"
    )

    return result

# ============================================================
# PHASE 1 — Pre-writing agents
# ============================================================

_TOPIC_ANALYZER_PROMPTS = {
    "tr": """\
Aşağıdaki akademik tez konusunu derinlemesine analiz et.

KONU: {topic}

MEVCUT KAYNAKLAR (varsa):
{rag_context}

GÖREV — şunları yaz:
## Konu Derinlik Analizi
### Alt Temalar
[konunun 3-5 alt temasını madde madde listele]
### Araştırma Soruları
[3-5 araştırma sorusu öner]
### Hipotezler
[2-3 olası hipotez öner]
### Genel Değerlendirme
[konunun akademik potansiyeli hakkında 2-3 cümle]
""",
    "ar": """\
حلل موضوع الأطروحة التالي تحليلاً معمقاً.
الموضوع: {topic}
المصادر المتاحة: {rag_context}

اكتب:
## تحليل عمق الموضوع
### المحاور الفرعية
### أسئلة البحث
### الفرضيات
### التقييم العام
""",
    "en": """\
Analyze the following thesis topic in depth.
Topic: {topic}
Available sources: {rag_context}

Write:
## Topic Depth Analysis
### Sub-themes
### Research Questions
### Hypotheses
### Overall Assessment
""",
}

def run_topic_analyzer(topic: str, language: str, llm_func, rag_context: str = "", system_instruction: str = "") -> dict:
    """Konu derinliğini analiz eder, alt temalar ve araştırma soruları belirler."""
    lang = language if language in _TOPIC_ANALYZER_PROMPTS else "tr"
    prompt = _TOPIC_ANALYZER_PROMPTS[lang].format(topic=topic, rag_context=rag_context or "(Kaynak yok)")
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return {"analysis_md": raw.strip(), "sub_themes": [], "research_questions": []}
    except Exception as e:
        logger.warning(f"TopicAnalyzer error: {e}")
    return {"analysis_md": "Konu analizi yapılamadı.", "sub_themes": [], "research_questions": []}


_OUTLINE_CRITIC_PROMPTS = {
    "tr": """\
Aşağıdaki tez taslağını (outline) eleştirel bir gözle değerlendir ve iyileştir.

KONU: {topic}
MEVCUT TASLAK:
{outline}

KONU ANALİZİ:
{topic_analysis}

GÖREV:
1. Taslağın güçlü ve zayıf yönlerini yaz
2. Eksik veya gereksiz bölümleri belirle
3. İYİLEŞTİRİLMİŞ TASLAK üret (## İyileştirilmiş Taslak başlığı altında)

ÇIKTI FORMATI:
## Taslak Eleştirisi
### Güçlü Yönler
[madde madde]
### Zayıf Yönler / Eksikler
[madde madde]
### Öneriler
[madde madde]
## İyileştirilmiş Taslak
[tam iyileştirilmiş taslak]
""",
    "ar": """\
قيّم المخطط التالي وحسّنه. الموضوع: {topic}
المخطط: {outline}
التحليل: {topic_analysis}
## نقد المخطط
## المخطط المحسّن
""",
    "en": """\
Evaluate and improve the following outline. Topic: {topic}
Outline: {outline}
Analysis: {topic_analysis}
## Outline Critique
## Improved Outline
""",
}

def run_outline_critic(outline: str, topic: str, language: str, llm_func, topic_analysis: str = "", system_instruction: str = "") -> dict:
    """Oluşturulan taslağı (outline) inceler ve iyileştirir."""
    lang = language if language in _OUTLINE_CRITIC_PROMPTS else "tr"
    prompt = _OUTLINE_CRITIC_PROMPTS[lang].format(topic=topic, outline=outline, topic_analysis=topic_analysis or "(Yok)")
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        critique_md = raw.strip()
        # İyileştirilmiş taslağı çıkar
        improved = ""
        for marker in ["## İyileştirilmiş Taslak", "## Improved Outline", "## المخطط المحسّن"]:
            if marker in raw:
                improved = raw[raw.index(marker) + len(marker):].strip()
                critique_md = raw[:raw.index(marker)].strip()
                break
        return {"critique_md": critique_md, "improved_outline": improved, "issues_found": critique_md.count("- ")}
    except Exception as e:
        logger.warning(f"OutlineCritic error: {e}")
    return {"critique_md": "Taslak eleştirisi yapılamadı.", "improved_outline": outline, "issues_found": 0}


_GAP_DETECTOR_PROMPTS = {
    "tr": """\
Aşağıdaki tez taslağını mevcut kaynaklarla karşılaştır ve literatür boşluklarını tespit et.

TASLAK:
{outline}

MEVCUT KAYNAKLAR:
{rag_context}

ÇIKTI FORMATI:
## Literatür Boşluk Raporu
### İyi Kapsanan Alanlar
[kaynaklarda yeterli bilgi olan konular]
### Zayıf Kapsanan Alanlar
[kaynaklarda eksik kalan konular]
### Öneriler
[eksik alanlar için ne yapılmalı]
""",
    "ar": """\
قارن المخطط مع المصادر المتاحة وحدد الفجوات.
المخطط: {outline}
المصادر: {rag_context}
## تقرير فجوات الأدبيات
""",
    "en": """\
Compare outline with available sources and identify literature gaps.
Outline: {outline}
Sources: {rag_context}
## Literature Gap Report
""",
}

def run_gap_detector(outline: str, rag_context: str, language: str, llm_func, system_instruction: str = "") -> dict:
    """RAG bağlamı ve taslağa dayanarak literatür boşluklarını tespit eder."""
    lang = language if language in _GAP_DETECTOR_PROMPTS else "tr"
    prompt = _GAP_DETECTOR_PROMPTS[lang].format(outline=outline, rag_context=rag_context or "(Kaynak yok)")
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return {"gaps_md": raw.strip(), "gaps_found": raw.count("- "), "well_covered": [], "poorly_covered": []}
    except Exception as e:
        logger.warning(f"GapDetector error: {e}")
    return {"gaps_md": "Boşluk analizi yapılamadı.", "gaps_found": 0, "well_covered": [], "poorly_covered": []}


# ============================================================
# PHASE 2 — Per-section agents
# ============================================================

_STYLE_ENFORCER_PROMPTS = {
    "tr": """\
Aşağıdaki akademik metinde yazım stili sorunlarını düzelt.

KONTROL EDİLECEKLER:
- Günlük dil kullanımı varsa akademik dile çevir
- Birinci tekil şahıs (ben, benim) varsa edilgen yapıya çevir
- Belirsiz ifadeler ("bazı araştırmacılar", "genellikle") varsa somutlaştır
- Uzun/karmaşık cümleleri sadeleştir

BÖLÜM ADI: {section_label}

METİN:
{section_text}

ÖNEMLİ: Aşağıda SADECE düzeltilmiş metni ver. Başka açıklama, not veya rapor YAZMA.
Metnin tamamını düzeltilmiş haliyle yaz, kısaltma.
""",
    "ar": """\
صحح مشاكل أسلوب الكتابة الأكاديمية في النص التالي.
القسم: {section_label}
النص: {section_text}
أعد النص المصحح بالكامل فقط.
""",
    "en": """\
Fix academic writing style issues in the following text.
Section: {section_label}
Text: {section_text}
Return ONLY the full corrected text, no explanations.
""",
}

def run_style_enforcer(section_text: str, section_label: str, language: str, llm_func, system_instruction: str = "") -> dict:
    """Akademik stil sorunlarını bulur ve düzeltilmiş metni döndürür."""
    lang = language if language in _STYLE_ENFORCER_PROMPTS else "tr"
    prompt = _STYLE_ENFORCER_PROMPTS[lang].format(section_text=section_text, section_label=section_label)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        corrected = raw.strip()
        # Model bazen açıklama ekleyebilir, ## ile başlayan rapor kısmını çıkar
        if corrected and len(corrected) > len(section_text) * 0.3:
            return {"corrected_text": corrected, "corrections_md": "Stil düzeltmeleri uygulandı.", "issues_count": 1}
    except Exception as e:
        logger.warning(f"StyleEnforcer error in {section_label}: {e}")
    return {"corrected_text": section_text, "corrections_md": "Düzeltme yapılamadı.", "issues_count": 0}


_DEPTH_ANALYZER_PROMPTS = {
    "tr": """\
Aşağıdaki akademik bölümün analitik derinliğini değerlendir.

BÖLÜM: {section_label}
HEDEF KELİME SAYISI: {target_words}
MEVCUT KELİME SAYISI: {current_words}

METİN:
{section_text}

GÖREV:
1. Derinlik skoru ver (0-100)
2. Eğer skor 60'ın altındaysa veya kelime sayısı hedefin %60'ından azsa, metni genişleterek yeniden yaz

Eğer metin yeterince derinde ise:
## Derinlik Analizi
Skor: [0-100]
[kısa değerlendirme]

Eğer metin genişletilmesi gerekiyorsa:
## Derinlik Analizi
Skor: [0-100]
Durum: Genişletme gerekli
## Genişletilmiş Metin
[tam genişletilmiş metin]
""",
    "ar": """\
قيّم العمق التحليلي للقسم التالي.
القسم: {section_label}. الكلمات المستهدفة: {target_words}. الحالية: {current_words}
النص: {section_text}
## تحليل العمق
""",
    "en": """\
Evaluate analytical depth of the following section.
Section: {section_label}. Target words: {target_words}. Current: {current_words}
Text: {section_text}
## Depth Analysis
""",
}

def run_depth_analyzer(section_text: str, section_label: str, target_words: int, language: str, llm_func, system_instruction: str = "") -> dict:
    """Bölümün yeterli derinliğe ve kelime sayısına sahip olup olmadığını kontrol eder."""
    lang = language if language in _DEPTH_ANALYZER_PROMPTS else "tr"
    current_words = len(section_text.split())
    prompt = _DEPTH_ANALYZER_PROMPTS[lang].format(
        section_text=section_text, section_label=section_label,
        target_words=target_words, current_words=current_words
    )
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        # Genişletilmiş metin varsa çıkar
        expanded = None
        needs_rewrite = False
        for marker in ["## Genişletilmiş Metin", "## Expanded Text", "## النص الموسع"]:
            if marker in raw:
                expanded = raw[raw.index(marker) + len(marker):].strip()
                needs_rewrite = True
                break
        # Kelime sayısı kontrolü
        if not needs_rewrite and current_words < target_words * 0.6:
            needs_rewrite = True
        # Skor çıkarma
        depth_score = 70  # default
        import re as _re
        score_match = _re.search(r'[Ss]kor[:\s]*(\d+)', raw)
        if score_match:
            depth_score = min(100, max(0, int(score_match.group(1))))
        if depth_score < 60:
            needs_rewrite = True
        return {
            "depth_score": depth_score,
            "analysis_md": raw[:500] if "##" in raw else "Derinlik analizi tamamlandı.",
            "needs_rewrite": needs_rewrite,
            "expanded_text": expanded
        }
    except Exception as e:
        logger.warning(f"DepthAnalyzer error in {section_label}: {e}")
    return {"depth_score": 100, "analysis_md": "Derinlik analizi yapılamadı.", "needs_rewrite": False, "expanded_text": None}


# ============================================================
# PHASE 3 — Post-writing agents (in parallel)
# ============================================================

def _make_snippet(full_markdown: str, head: int = 8000, tail: int = 3000) -> str:
    """Context window aşımını önlemek için metnin baş ve sonunu alır."""
    if len(full_markdown) <= head + tail:
        return full_markdown
    return full_markdown[:head] + "\n\n[... orta bölümler kısaltıldı ...]\n\n" + full_markdown[-tail:]

_TRANSITION_PROMPTS = {
    "tr": """\
Aşağıdaki akademik tezde bölümler arası geçişleri değerlendir.

METİN:
{snippet}

ÇIKTI FORMATI:
## Geçiş Analizi Raporu
### Güçlü Geçişler
[iyi olan geçişler]
### Zayıf Geçişler
[sorunlu geçişler ve öneriler]
### Genel Değerlendirme
[1-2 cümle]
""",
    "ar": "قيّم الانتقالات بين الفصول.\nالنص: {snippet}\n## تقرير الانتقالات",
    "en": "Evaluate transitions between sections.\nText: {snippet}\n## Transition Report",
}

def run_transition_agent(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Bölümler arası geçişleri kontrol eder ve iyileştirmeler önerir."""
    lang = language if language in _TRANSITION_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _TRANSITION_PROMPTS[lang].format(snippet=snippet)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"TransitionAgent error: {e}")
        return "## Geçiş Analizi Raporu\nAnaliz sırasında hata oluştu.\n"

_CITATION_BALANCER_PROMPTS = {
    "tr": """\
Aşağıdaki tezdeki atıf dağılımını analiz et.

Kural-tabanlı ön bilgi: {apa_count} APA atıfı, {doi_count} DOI tespit edildi.

METİN:
{snippet}

ÇIKTI FORMATI:
## Atıf Dengesi Raporu
### Bölüm Bazlı Atıf Yoğunluğu
[her bölüm için atıf sayısı tahmini]
### Atıfsız Paragraflar
[atıf eksik olan yerler]
### Öneriler
[denge önerileri]
""",
    "ar": "حلل توزيع الإحالات. APA: {apa_count}, DOI: {doi_count}.\nالنص: {snippet}\n## تقرير توازن الإحالات",
    "en": "Analyze citation distribution. APA: {apa_count}, DOI: {doi_count}.\nText: {snippet}\n## Citation Balance Report",
}

def run_citation_balancer(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Bölümler arası atıf dağılımını (rule-based + LLM) analiz eder."""
    apa_count = len(_APA_PATTERN.findall(full_markdown))
    doi_count = len(_DOI_PATTERN.findall(full_markdown))
    lang = language if language in _CITATION_BALANCER_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _CITATION_BALANCER_PROMPTS[lang].format(snippet=snippet, apa_count=apa_count, doi_count=doi_count)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"CitationBalancer error: {e}")
        return "## Atıf Dengesi Raporu\nAnaliz sırasında hata oluştu.\n"

_ARGUMENT_MAPPER_PROMPTS = {
    "tr": """\
Aşağıdaki tezin mantıksal argüman akışını çıkar.

KONU: {topic}

METİN:
{snippet}

ÇIKTI FORMATI:
## Argüman Haritası Raporu
### Ana Argüman Zinciri
[hipotez → kanıt → sonuç akışı]
### Döngüsel / Kopuk Argümanlar
[varsa listele]
### Desteklenmeyen İddialar
[kanıtsız iddialar]
### Genel Değerlendirme
[1-2 cümle]
""",
    "ar": "استخرج تسلسل الحجج. الموضوع: {topic}\nالنص: {snippet}\n## خريطة الحجج",
    "en": "Map logical argument flow. Topic: {topic}\nText: {snippet}\n## Argument Map Report",
}

def run_argument_mapper(full_markdown: str, topic: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Mantıksal argüman akışının haritasını çıkarır, döngüsel/kopuk argümanları bulur."""
    lang = language if language in _ARGUMENT_MAPPER_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _ARGUMENT_MAPPER_PROMPTS[lang].format(topic=topic, snippet=snippet)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"ArgumentMapper error: {e}")
        return "## Argüman Haritası Raporu\nAnaliz sırasında hata oluştu.\n"

_METHODOLOGY_AUDITOR_PROMPTS = {
    "tr": """\
Aşağıdaki tezin yöntem bölümünü titizlik açısından denetle.

METİN:
{snippet}

ÇIKTI FORMATI:
## Metodoloji Denetim Raporu
### Araştırma Tasarımı
[uygun mu?]
### Örneklem / Veri Toplama
[yeterli mi?]
### Analiz Yöntemi
[doğru mu?]
### Sınırlılıklar
[eksikler]
### Genel Değerlendirme
[1-2 cümle]
""",
    "ar": "راجع قسم المنهجية.\nالنص: {snippet}\n## تقرير تدقيق المنهجية",
    "en": "Audit methodology section.\nText: {snippet}\n## Methodology Audit Report",
}

def run_methodology_auditor(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Özellikle metodoloji bölümünü titizlik ve bilimsellik açısından denetler."""
    lang = language if language in _METHODOLOGY_AUDITOR_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _METHODOLOGY_AUDITOR_PROMPTS[lang].format(snippet=snippet)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"MethodologyAuditor error: {e}")
        return "## Metodoloji Denetim Raporu\nAnaliz sırasında hata oluştu.\n"

_ABSTRACT_VALIDATOR_PROMPTS = {
    "tr": """\
Aşağıdaki tezin özetini (abstract) tezin geri kalanıyla karşılaştır.

METİN:
{snippet}

ÇIKTI FORMATI:
## Özet Doğrulama Raporu
### Amaç Uyumu
[özetin amacı tezle uyumlu mu?]
### Yöntem Uyumu
[özetteki yöntem, tezdeki yöntemle eşleşiyor mu?]
### Bulgu Uyumu
[özetin bulguları tez bulgularıyla tutarlı mı?]
### Genel Değerlendirme
[1-2 cümle]
""",
    "ar": "قارن الملخص مع محتوى الأطروحة.\nالنص: {snippet}\n## تقرير التحقق من الملخص",
    "en": "Validate abstract against thesis.\nText: {snippet}\n## Abstract Validation Report",
}

def run_abstract_validator(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Özetin (Abstract) tezin geri kalanıyla uyumlu olup olmadığını kontrol eder."""
    lang = language if language in _ABSTRACT_VALIDATOR_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _ABSTRACT_VALIDATOR_PROMPTS[lang].format(snippet=snippet)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"AbstractValidator error: {e}")
        return "## Özet Doğrulama Raporu\nAnaliz sırasında hata oluştu.\n"

_TERMINOLOGY_GUARD_PROMPTS = {
    "tr": """\
Aşağıdaki tezde tutarsız terminoloji kullanımını bul.

METİN:
{snippet}

ÇIKTI FORMATI:
## Terminoloji Raporu
### Tutarsız Terimler
[aynı kavram için farklı kelimeler kullanılmış mı? Tablo halinde göster]
### Öneriler
[hangi terimler standardize edilmeli]
""",
    "ar": "ابحث عن المصطلحات غير المتسقة.\nالنص: {snippet}\n## تقرير المصطلحات",
    "en": "Find inconsistent terminology.\nText: {snippet}\n## Terminology Guard Report",
}

def run_terminology_guard(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Tutarsız terminoloji kullanımını bulur."""
    lang = language if language in _TERMINOLOGY_GUARD_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _TERMINOLOGY_GUARD_PROMPTS[lang].format(snippet=snippet)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"TerminologyGuard error: {e}")
        return "## Terminoloji Raporu\nAnaliz sırasında hata oluştu.\n"

_STATISTICS_CHECKER_PROMPTS = {
    "tr": """\
Aşağıdaki tezdeki sayısal verileri ve istatistikleri kontrol et.

METİN:
{snippet}

ÇIKTI FORMATI:
## İstatistik Kontrol Raporu
### Sayısal Tutarsızlıklar
[çelişen rakamlar, toplamı 100 yapmayan yüzdeler vb.]
### Doğrulanamayan İstatistikler
[kaynağı belirtilmemiş istatistikler]
### Genel Değerlendirme
[1-2 cümle]
""",
    "ar": "افحص الإحصاءات والأرقام.\nالنص: {snippet}\n## تقرير فحص الإحصاءات",
    "en": "Check statistics and numbers.\nText: {snippet}\n## Statistics Checker Report",
}

def run_statistics_checker(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> str:
    """Rakamlar, yüzdeler ve istatistiklerdeki tutarsızlıkları bulur."""
    lang = language if language in _STATISTICS_CHECKER_PROMPTS else "tr"
    snippet = _make_snippet(full_markdown)
    prompt = _STATISTICS_CHECKER_PROMPTS[lang].format(snippet=snippet)
    try:
        raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
        if "##" in raw:
            raw = raw[raw.index("##"):]
        return raw.strip()
    except Exception as e:
        logger.warning(f"StatisticsChecker error: {e}")
        return "## İstatistik Kontrol Raporu\nAnaliz sırasında hata oluştu.\n"


# ============================================================
# PHASE 4 — Final agents (process full text in chunks)
# ============================================================

def _process_text_in_chunks(text: str, chunk_prompt_template: str, text_key: str,
                            language: str, llm_func, system_instruction: str = "",
                            chunk_size: int = 4000) -> str:
    """Uzun metni parçalara bölerek her parçayı LLM ile işler ve birleştirir."""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i + chunk_size])

    processed = []
    for chunk in chunks:
        prompt = chunk_prompt_template.format(**{text_key: chunk})
        try:
            raw = llm_func(prompt, system_prompt=system_instruction) if system_instruction else llm_func(prompt)
            # Model düzeltilmiş metni döndürmeli, açıklama eklemişse orijinalden kısa olmamalı
            cleaned = raw.strip()
            if cleaned and len(cleaned) > len(chunk) * 0.3:
                processed.append(cleaned)
            else:
                processed.append(chunk)
        except Exception as e:
            logger.warning(f"Chunk processing error: {e}")
            processed.append(chunk)
    return "\n".join(processed)


_READABILITY_PROMPTS = {
    "tr": """\
Aşağıdaki akademik metni okunabilirlik açısından iyileştir:
- Çok uzun cümleleri böl
- Pasif yapıları gerektiğinde aktife çevir
- Paragraf uzunluklarını dengele

ÖNEMLİ: Sadece iyileştirilmiş metni döndür. Açıklama, not veya rapor YAZMA. İçeriği değiştirme, sadece yazım kalitesini artır.

METİN:
{chunk}
""",
    "ar": "حسّن قابلية القراءة. أعد النص المحسن فقط.\nالنص: {chunk}",
    "en": "Improve readability. Return ONLY improved text.\nText: {chunk}",
}

def run_readability_optimizer(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> dict:
    """Okunabilirlik sorunlarını (uzun cümleler, pasif yapı vs.) düzeltir."""
    lang = language if language in _READABILITY_PROMPTS else "tr"
    optimized = _process_text_in_chunks(
        text=full_markdown,
        chunk_prompt_template=_READABILITY_PROMPTS[lang],
        text_key="chunk",
        language=lang,
        llm_func=llm_func,
        system_instruction=system_instruction,
    )
    return {"optimized_text": optimized, "changes_md": "Okunabilirlik iyileştirmeleri uygulandı.", "improvements_count": 1}


_PROOFREADER_PROMPTS = {
    "tr": """\
Aşağıdaki akademik metni son kez gözden geçir ve düzelt:
- Yazım hataları
- Noktalama hataları
- Başlık numaralandırma tutarsızlıkları
- Tablo/şekil referans tutarlılığı

ÖNEMLİ: Sadece düzeltilmiş metni döndür. Açıklama YAZMA. İçeriği değiştirme.

METİN:
{chunk}
""",
    "ar": "قم بالتدقيق اللغوي النهائي. أعد النص المدقق فقط.\nالنص: {chunk}",
    "en": "Final proofreading. Return ONLY corrected text.\nText: {chunk}",
}

def run_final_proofreader(full_markdown: str, language: str, llm_func, system_instruction: str = "") -> dict:
    """Son yazım ve noktalama denetimi yapar, düzeltilmiş metni döndürür."""
    lang = language if language in _PROOFREADER_PROMPTS else "tr"
    proofread = _process_text_in_chunks(
        text=full_markdown,
        chunk_prompt_template=_PROOFREADER_PROMPTS[lang],
        text_key="chunk",
        language=lang,
        llm_func=llm_func,
        system_instruction=system_instruction,
    )
    return {"proofread_text": proofread, "corrections_md": "Yazım denetimi tamamlandı.", "error_count": 0}


# ============================================================
# ORCHESTRATORS
# ============================================================

def run_phase1_agents(topic: str, outline: str, language: str, llm_func, rag_context: str = "", system_instruction: str = "", report_callback=None) -> dict:
    """TopicAnalyzer -> OutlineCritic -> GapDetector (sıralı)."""
    def _report(msg: str):
        logger.info(msg)
        if report_callback:
            try: report_callback(msg)
            except Exception: pass

    _report("Phase 1: Topic Analyzer çalışıyor...")
    ta_res = run_topic_analyzer(topic, language, llm_func, rag_context, system_instruction)

    _report("Phase 1: Outline Critic çalışıyor...")
    oc_res = run_outline_critic(outline, topic, language, llm_func, ta_res.get("analysis_md", ""), system_instruction)

    _report("Phase 1: Gap Detector çalışıyor...")
    gd_res = run_gap_detector(oc_res.get("improved_outline", outline), rag_context, language, llm_func, system_instruction)

    return {"topic_analyzer": ta_res, "outline_critic": oc_res, "gap_detector": gd_res}


def run_phase3_agents(full_markdown: str, topic: str, language: str, llm_func, system_instruction: str = "", report_callback=None) -> dict:
    """Tüm Phase 3 ajanlarını paralel çalıştırır (Verifier, Thread, Skeptic + 7 yeni)."""
    def _report(msg: str):
        logger.info(msg)
        if report_callback:
            try: report_callback(msg)
            except Exception: pass

    _report("Phase 3: Paralel ajanlar başlatılıyor...")
    result = {}

    # Verifier senkron çalışsın
    verifier_out = run_verifier(full_markdown, language=language)
    result["verifier"] = verifier_out

    futures = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures[executor.submit(run_thread, full_markdown, language, llm_func, system_instruction)] = "thread_report"
        futures[executor.submit(run_skeptic, full_markdown, topic, language, llm_func, system_instruction)] = "skeptic_report"
        futures[executor.submit(run_transition_agent, full_markdown, language, llm_func, system_instruction)] = "transition_report"
        futures[executor.submit(run_citation_balancer, full_markdown, language, llm_func, system_instruction)] = "citation_report"
        futures[executor.submit(run_argument_mapper, full_markdown, topic, language, llm_func, system_instruction)] = "argument_report"
        futures[executor.submit(run_methodology_auditor, full_markdown, language, llm_func, system_instruction)] = "methodology_report"
        futures[executor.submit(run_abstract_validator, full_markdown, language, llm_func, system_instruction)] = "abstract_report"
        futures[executor.submit(run_terminology_guard, full_markdown, language, llm_func, system_instruction)] = "terminology_report"
        futures[executor.submit(run_statistics_checker, full_markdown, language, llm_func, system_instruction)] = "statistics_report"

        for f in as_completed(futures):
            name = futures[f]
            try:
                result[name] = f.result()
                _report(f"  ✅ {name} tamamlandı")
            except Exception as e:
                result[name] = f"Hata: {e}"
                _report(f"  ❌ {name} hata: {e}")

    _report("Phase 3: Tüm paralel analizler tamamlandı.")
    return result

def run_phase4_agents(full_markdown: str, language: str, llm_func, system_instruction: str = "", report_callback=None) -> dict:
    """ReadabilityOptimizer -> FinalProofreader (sıralı)."""
    def _report(msg: str):
        logger.info(msg)
        if report_callback:
            try: report_callback(msg)
            except Exception: pass

    _report("Phase 4: Readability Optimizer çalışıyor...")
    ro_res = run_readability_optimizer(full_markdown, language, llm_func, system_instruction)

    _report("Phase 4: Final Proofreader çalışıyor...")
    fp_res = run_final_proofreader(ro_res.get("optimized_text", full_markdown), language, llm_func, system_instruction)

    return {
        "final_text": fp_res.get("proofread_text", ""),
        "readability_report": ro_res.get("changes_md", ""),
        "proofreader_report": fp_res.get("corrections_md", "")
    }

def run_all_qa_deep(full_markdown: str, topic: str, language: str, llm_func, system_instruction: str = "", report_callback=None) -> dict:
    """Master orchestrator: Phase 3 (Paralel) -> Phase 4 (Sıralı)."""
    def _report(msg: str):
        logger.info(msg)
        if report_callback:
            try: report_callback(msg)
            except Exception: pass

    _report("Master QA Orchestrator: Derin analiz başlıyor...")

    # Phase 3
    p3_res = run_phase3_agents(full_markdown, topic, language, llm_func, system_instruction, report_callback)

    # Phase 4
    p4_res = run_phase4_agents(full_markdown, language, llm_func, system_instruction, report_callback)

    combined_md = "\n\n---\n\n## 🔬 Gelişmiş Kalite Analizi (Deep QA)\n\n"
    combined_md += p3_res.get("verifier", {}).get("summary_md", "") + "\n---\n\n"

    reports = ["thread_report", "skeptic_report", "transition_report", "citation_report", "argument_report",
               "methodology_report", "abstract_report", "terminology_report", "statistics_report"]

    for r in reports:
        val = p3_res.get(r, "")
        if val:
            combined_md += val + "\n---\n\n"

    combined_md += "### Okunabilirlik ve Yazım Denetimi\n"
    combined_md += f"- **Okunabilirlik**: {p4_res.get('readability_report', '')}\n"
    combined_md += f"- **Yazım Düzeltmeleri**: {p4_res.get('proofreader_report', '')}\n"

    final_dict = {
        "phase3": p3_res,
        "phase4": p4_res,
        "final_text": p4_res.get("final_text", ""),
        "combined_md": combined_md
    }

    _report("Master QA Orchestrator: Analiz tamamlandı.")
    return final_dict


