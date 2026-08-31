"""
Autonomous Career Engine (ACE) - PDF & Document CV Parser.
Extracts raw text from PDF/Markdown/Text CVs and converts them into structured
Markdown sources of truth (Experience.md, Education.md, Toolbox.md, Summary.md).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

from src.utils.logger import logger, console


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract raw text from a PDF document using pypdf."""
    p = Path(pdf_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"PDF file not found: {p}")

    if not PYPDF_AVAILABLE:
        raise ImportError("pypdf is required for PDF CV parsing. Install via `pip install pypdf`.")

    reader = PdfReader(str(p))
    pages_text: List[str] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(text.strip())

    return "\n\n--- Page Break ---\n\n".join(pages_text)


def extract_text_from_file(file_path: str | Path) -> str:
    """Extract raw text from PDF, Markdown, or plain text file."""
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(p)
    elif suffix in (".md", ".txt", ".markdown"):
        return p.read_text(encoding="utf-8", errors="replace")
    else:
        # Fallback to UTF-8 text read
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raise ValueError(f"Unsupported file format '{suffix}': {e}")


def extract_contact_info_regex(text: str) -> Dict[str, Optional[str]]:
    """Extract email, phone, and links using regex pattern heuristics."""
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    email = email_match.group(0) if email_match else None

    phone_match = re.search(r"(\+?\d{1,3}[\s\-]?)?(\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}", text)
    phone = phone_match.group(0) if phone_match else None

    linkedin_match = re.search(r"https?://(?:www\.)?linkedin\.com/in/[\w\-]+", text)
    linkedin = linkedin_match.group(0) if linkedin_match else None

    github_match = re.search(r"https?://(?:www\.)?github\.com/[\w\-]+", text)
    github = github_match.group(0) if github_match else None

    return {
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
    }


