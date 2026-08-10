# -*- coding: utf-8 -*-
"""
VeFa - Çok Dilli Akademik İstemler (Türkçe, Arapça, İngilizce)
Bu modül, tez ve akademik makale yazımında Türkçe, Arapça (العربية) veya İngilizce
dil seçeneklerinin kusursuz uygulanmasını sağlar.
"""

LANG_CONFIGS = {
    "tr": {
        "name": "Türkçe",
        "system_instruction": "Sen üst düzey bir Akademik Tez ve Makale Yazım Uzmanısın. YALNIZCA SAF AKADEMİK TÜRKÇE KULLANACAKSIN. Kesinlikle başka bir dil veya yapay zeka meta-notları (Word count vb.) eklemeyeceksin. ASLA kendini tanıtma, ASLA \"Bir akademik uzmanım\", \"İşte metin\", \"Aşağıda...\" gibi giriş cümleleri yazma, ASLA talimatları veya bu istemi tekrar etme, ASLA kullanıcıyla sohbet eder gibi cevap verme (\"Görüyorum ki...\", \"Bahsettiğiniz...\" gibi). SADECE doğrudan akademik metnin kendisini yaz — hiçbir giriş, açıklama veya yorum ekleme.",
        "intro": "1. BÖLÜM: GİRİŞ",
        "lit_review": "2. BÖLÜM: LİTERATÜR TARAMASI",
        "methodology": "3. BÖLÜM: YÖNTEM VE METODOLOJİ",
        "results": "4. BÖLÜM: BULGULAR VE ANALİZ",
        "discussion": "5. BÖLÜM: TARTIŞMA VE DEĞERLENDİRME",
        "conclusion": "6. BÖLÜM: SONUÇ VE ÖNERİLER",
        "references": "KAYNAKÇA",
        "abstract": "ÖZET",
        "keywords": "Anahtar Kelimeler",
        "toc_title": "İÇİNDEKİLER",
        "author_prefix": "Hazırlayan",
        "advisor_prefix": "Tez Danışmanı"
    },
    "ar": {
        "name": "Arapça",
        "system_instruction": "أنت خبير فائق في كتابة الأطروحات والأبحاث الأكاديمية باللغة العربية الفصحى. يجب عليك استخدام الأحرف والكلمات العربية الفصحى فقط 100%. يمنع منعاً باتاً كتابة أي جمل أو كلمات باللغة التركية أو الإنجليزية أو بالأحرف اللاتينية، بما في ذلك قائمة المراجع والعناوين الأكاديمية. لا تُقدّم نفسك أبداً، ولا تكتب عبارات افتتاحية مثل \"إليك النص\" أو \"بصفتي خبيراً\"، ولا تكرر هذه التعليمات، ولا ترد وكأنك تتحدث مع المستخدم. اكتب فقط النص الأكاديمي نفسه مباشرة دون أي مقدمات أو تعليقات.",
        "intro": "الفصل الأول: المقدمة",
        "lit_review": "الفصل الثاني: الدراسات السابقة والإطار النظري",
        "methodology": "الفصل الثالث: منهجية البحث وإجراءاته",
        "results": "الفصل الرابع: عرض النتائج وتحليلها",
        "discussion": "الفصل الخامس: مناقشة النتائج وتفسيرها",
        "conclusion": "الفصل السادس: الخاتمة والتوصيات",
        "references": "المصادر والمراجع",
        "abstract": "الملخص",
        "keywords": "الكلمات المفتاحية",
        "toc_title": "الفهرس والمحتويات",
        "author_prefix": "إعداد",
        "advisor_prefix": "المشرف الأكاديمي"
    },
    "en": {
        "name": "İngilizce",
        "system_instruction": "You are a senior Academic Thesis Writing Expert. USE ONLY HIGH-LEVEL ACADEMIC ENGLISH (100%). Do not output any Turkish/Arabic text or LLM meta-notes (Word count: X). NEVER introduce yourself, NEVER write preambles like \"Here is the text\" or \"As an academic expert...\", NEVER repeat these instructions, NEVER respond conversationally (\"I see that...\", \"You mentioned...\"). Output ONLY the academic text itself — no introduction, explanation, or commentary.",
        "intro": "CHAPTER 1: INTRODUCTION",
        "lit_review": "CHAPTER 2: LITERATURE REVIEW",
        "methodology": "CHAPTER 3: METHODOLOGY",
        "results": "CHAPTER 4: RESULTS AND ANALYSIS",
        "discussion": "CHAPTER 5: DISCUSSION",
        "conclusion": "CHAPTER 6: CONCLUSION AND RECOMMENDATIONS",
        "references": "REFERENCES",
        "abstract": "ABSTRACT",
        "keywords": "Keywords",
        "toc_title": "TABLE OF CONTENTS",
        "author_prefix": "Prepared by",
        "advisor_prefix": "Thesis Advisor"
    }
}

