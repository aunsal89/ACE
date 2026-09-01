"""Tailored Application Asset Generator (Markdown + PDF Staging in /inbox/)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.panel import Panel

from src.applicator.base import BaseApplicator
from src.config import EngineConfig, TenantProfile, load_engine_config, load_tenant_profile
from src.database.models import (
    ApplicationPackage,
    ApplicationPackageCreate,
    JobListing,
    JobStatus,
    PackageStatus,
    ScoringEvaluation,
    TrackType,
)
from src.database.repository import JobRepository
from src.utils.dashboard import generate_inbox_dashboard
from src.utils.logger import console, logger
from src.utils.pdf import render_markdown_to_pdf


class ApplicationGenerator(BaseApplicator):
    """
    Generates tailored Resumes, Cover Letters, Job Details overview,
    and LinkedIn guidance prompts staged into /inbox/ for Human-in-the-Loop approval.
    """

    def __init__(self, config: Optional[EngineConfig] = None, tenant: Optional[TenantProfile] = None):
        self.config = config or load_engine_config()
        self.tenant = tenant or load_tenant_profile(config=self.config)
        super().__init__(self.tenant, self.config.engine.inbox_dir)
        self.repo = JobRepository(self.config.database.db_path)
        self._load_master_content()

    def _load_master_content(self) -> None:
        """Load authoritative content sources of truth (Experience and Education)."""
        cv_path = self.tenant.sources_of_truth.cv_markdown
        if cv_path and cv_path.exists():
            self.master_cv = cv_path.read_text(encoding="utf-8")
        else:
            self.master_cv = "# Professional Experience\n\nExperience and technical track record."

        edu_path = self.tenant.sources_of_truth.education_markdown
        if edu_path and edu_path.exists():
            self.master_education = edu_path.read_text(encoding="utf-8")
        else:
            self.master_education = "# Education\n\nAcademic background and certifications."

    def generate_package(self, job: JobListing, evaluation: ScoringEvaluation) -> ApplicationPackageCreate:
        """Generate tailored Resume.md, Cover_Letter.md, LinkedIn_Guidance.md, Job_Details.md, and PDFs."""
        track = "GENERAL"
        date_folder = datetime.now().strftime("%Y-%m-%d")

        comp_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.company).strip("_").lower()
        job_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.title[:20]).strip("_").lower()
        package_dir = self.inbox_dir / self.tenant.tenant_id / date_folder / f"{comp_slug}_{job_slug}_{job.id[:8]}"
        package_dir.mkdir(parents=True, exist_ok=True)

        # 1. Draft Tailored Resume Markdown (with Experience and Education)
        resume_md = self._draft_tailored_resume(job, evaluation)
        resume_md_path = package_dir / f"Resume_{self.tenant.name.replace(' ', '_')}_{comp_slug}.md"
        resume_md_path.write_text(resume_md, encoding="utf-8")

        # 2. Render Resume PDF
        resume_pdf_path = package_dir / f"Resume_{self.tenant.name.replace(' ', '_')}_{comp_slug}.pdf"
        render_markdown_to_pdf(resume_md, resume_pdf_path, doc_title=f"{self.tenant.name} - Resume")

        # 3. Draft Tailored Cover Letter Markdown
        cover_md = self._draft_cover_letter(job, evaluation)
        cover_md_path = package_dir / f"Cover_Letter_{comp_slug}.md"
        cover_md_path.write_text(cover_md, encoding="utf-8")

        # 4. Render Cover Letter PDF
        cover_pdf_path = package_dir / f"Cover_Letter_{comp_slug}.pdf"
        render_markdown_to_pdf(cover_md, cover_pdf_path, doc_title=f"{self.tenant.name} - Cover Letter")

        # 5. Draft LinkedIn Guidance Prompts
        linkedin_md = self._draft_linkedin_guidance(job, evaluation)
        linkedin_path = package_dir / "LinkedIn_Guidance.md"
        linkedin_path.write_text(linkedin_md, encoding="utf-8")

        # 6. Draft Comprehensive Job Details & Action Commands
        details_md = self._draft_job_details(job, evaluation, comp_slug)
        details_path = package_dir / "Job_Details.md"
        details_path.write_text(details_md, encoding="utf-8")

        return ApplicationPackageCreate(
            job_id=job.id,
            tenant_id=self.tenant.tenant_id,
            track=track,
            resume_md_path=str(resume_md_path),
            resume_pdf_path=str(resume_pdf_path),
            cover_letter_md_path=str(cover_md_path),
            cover_letter_pdf_path=str(cover_pdf_path),
            linkedin_prompt_path=str(linkedin_path),
            status=PackageStatus.GENERATED,
            notes=f"Generated for {job.company} - {job.title} (Score: {evaluation.overall_score:.1f})"
        )

    def _draft_tailored_resume(self, job: JobListing, evaluation: ScoringEvaluation) -> str:
        """Synthesize tailored executive CV matching JD priorities including Education at the end."""
        t = self.tenant
        prefs = t.preferences

        # Collect contact links
        links_parts = []
        if t.links.website:
            links_parts.append(f"**Website:** {t.links.website}")
        if t.links.linkedin:
            links_parts.append(f"**LinkedIn:** {t.links.linkedin}")
        if t.links.github:
            links_parts.append(f"**GitHub:** {t.links.github}")
        if t.links.portfolio_showcase:
            links_parts.append(f"**Portfolio:** {t.links.portfolio_showcase}")
        links_line = " | ".join(links_parts) if links_parts else ""

        skills = ", ".join(track_profile.core_competencies[:10]) if track_profile.core_competencies else "Domain Architecture, Engineering Execution, High-Impact Delivery"
        
        exp_reqs = getattr(track_profile, "experience_requirements", None)
        years_exp = getattr(exp_reqs, "min_total_years", 5) if exp_reqs else 5

        summary = (
            f"Accomplished {job.title} professional with {years_exp}+ years of proven engineering expertise. "
            f"Demonstrated track record of technical delivery, scalable architecture design, and domain leadership "
            f"delivering high-reliability solutions for {job.company}."
        )

        edu_body = self.master_education.replace("# Education", "").strip()

        return f"""# {t.name}