def parse_cv_heuristic(text: str, candidate_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic rule-based CV parser that segments raw text into structured sections:
    Experience, Education, Toolbox/Skills, and Summary.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    contact = extract_contact_info_regex(text)

    experience_lines: List[str] = []
    education_lines: List[str] = []
    skills_lines: List[str] = []
    summary_lines: List[str] = []

    current_section = "summary"

    # Section header patterns
    exp_pattern = re.compile(r"^(experience|work experience|professional experience|employment history|career history|work history)\b", re.I)
    edu_pattern = re.compile(r"^(education|academic background|qualifications|degrees|academics)\b", re.I)
    skills_pattern = re.compile(r"^(skills|technical skills|skills & competencies|toolbox|core competencies|technologies)\b", re.I)
    summary_pattern = re.compile(r"^(summary|profile|about me|professional summary|executive summary)\b", re.I)

    for line in lines:
        if line.startswith("--- Page Break ---"):
            continue

        clean_line = line.strip("#* :")
        if exp_pattern.match(clean_line):
            current_section = "experience"
            continue
        elif edu_pattern.match(clean_line):
            current_section = "education"
            continue
        elif skills_pattern.match(clean_line):
            current_section = "skills"
            continue
        elif summary_pattern.match(clean_line):
            current_section = "summary"
            continue

        if current_section == "experience":
            experience_lines.append(line)
        elif current_section == "education":
            education_lines.append(line)
        elif current_section == "skills":
            skills_lines.append(line)
        elif current_section == "summary":
            summary_lines.append(line)

    name = candidate_name or (lines[0] if lines else "Candidate Name")

    exp_md = "# Professional Experience\n\n" + ("\n".join(experience_lines) if experience_lines else "Experience details extracted from CV.")
    edu_md = "# Education\n\n" + ("\n".join(education_lines) if education_lines else "Education details extracted from CV.")
    skills_md = "# Technical Skills & Competencies\n\n" + ("\n".join(skills_lines) if skills_lines else "Technical skills extracted from CV.")
    summary_md = "# Professional Summary\n\n" + ("\n".join(summary_lines[:10]) if summary_lines else "Executive summary.")

    return {
        "metadata": {
            "name": name,
            "email": contact.get("email"),
            "phone": contact.get("phone"),
            "linkedin": contact.get("linkedin"),
            "github": contact.get("github"),
        },
        "sections": {
            "Experience.md": exp_md,
            "Education.md": edu_md,
            "Toolbox.md": skills_md,
            "Summary.md": summary_md,
        }
    }


def parse_cv_with_llm(text: str, candidate_name: Optional[str] = None, llm_client: Any = None) -> Dict[str, Any]:
    """
    Use Generative AI (Gemini / OpenRouter / Claude / OpenAI) to extract clean, structured Markdown sections.
    Falls back to parse_cv_heuristic if LLM is unavailable.
    """
    if llm_client is None:
        try:
            from src.scoring.llm_client import LLMScoringClient
            llm_client = LLMScoringClient()
        except Exception:
            return parse_cv_heuristic(text, candidate_name)

    prompt = f"""You are an expert executive resume parser. Analyze the following raw CV text and segment it into structured Markdown sections.

Return ONLY a valid JSON object matching this exact schema:
{{
  "candidate_name": "Full Name",
  "email": "email@example.com or null",
  "phone": "+123456789 or null",
  "location": "City, Country or null",
  "linkedin": "https://linkedin.com/in/... or null",
  "github": "https://github.com/... or null",
  "target_titles": ["Title 1", "Title 2", "Title 3"],
  "core_competencies": ["Skill 1", "Skill 2", "Skill 3", "Skill 4", "Skill 5"],
  "experience_markdown": "# Professional Experience\\n\\n### Role | Company\\n* Details...",
  "education_markdown": "# Education\\n\\n**Degree** | Institution | Year",
  "skills_markdown": "# Technical Skills\\n\\n* **Category:** Skill 1, Skill 2",
  "summary_markdown": "# Summary\\n\\nHigh-impact executive summary..."
}}

RAW CV TEXT:
\"\"\"
{text[:12000]}
\"\"\"
"""

    try:
        # Check if active LLM is available
        response_text = None
        if hasattr(llm_client, "call_raw_prompt"):
            response_text = llm_client.call_raw_prompt(prompt)

        if not response_text:
            return parse_cv_heuristic(text, candidate_name)

        clean_json = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.MULTILINE)
        clean_json = re.sub(r"^```\s*", "", clean_json.strip(), flags=re.MULTILINE)
        clean_json = clean_json.strip("` \n")

        data = json.loads(clean_json)
        return {
            "metadata": {
                "name": data.get("candidate_name") or candidate_name or "Candidate Name",
                "email": data.get("email"),
                "phone": data.get("phone"),
                "location": data.get("location") or "Remote / Anywhere",
                "linkedin": data.get("linkedin"),
                "github": data.get("github"),
                "target_titles": data.get("target_titles", []),
                "core_competencies": data.get("core_competencies", []),
            },
            "sections": {
                "Experience.md": data.get("experience_markdown") or "# Professional Experience\n\nDetails.",
                "Education.md": data.get("education_markdown") or "# Education\n\nAcademic background.",
                "Toolbox.md": data.get("skills_markdown") or "# Technical Skills\n\nSkills list.",
                "Summary.md": data.get("summary_markdown") or "# Summary\n\nExecutive summary.",
            }
        }
    except Exception as e:
        logger.warning(f"LLM CV parsing encountered error, falling back to heuristic parser: {e}")
        return parse_cv_heuristic(text, candidate_name)


def save_parsed_cv_to_tenant(
    tenant_dir: Path,
    parsed_data: Dict[str, Any]
) -> Dict[str, Path]:
    """Write parsed markdown sections into tenant sources directory."""
    sources_dir = tenant_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: Dict[str, Path] = {}
    for filename, content in parsed_data.get("sections", {}).items():
        file_path = sources_dir / filename
        file_path.write_text(content.strip() + "\n", encoding="utf-8")
        saved_paths[filename] = file_path

    return saved_paths