SYSTEM_PROMPT = """Sen, Türkiye'deki YÖK tez yazım kılavuzlarına ve uluslararası akademik standartlara mükemmel derecede hakim, üst düzey bir Akademik Tez ve Makale Yazım Uzmanısın.

KAZIKLI VE KESİN KURALLAR:
1. SEÇİLEN DİLDE YAZIM YAPACAKSIN. KESİNLİKLE BAŞKA BİR DİL KARIŞTIRMAYACAKSIN!
2. Metnin sonuna veya başına KESİNLİKLE 'Word count', 'Target word count', 'Here is the text' gibi yapay zeka notları, kelime sayısı açıklamaları EKLEMEYECEKSİN.
3. Yazım dilin resmi, objektif, bilimsel ve akademik derinliğe sahip olmalıdır.
4. Paragrafların başına sebepsiz yere madde işareti (* veya -) KOYMAYACAKSIN. Akıcı akademik paragraflar yazacaksın.
5. BAŞLIK FORMATI: Tüm bölüm ve alt başlıkları KESİNLİKLE Markdown `#` işaretleriyle belirteceksin.
6. Yalnızca doğrudan akademik metni döndür. Yapay zeka gevezeliği EKLEME.
7. ASLA "İşte özetiniz", "Kaynakları gözden geçirerek", "Anladığım kadarıyla" gibi sohbet/giriş cümleleri kurma. Direkt metne başla.
"""