**{t.location_current}** | **Email:** {t.email}{f' | **Phone:** {t.phone}' if t.phone else ''}  
{links_line}

---

## Executive Summary
{summary}

## Tailored Competencies for {job.company} ({job.title})
* **Target Role Focus:** {job.title}
* **Core Technical Competencies:** {skills}

---

{self.master_cv}

---

## Education

{edu_body}
"""

    def _draft_cover_letter(self, job: JobListing, evaluation: ScoringEvaluation) -> str:
        """Draft tailored, comprehensive, metric-driven executive cover letter."""
        t = self.tenant
        prefs = t.preferences
        skills = ", ".join(prefs.core_competencies[:6]) if prefs.core_competencies else "system design, technical leadership, and engineering rigor"
        exp_reqs = getattr(prefs, "experience_requirements", None)
        years_exp = getattr(exp_reqs, "min_total_years", 5) if exp_reqs else 5

        body = (
            f"I am writing to express my enthusiastic interest in the **{job.title}** position at **{job.company}**.\n\n"
            f"With over {years_exp} years of dedicated engineering experience, my technical background directly aligns with {job.company}'s requirements. "
            f"Throughout my career, I have focused on building resilient systems, architecting mission-critical platforms, and driving technical ownership from concept to production.\n\n"
            f"My hands-on experience encompasses {skills}. I maintain a disciplined approach to verification, robust architecture, and cross-functional collaboration, ensuring project milestones are met on schedule and with the highest quality standards.\n\n"
            f"I would welcome the opportunity to discuss how my background, technical execution, and dedication can contribute to {job.company}'s engineering objectives."
        )

        links_parts = [p for p in [t.links.website, t.links.linkedin, t.links.github] if p]
        links_footer = " | ".join(links_parts) if links_parts else ""

        return f"""# Cover Letter

**Candidate:** {t.name}  
**Contact:** {t.email}{f' | {t.phone}' if t.phone else ''} | {t.location_current}  
**Position:** {job.title}  
**Target Organization:** {job.company} ({job.location or 'Global'})  
**Job URL:** {job.url or 'N/A'}  

---

Dear Hiring Team & Leadership at {job.company},

{body}

Sincerely,  
**{t.name}**  
{links_footer}
"""

    def _draft_job_details(self, job: JobListing, evaluation: ScoringEvaluation, comp_slug: str) -> str:
        """Create a comprehensive Job_Details.md containing metadata, URLs, review commands, and evaluation notes."""
        t = self.tenant
        assigned_track_str = job.assigned_track.value if hasattr(job.assigned_track, "value") else str(job.assigned_track or "GENERAL")
        return f"""# Job Overview & Review Actions: {job.title}

## Target Organization & Metadata
* **Company:** {job.company}
* **Position:** {job.title}
* **Location:** {job.location or 'Not specified'} {'(Remote)' if job.is_remote else ''}
* **Source:** {job.source}
* **Discovered At:** {job.discovered_at.strftime('%Y-%m-%d %H:%M:%S') if job.discovered_at else 'N/A'}
* **Assigned Track:** {assigned_track_str}
* **Original Job Posting URL:** [{job.url or 'Link'}]({job.url or '#'})

