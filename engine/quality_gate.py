# -*- coding: utf-8 -*-
"""
VeFa - Tez Kalite Puanlama Modülü
Üretilen tezi/makaleyi birkaç somut, ölçülebilir kritere göre 0-100 arası puanlar
ve elle kontrol edilmesi gereken noktaları listeler. Bu bir "mükemmellik garantisi"
değildir — otomatik olarak ölçülebilen şeyleri (kelime sayısı, başlık yapısı, atıf
yoğunluğu, tekrar, dil tutarlılığı) kontrol eder; akademik içerik/argüman kalitesini
değerlendiremez, bunu hâlâ danışmanınız/siz değerlendirmelisiniz.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class QualityScore:
    word_count_score: float = 0.0      # /15
    structure_score: float = 0.0       # /20
    citation_score: float = 0.0        # /20
    repetition_score: float = 0.0      # /15
    language_score: float = 0.0        # /15
    formatting_score: float = 0.0      # /15
    overall_score: float = 0.0         # /100
    suggestions: List[str] = field(default_factory=list)
    stats: Dict[str, float] = field(default_factory=dict)


# Each entry is a tuple: (display_name, list_of_accepted_synonyms)
REQUIRED_SECTIONS_TR = [
    ("giriş",    ["giriş", "introduction"]),
    ("literatür", ["literatür", "literature", "kuramsal", "teorik", "kavramsal", "alanyazın"]),
    ("yöntem",   ["yöntem", "methodology", "method", "araştırma yöntemi", "materyal"]),
    ("bulgular", ["bulgular", "results", "findings", "analiz", "veri"]),
    ("tartışma", ["tartışma", "discussion", "değerlendirme"]),
    ("sonuç",    ["sonuç", "conclusion", "öneriler"]),
    ("kaynak",   ["kaynak", "kaynakça", "references", "referanslar", "المصادر"]),
]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def _score_word_count(text: str, target_words: int) -> tuple:
    wc = _word_count(text)
    if target_words <= 0:
        return 15.0, wc, []
    ratio = wc / target_words
    if 0.9 <= ratio <= 1.3:
        score = 15.0
    elif 0.7 <= ratio < 0.9 or 1.3 < ratio <= 1.6:
        score = 10.0
    elif 0.5 <= ratio < 0.7:
        score = 5.0
    else:
        score = 2.0
    suggestions = []
    if ratio < 0.9:
        suggestions.append(f"📏 Kelime sayısı hedefin altında ({wc}/{target_words}) — bazı bölümler genişletilmeli.")
    return score, wc, suggestions


def _score_structure(text: str) -> tuple:
    headings = re.findall(r'^#{1,6}\s+(.+)$', text, flags=re.MULTILINE)
    lower_headings = " ".join(h.lower() for h in headings)
    found = 0
    missing_names = []
    for display_name, synonyms in REQUIRED_SECTIONS_TR:
        if any(syn in lower_headings for syn in synonyms):
            found += 1
        else:
            missing_names.append(display_name)
    score = min(20.0, (found / len(REQUIRED_SECTIONS_TR)) * 20.0)
    suggestions = []
    if missing_names:
        suggestions.append(f"🧩 Standart bölümlerden bazıları başlıklarda görünmüyor: {', '.join(missing_names)}. (Özel bölüm planı kullandıysanız bu normaldir.)")
    if len(headings) < 4:
        suggestions.append("🧩 Belgede çok az başlık var — daha fazla alt başlıkla bölmeyi düşünün.")
    return score, len(headings), suggestions


# In-text citation: (Yazar, 2020) or (Yazar ve ark., 2020) or (Author et al., 2020)
_CITATION_PATTERN = re.compile(
    r'\(\'?[A-ZÇĞİÖŞÜA-Z][a-zçğıöşüa-z\'-]+(?:\s+(?:ve ark\.|et al\.|vd\.))?[,.]?\s*\d{4}[a-z]?(?:[,;]\s*s\.?\s*\d+)?\)',
    re.UNICODE
)

# References/Bibliography section header detector (very permissive)
_REFERENCES_HEADER = re.compile(
    r'^#{1,3}\s*(?:KAYNAKÇA|Kaynakça|kaynakça|REFERENCES|References|REFERANSLAR|Referanslar|المصادر|والمراجع|BIBLIOGRAPHY|Bibliography)',
    re.MULTILINE | re.IGNORECASE
)


def _score_citations(text: str) -> tuple:
    # Strip references section from body before computing density
    refs_match = _REFERENCES_HEADER.search(text)
    if refs_match:
        body_text = text[:refs_match.start()]
    else:
        body_text = text

    body_word_count = max(1, _word_count(body_text))
    citations = _CITATION_PATTERN.findall(body_text)
    density_per_1000 = (len(citations) / body_word_count) * 1000
    if density_per_1000 >= 4:
        score = 20.0
    elif density_per_1000 >= 2:
        score = 14.0
    elif density_per_1000 >= 1:
        score = 8.0
    else:
        score = 3.0
    suggestions = []
    if density_per_1000 < 2:
        suggestions.append(f"📚 Atıf yoğunluğu düşük (~{density_per_1000:.1f}/1000 kelime) — YÖK/APA 7 için genelde daha sık atıf beklenir.")
    has_references_section = bool(refs_match)
    if not has_references_section:
        score = min(score, 5.0)
        suggestions.append("📚 Kaynakça bölümü bulunamadı veya başlığı standart değil.")
    return score, len(citations), suggestions


def _score_repetition(text: str) -> tuple:
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if len(p.strip()) > 60]
    if len(paragraphs) < 2:
        return 15.0, 0, []
    seen_starts = {}
    dup_count = 0
    for p in paragraphs:
        start = p[:50].lower()
        seen_starts[start] = seen_starts.get(start, 0) + 1
        if seen_starts[start] > 1:
            dup_count += 1
    ratio = dup_count / len(paragraphs)
    score = max(0.0, 15.0 * (1 - min(1.0, ratio * 4)))
    suggestions = []
    if dup_count > 0:
        suggestions.append(f"🔁 {dup_count} paragrafın başlangıcı diğerleriyle çok benziyor — tekrar/yer değiştirme kontrolü yapın.")
    return score, dup_count, suggestions


def _score_language_consistency(language_warnings: List[str]) -> tuple:
    if not language_warnings:
        return 15.0, 0, []
    penalty = min(15.0, len(language_warnings) * 4.0)
    return 15.0 - penalty, len(language_warnings), [
        "🌐 Dil tutarlılığı uyarıları var (yukarıda listelendi) — bu bölümleri mutlaka elle kontrol edin."
    ]


def _score_formatting(text: str) -> tuple:
    issues = 0
    suggestions = []
    if re.search(r'\*\*\d+(\.\d+)*\.?\s+[^*#\n]+\*\*', text):
        issues += 1
        suggestions.append("🖋️ Kalın (`**...**`) yazılmış ama `#` başlık biçimine çevrilmemiş satırlar tespit edildi.")
    if re.search(r'\b(Word count|Target word count|Here is|İşte)\b', text, flags=re.IGNORECASE):
        issues += 1
        suggestions.append("🖋️ Metinde yapay zekaya ait meta not/gevezelik kalıntısı olabilir.")
    score = max(0.0, 15.0 - issues * 5.0)
    return score, issues, suggestions


def calculate_quality_score(
    full_text: str,
    target_words: int,
    language_warnings: List[str] = None
) -> QualityScore:
    """
    Score a generated thesis/article across word count, structure, citation
    density, repetition, language consistency, and residual formatting issues.
    Returns a QualityScore with an overall /100 total and a flat list of
    actionable suggestions (Turkish).
    """
    language_warnings = language_warnings or []
    result = QualityScore()

    wc_score, wc, wc_sugg = _score_word_count(full_text, target_words)
    struct_score, heading_count, struct_sugg = _score_structure(full_text)
    cite_score, cite_count, cite_sugg = _score_citations(full_text)
    rep_score, dup_count, rep_sugg = _score_repetition(full_text)
    lang_score, lang_issue_count, lang_sugg = _score_language_consistency(language_warnings)
    fmt_score, fmt_issue_count, fmt_sugg = _score_formatting(full_text)

    result.word_count_score = round(wc_score, 1)
    result.structure_score = round(struct_score, 1)
    result.citation_score = round(cite_score, 1)
    result.repetition_score = round(rep_score, 1)
    result.language_score = round(lang_score, 1)
    result.formatting_score = round(fmt_score, 1)
    result.overall_score = round(
        wc_score + struct_score + cite_score + rep_score + lang_score + fmt_score, 1
    )
    result.stats = {
        "word_count": wc,
        "heading_count": heading_count,
        "citation_count": cite_count,
        "duplicate_paragraphs": dup_count,
        "language_warning_count": lang_issue_count,
        "formatting_issue_count": fmt_issue_count,
    }
    result.suggestions = wc_sugg + struct_sugg + cite_sugg + rep_sugg + lang_sugg + fmt_sugg
    return result


def format_quality_report(score: QualityScore) -> str:
    """Render a QualityScore as a short Turkish markdown report."""
    lines = [
        f"## 📊 Kalite Puanı: {score.overall_score:.0f}/100",
        "",
        f"- Kelime Sayısı: {score.word_count_score:.0f}/15",
        f"- Yapı (Başlıklar): {score.structure_score:.0f}/20",
        f"- Atıf Yoğunluğu: {score.citation_score:.0f}/20",
        f"- Tekrar Kontrolü: {score.repetition_score:.0f}/15",
        f"- Dil Tutarlılığı: {score.language_score:.0f}/15",
        f"- Biçimlendirme: {score.formatting_score:.0f}/15",
    ]
    if score.suggestions:
        lines.append("")
        lines.append("### Öneriler")
        for s in score.suggestions:
            lines.append(f"- {s}")
    return "\n".join(lines)
