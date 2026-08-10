# -*- coding: utf-8 -*-
"""
VeFa - Gerçek Word Dipnotları (Footnotes)
python-docx'in yüksek seviyeli bir dipnot API'si yoktur; bu modül dipnotları
doğrudan OOXML (word/footnotes.xml) seviyesinde inşa eder. İslami ilimler /
fıkıh tezlerinde APA'nın yanı sıra (veya yerine) dipnot sistemi standart
olduğu için eklendi.
"""

from docx.opc.part import XmlPart
from docx.opc.packuri import PackURI
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import qn

FOOTNOTES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"

_INITIAL_FOOTNOTES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    '</w:footnotes>'
).encode("utf-8")


class FootnoteManager:
    """
    Attach real, Word-native footnotes to a python-docx Document.

    Usage:
        fm = FootnoteManager(doc)
        p = doc.add_paragraph("Bu cümlenin sonunda bir dipnot var")
        fm.add_footnote(p, "es-Serahsî, el-Mebsût, C. 3, s. 45.")
    """

    def __init__(self, document):
        self._document = document
        self._next_id = 1

        package = document.part.package
        partname = PackURI("/word/footnotes.xml")
        element = parse_xml(_INITIAL_FOOTNOTES_XML)
        self._part = XmlPart(partname, FOOTNOTES_CONTENT_TYPE, element, package)
        document.part.relate_to(self._part, RT.FOOTNOTES)

    def add_footnote(self, paragraph, footnote_text: str, font_name: str = "Times New Roman") -> int:
        """
        Appends a footnote reference mark at the end of `paragraph` and adds
        the corresponding note text to the document's footnotes part.
        Returns the footnote's numeric id.
        """
        fid = self._next_id
        self._next_id += 1

        # --- Build the footnote entry itself (word/footnotes.xml) ---
        fn = OxmlElement("w:footnote")
        fn.set(qn("w:id"), str(fid))

        note_p = OxmlElement("w:p")

        # Reference mark (superscript number) at the start of the footnote text
        r_marker = OxmlElement("w:r")
        rpr_marker = OxmlElement("w:rPr")
        rfonts_marker = OxmlElement("w:rFonts")
        rfonts_marker.set(qn("w:ascii"), font_name)
        rfonts_marker.set(qn("w:hAnsi"), font_name)
        va = OxmlElement("w:vertAlign")
        va.set(qn("w:val"), "superscript")
        rpr_marker.append(rfonts_marker)
        rpr_marker.append(va)
        r_marker.append(rpr_marker)
        r_marker.append(OxmlElement("w:footnoteRef"))
        note_p.append(r_marker)

        # Footnote body text (10pt, same font family as the document)
        r_text = OxmlElement("w:r")
        rpr_text = OxmlElement("w:rPr")
        rfonts_text = OxmlElement("w:rFonts")
        rfonts_text.set(qn("w:ascii"), font_name)
        rfonts_text.set(qn("w:hAnsi"), font_name)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "20")  # 10pt, in half-points
        rpr_text.append(rfonts_text)
        rpr_text.append(sz)
        r_text.append(rpr_text)
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = " " + footnote_text
        r_text.append(t)
        note_p.append(r_text)

        fn.append(note_p)
        self._part.element.append(fn)

        # --- Insert the reference mark into the body paragraph ---
        run = paragraph.add_run()
        run.font.superscript = True
        run.font.name = font_name
        ref = OxmlElement("w:footnoteReference")
        ref.set(qn("w:id"), str(fid))
        run._r.append(ref)

        return fid

    @property
    def count(self) -> int:
        return self._next_id - 1