---

## ⚡ Review & Action Commands
To approve or reject this opportunity from the terminal:

```bash
# Approve and mark as APPLIED:
python run.py approve {job.id[:8]}

# Or Reject:
python run.py reject {job.id[:8]}
```

* **Full Job ID:** `{job.id}`
* **Short Job ID:** `{job.id[:8]}`

---

## 🎯 Evaluation & Scoring Analysis
* **Overall Score:** {evaluation.overall_score:.1f} / 100
* **Recommendation:** `{evaluation.recommendation.value}`
* **Fits Criteria:** `{'YES' if evaluation.fits_criteria else 'NO'}`
* **Model Used:** `{evaluation.model_used or 'N/A'}`

### AI Rationale
{evaluation.reasoning or 'N/A'}

---

## 📁 Staged Application Assets in this Folder
* **Resume PDF:** `Resume_{t.name.replace(' ', '_')}_{comp_slug}.pdf`
* **Resume Markdown:** `Resume_{t.name.replace(' ', '_')}_{comp_slug}.md`
* **Cover Letter PDF:** `Cover_Letter_{comp_slug}.pdf`
* **Cover Letter Markdown:** `Cover_Letter_{comp_slug}.md`
* **LinkedIn Guidance:** `LinkedIn_Guidance.md`

---

## 📄 Original Job Description
{job.description_cleaned or job.description_raw or 'No description provided.'}
"""

    def _draft_linkedin_guidance(self, job: JobListing, evaluation: ScoringEvaluation) -> str:
        """Step-by-step guidance for manual LinkedIn updates."""
        t = self.tenant
        prefs = t.preferences
        headline = f"{job.title} | {t.name} | Systems Architecture & Engineering"
        keywords = ", ".join(prefs.core_competencies[:8]) if prefs.core_competencies else "Software Architecture, Systems Engineering, Technical Leadership"

        return f"""# LinkedIn Guidance & Keyword Optimization for {job.company}

### 1. Recommended Headline:
`{headline}`

### 2. Priority Skills to Spotlight on LinkedIn:
- {keywords}

### 3. Tailored Connection Note / InMail Copy:
"Hello, I noticed {job.company}'s open role for {job.title}. With my engineering background, I would welcome the chance to connect and discuss how my experience aligns with your engineering goals."
"""

    def draft_queued_jobs(self, job_id: Optional[str] = None) -> List[ApplicationPackage]:
        """Draft application packages for all QUEUED jobs (or specific job ID), and refresh dashboard."""
        if job_id:
            job = self.repo.get_job_by_id(job_id)
            jobs = [job] if job else []
        else:
            jobs = self.repo.list_jobs(status=JobStatus.QUEUED, limit=50)

        if not jobs:
            console.print("[yellow]No QUEUED jobs found ready for drafting.[/yellow]")
            # Still refresh dashboard to reflect current state
            generate_inbox_dashboard(config=self.config, tenant=self.tenant)
            return []

        console.print(f"[bold cyan]Drafting Application Packages in /inbox/ for {len(jobs)} QUEUED opportunities...[/bold cyan]")
        packages: List[ApplicationPackage] = []

        for j in jobs:
            evals = self.repo.get_evaluations_for_job(j.id)
            if not evals:
                from src.scoring.scorer import OpportunityScorer
                scorer = OpportunityScorer(config=self.config, tenant=self.tenant)
                eval_create = scorer.evaluate(j)
                evaluation = self.repo.save_evaluation(eval_create)
            else:
                evaluation = evals[0]

            pkg_create = self.generate_package(j, evaluation)
            pkg = self.repo.save_application_package(pkg_create)
            packages.append(pkg)

            console.print(Panel(
                f"[bold green]✓ Package Staged in /inbox/:[/bold green] [cyan]{j.company} — {j.title}[/cyan]\n"
                f"[bold]Job ID:[/bold] {j.id[:8]} (Full: {j.id})\n"
                f"[bold]Resume PDF:[/bold] {pkg.resume_pdf_path}\n"
                f"[bold]Cover Letter PDF:[/bold] {pkg.cover_letter_pdf_path}\n"
                f"[bold]Job Details:[/bold] {Path(pkg.resume_md_path).parent / 'Job_Details.md'}\n"
                f"[bold]LinkedIn Guidance:[/bold] {pkg.linkedin_prompt_path}",
                title=f"Staged Application - {j.company}",
                border_style="green"
            ))

        # Regenerate inbox dashboard
        generate_inbox_dashboard(config=self.config, tenant=self.tenant)
        console.print("[bold green]✓ Inbox review dashboard updated at inbox/index.html[/bold green]")

        return packages
