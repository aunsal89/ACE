"""Clean, Unicode-enabled PDF rendering engine using fpdf2 for tailored Resumes and Cover Letters."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Silence benign OpenType 1904 vs 1970 epoch fontTools warnings from system TTF headers
logging.getLogger("fontTools.ttLib.tables._h_e_a_d").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)

LATO_REGULAR = "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
LATO_BOLD = "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"
LATO_ITALIC = "/usr/share/fonts/truetype/lato/Lato-Italic.ttf"


class DocumentPDF(FPDF):
    """Custom styled PDF document for executive CVs and Cover Letters."""

    def __init__(self, title_text: str = "Executive Application Document"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.doc_title = title_text
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(18, 18, 18)
        self.font_family = "Helvetica"

        # Register Unicode Lato Font if available
        if os.path.exists(LATO_REGULAR) and os.path.exists(LATO_BOLD):
            self.add_font("Lato", "", LATO_REGULAR)
            self.add_font("Lato", "B", LATO_BOLD)
            if os.path.exists(LATO_ITALIC):
                self.add_font("Lato", "I", LATO_ITALIC)
            self.font_family = "Lato"

    def header(self):
        self.set_font(self.font_family, "B", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, self.doc_title.upper(), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)
        self.set_draw_color(220, 220, 220)
        self.line(18, 15, 192, 15)
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font(self.font_family, "I" if self.font_family == "Lato" and os.path.exists(LATO_ITALIC) else "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, f"Page {self.page_no()}", align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)


def clean_text_for_pdf(text: str) -> str:
    """Normalize typography symbols for PDF generation."""
    # Replace em/en dashes, smart quotes, bullets
    t = text.replace("—", " - ").replace("–", " - ")
    t = t.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = t.replace("•", "-").replace("…", "...")
    return t


def render_markdown_to_pdf(markdown_text: str, output_pdf_path: Path | str, doc_title: str = "Ahmet Halit Ünsal - Application") -> Path:
    """
    Render structured Markdown into a styled, professional PDF document.
    """
    out_path = Path(output_pdf_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = DocumentPDF(title_text=doc_title)
    font_name = pdf.font_family
    pdf.add_page()

    lines = markdown_text.splitlines()

    for line in lines:
        raw_line = clean_text_for_pdf(line.strip())
        if not raw_line:
            pdf.ln(3)
            continue

        # H1 Heading
        if raw_line.startswith("# "):
            text = raw_line.replace("# ", "").strip()
            pdf.set_font(font_name, "B", 15)
            pdf.set_text_color(20, 40, 80)
            pdf.cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

        # H2 Heading
        elif raw_line.startswith("## "):
            text = raw_line.replace("## ", "").strip()
            pdf.set_font(font_name, "B", 11)
            pdf.set_text_color(30, 60, 120)
            pdf.cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(200, 210, 230)
            pdf.line(pdf.get_x(), pdf.get_y(), 192, pdf.get_y())
            pdf.ln(2)

        # H3 Heading
        elif raw_line.startswith("### "):
            text = raw_line.replace("### ", "").strip()
            pdf.set_font(font_name, "B", 10)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Bullet items
        elif raw_line.startswith("* ") or raw_line.startswith("- "):
            bullet_text = raw_line[2:].strip()
            clean_text = re.sub(r"\*\*(.*?)\*\*", r"\1", bullet_text)

            pdf.set_font(font_name, "", 9.5)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(5, 5, "-", align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.multi_cell(0, 5, f"  {clean_text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

        # Normal paragraphs
        else:
            clean_text = re.sub(r"\*\*(.*?)\*\*", r"\1", raw_line)
            clean_text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", clean_text)

            pdf.set_font(font_name, "", 9.5)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5, clean_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

    pdf.output(str(out_path))
    return out_path