def get_prompts_for_language(language: str = "tr") -> dict:
    """
    Returns native language prompts for Arabic, English, or Turkish to prevent LLM language confusion.
    """
    lang = language.lower()
    cfg = LANG_CONFIGS.get(lang, LANG_CONFIGS["tr"])

    if lang == "ar":
        return {
            "outline": f"""قم بإعداد الفهرس والمخطط التفصيلي للأطروحة باللغة العربية الفصحى 100%.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{target_words}} كلمة تقريباً

الشروط:
1. اكتب جميع العناوين باللغة العربية الفصحى حصراً وبأحرف عربية.
2. تشمل الأقسام التالية:
   # {cfg['intro']}
   # {cfg['lit_review']}
   # {cfg['methodology']}
   # {cfg['results']}
   # {cfg['discussion']}
   # {cfg['conclusion']}

عد فقط المخطط التفصيلي بتنسيق Markdown.
""",
            "introduction": f"""اكتب "{cfg['intro']}" باللغة العربية الفصحى الأكاديمية الرصينة.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي:
{{outline}}

جميع العناوين والنصوص يجب أن تكون باللغة العربية الفصحى 100%. يمنع استخدام الكلمات أو الأحرف الإنجليزية أو التركية.
""",
            "literature_review": f"""اكتب "{cfg['lit_review']}" باللغة العربية الفصحى الأكاديمية.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي:
{{outline}}

جميع العناوين والنصوص والجدول المقارن يجب أن تكون باللغة العربية الفصحى 100%. يمنع استخدام الأحرف اللاتينية.
""",
            "methodology": f"""اكتب "{cfg['methodology']}" باللغة العربية الفصحى الأكاديمية.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي:
{{outline}}

جميع العناوين والنصوص يجب أن تكون باللغة العربية الفصحى 100%.
""",
            "results": f"""اكتب "{cfg['results']}" باللغة العربية الفصحى الأكاديمية مع الجداول الاحصائية.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي:
{{outline}}

جميع العناوين والنصوص والجداول يجب أن تكون باللغة العربية الفصحى 100%.
""",
            "discussion": f"""اكتب "{cfg['discussion']}" باللغة العربية الفصحى الأكاديمية.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي:
{{outline}}

جميع العناوين والنصوص يجب أن تكون باللغة العربية الفصحى 100%.
""",
            "conclusion": f"""اكتب "{cfg['conclusion']}" باللغة العربية الفصحى الأكاديمية.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي:
{{outline}}

جميع العناوين والنصوص يجب أن تكون باللغة العربية الفصحى 100%.
""",
            "references": f"""اكتب قائمة "{cfg['references']}" باللغة العربية الفصحى وبأحرف عربية 100% وفقاً لمعايير APA 7.

الموضوع: {{topic}}
{{topic_summary}}

شروط صارمة:
1. اكتب أسماء جميع المؤلفين وعناوين الأبحاث والمجلات باللغة العربية والأحرف العربية حصراً (مثال: عبد الله، م. (2018). إحياء الثقافة الحنفية...).
2. يمنع منعاً باتاً استخدام الأحرف اللاتينية أو الإنجليزية أو التركية في المصادر.
""",
            "abstract": f"""اكتب "{cfg['abstract']}" والكلمات المفتاحية باللغة العربية الفصحى 100%.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}

التنسيق:
# {cfg['abstract']}
[نص الملخص باللغة العربية الفصحى]

**{cfg['keywords']}:** [كلمة 1، كلمة 2، ...]
""",
            "english_abstract": f"""اكتب "{cfg['abstract']}" والكلمات المفتاحية باللغة الإنجليزية الأكاديمية (English Abstract).

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}

التنسيق يجب أن يكون باللغة الإنجليزية 100%.

Format:
# ABSTRACT
[English Abstract Text]

**Keywords:** [keyword1, keyword2, ...]
""",
            "custom_outline": f"""قم بإعداد فهرس ومخطط تفصيلي للأطروحة باللغة العربية الفصحى 100%، باستخدام عناوين الفصول التالية فقط وبنفس الترتيب المحدد. لا تضف أو تحذف أي فصل.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{target_words}} كلمة تقريباً

عناوين الفصول (استخدمها بهذا الترتيب وبهذه الأسماء حصراً):
{{section_titles}}

أعد فقط المخطط التفصيلي بتنسيق Markdown باستخدام علامة #.
""",
            "custom_section": f"""اكتب فصل "{{section_title}}" باللغة العربية الفصحى الأكاديمية الرصينة.

الموضوع: {{topic}}
المستوى الأكاديمي: {{academic_level}}
عدد الكلمات المستهدف: {{word_count}} كلمة على الأقل.
المخطط التفصيلي والسياق:
{{outline}}
{{sources_block}}
يجب أن يكون كل النص باللغة العربية الفصحى 100%. اكتب فقط محتوى هذا الفصل تحديداً، ولا تكرر مواضيع الفصول الأخرى.
""",
            "references_strict": f"""أعد قائمة "{cfg['references']}" بتنسيق APA 7 باستخدام قائمة المصادر التالية فقط، وباللغة العربية الفصحى.

الموضوع: {{topic}}

المصادر المتاحة (استخدم هذه فقط):
{{sources_block}}

قواعد صارمة:
1. استخدم فقط المصادر المذكورة أعلاه حصراً. يمنع منعاً باتاً اختلاق أو إضافة أي مصدر غير موجود في هذه القائمة.
2. نسّق كل مصدر وفق معايير APA 7 وبأحرف عربية.
3. رتب المصادر أبجدياً حسب اسم العائلة للمؤلف.
"""
        }

    elif lang == "en":
        return {
            "outline": f"""Generate a detailed Academic Thesis Outline strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: {{target_words}} words

Return only the markdown heading hierarchy using headings:
# {cfg['intro']}
# {cfg['lit_review']}
# {cfg['methodology']}
# {cfg['results']}
# {cfg['discussion']}
# {cfg['conclusion']}
""",
            "introduction": f"""Write "{cfg['intro']}" strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE:
{{outline}}

All text and headings MUST be in 100% Academic English. Do not write any Turkish or Arabic words.
""",
            "literature_review": f"""Write "{cfg['lit_review']}" strictly in Academic English (100%). Include a comparative Markdown table.

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE:
{{outline}}
""",
            "methodology": f"""Write "{cfg['methodology']}" strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE:
{{outline}}
""",
            "results": f"""Write "{cfg['results']}" strictly in Academic English (100%). Include statistical data tables.

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE:
{{outline}}
""",
            "discussion": f"""Write "{cfg['discussion']}" strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE:
{{outline}}
""",
            "conclusion": f"""Write "{cfg['conclusion']}" strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE:
{{outline}}
""",
            "references": f"""Write "{cfg['references']}" list strictly in Academic English (APA 7 style).

TOPIC: {{topic}}
{{topic_summary}}
""",
            "abstract": f"""Write "{cfg['abstract']}" strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}

Format:
# {cfg['abstract']}
[Abstract Text in Academic English]

**{cfg['keywords']}:** [keyword1, keyword2, ...]
""",
            "custom_outline": f"""Generate a detailed Academic Thesis Outline strictly in Academic English (100%), using ONLY the following chapter titles, in the exact order given. Do not add or remove any chapter.

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: {{target_words}} words

CHAPTER TITLES (use exactly these, in this order):
{{section_titles}}

Return only the markdown heading hierarchy using # for each chapter, with a short 2-4 bullet sketch under each.
""",
            "custom_section": f"""Write the chapter "{{section_title}}" strictly in Academic English (100%).

TOPIC: {{topic}}
ACADEMIC LEVEL: {{academic_level}}
TARGET WORD COUNT: At least {{word_count}} words.
OUTLINE AND CONTEXT:
{{outline}}
{{sources_block}}
All text MUST be in 100% Academic English. Write ONLY the content for this specific chapter — do not repeat content belonging to other chapters.
""",
            "references_strict": f"""Write the "{cfg['references']}" list in APA 7 style, using ONLY the following source list.

TOPIC: {{topic}}

AVAILABLE SOURCES (use only these):
{{sources_block}}

STRICT RULES:
1. Use ONLY the sources listed above. Do NOT invent or add any source not present in this list.
2. Format every source strictly according to APA 7.
3. Sort sources alphabetically by author surname.
"""
        }

    else: # Default Turkish
        return {
            "outline": """Aşağıda verilen konu ve parametrelere uygun olarak, detaylı bir Akademik Tez / Makale İÇİNDEKİLER (Anahat) planı oluştur.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: {target_words} kelime civarı
YAZIM DİLİ: Türkçe

ÇIKTI FORMATI:
Yalnızca başlık listesini Markdown hiyerarşisiyle döndür.
""",
            "introduction": """Aşağıdaki konu ve anahat doğrultusunda "1. BÖLÜM: GİRİŞ" bölümünü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}

Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır.
""",
            "literature_review": """Aşağıdaki konu ve anahat doğrultusunda "2. BÖLÜM: LİTERATÜR TARAMASI" bölümünü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}

Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır. En az 1 karşılaştırma tablosu içermelidir.
""",
            "methodology": """Aşağıdaki konu ve anahat doğrultusunda "3. BÖLÜM: YÖNTEM VE METODOLOJİ" bölümünü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}

Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır.
""",
            "results": """Aşağıdaki konu ve anahat doğrultusunda "4. BÖLÜM: BULGULAR VE ANALİZ" bölümünü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}

Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır.
""",
            "discussion": """Aşağıdaki konu ve anahat doğrultusunda "5. BÖLÜM: TARTIŞMA VE DEĞERLENDİRME" bölümünü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}

Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır.
""",
            "conclusion": """Aşağıdaki konu ve anahat doğrultusunda "6. BÖLÜM: SONUÇ VE ÖNERİLER" bölümünü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}

Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır.
""",
            "references": """Aşağıdaki konu ve metin içeriğine uygun olarak KAYNAKÇA bölümünü oluştur.

KONU: {topic}
{topic_summary}

%100 Türkçe akademik APA 7 kaynakça listesini döndür.
""",
            "abstract": """Aşağıdaki konu doğrultusunda tezin/makalenin YALNIZCA Türkçe ÖZET metnini oluştur.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}

Format:
# ÖZET
[Türkçe Özet Metni]

**Anahtar Kelimeler:** [kelime1, kelime2, ...]
""",
            "english_abstract": """Aşağıdaki konu doğrultusunda tezin/makalenin YALNIZCA İngilizce 'ABSTRACT' metnini oluştur.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}

Tüm metin KESİNLİKLE %100 İngilizce olmalıdır (İngilizce akademik format).

Format:
# ABSTRACT
[English Abstract Text]

**Keywords:** [keyword1, keyword2, ...]
""",
            "custom_outline": """Aşağıda verilen konu, akademik seviye ve ÖZEL BÖLÜM BAŞLIKLARI doğrultusunda, detaylı bir Akademik Tez İÇİNDEKİLER (Anahat) planı oluştur. Anahat YALNIZCA aşağıda verilen bölüm başlıklarını, bu sırayla ve bu isimlerle kullanmalıdır; başka bölüm ekleme veya çıkarma.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: {target_words} kelime civarı
YAZIM DİLİ: Türkçe

BÖLÜM BAŞLIKLARI (bu sırayla ve bu isimlerle kullan):
{section_titles}

ÇIKTI FORMATI:
Yalnızca yukarıdaki başlıkları Markdown # işaretleriyle ve her başlığın altında 2-4 alt maddelik kısa bir taslakla döndür.
""",
            "custom_section": """Aşağıdaki konu ve anahat doğrultusunda "{section_title}" başlıklı bölümü yaz.

KONU: {topic}
AKADEMİK SEVİYE: {academic_level}
HEDEF KELİME SAYISI: En az {word_count} kelime.
ANAHAT VE BAĞLAM:
{outline}
{sources_block}
Tüm metin %100 Türkçe ve akademik üslupta yazılmalıdır. Yalnızca bu bölümün başlığıyla ilgili içerik yaz, diğer bölümlerin konularını tekrarlama.
""",
            "references_strict": """Aşağıda verilen KAYNAK LİSTESİNİ kullanarak KAYNAKÇA bölümünü APA 7 formatında hazırla.

KONU: {topic}

KULLANILACAK KAYNAKLAR (yalnızca bunları kullan):
{sources_block}

KURALLAR:
1. YALNIZCA yukarıda verilen kaynakları kullan. Listede olmayan hiçbir kaynağı UYDURMA veya EKLEME.
2. Her kaynağı APA 7 formatına uygun şekilde biçimlendir.
3. Kaynakları yazarın soyadına göre alfabetik sırala.
4. %100 Türkçe akademik format kullan.
"""
        }


OUTLINE_PROMPT = ""
SECTION_PROMPTS = {}
