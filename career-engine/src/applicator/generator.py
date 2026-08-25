"""Tailored Application Asset Generator (Markdown + PDF Staging in /inbox/)."""

from __future__ import annotations

import re
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
from src.utils.logger import console, logger
from src.utils.pdf import render_markdown_to_pdf


class ApplicationGenerator(BaseApplicator):
    """
    Generates tailored Resumes, Cover Letters, and LinkedIn guidance prompts
    staged into /inbox/ for Human-in-the-Loop approval.
    """

    def __init__(self, config: Optional[EngineConfig] = None, tenant: Optional[TenantProfile] = None):
        self.config = config or load_engine_config()
        self.tenant = tenant or load_tenant_profile(config=self.config)
        super().__init__(self.tenant, self.config.engine.inbox_dir)
        self.repo = JobRepository(self.config.database.db_path)
        self._load_master_content()

    def _load_master_content(self) -> None:
        """Load authoritative content sources of truth."""
        cv_path = self.tenant.sources_of_truth.cv_markdown
        if cv_path and cv_path.exists():
            self.master_cv = cv_path.read_text(encoding="utf-8")
        else:
            self.master_cv = "# Professional Experience\n\n15+ years experience in embedded systems and leadership."

    def generate_package(self, job: JobListing, evaluation: ScoringEvaluation) -> ApplicationPackageCreate:
        """Generate tailored Resume.md, Cover_Letter.md, LinkedIn_Guidance.md, and PDFs."""
        comp_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.company).strip("_").lower()
        job_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.title[:20]).strip("_").lower()
        package_dir = self.inbox_dir / f"{comp_slug}_{job_slug}_{job.id[:8]}"
        package_dir.mkdir(parents=True, exist_ok=True)

        track = evaluation.track

        # 1. Draft Tailored Resume Markdown
        resume_md = self._draft_tailored_resume(job, evaluation)
        resume_md_path = package_dir / f"Resume_{self.tenant.name.replace(' ', '_')}_{comp_slug}.md"
        resume_md_path.write_text(resume_md, encoding="utf-8")

        # 2. Render Resume PDF
        resume_pdf_path = package_dir / f"Resume_{self.tenant.name.replace(' ', '_')}_{comp_slug}.pdf"
        render_markdown_to_pdf(resume_md, resume_pdf_path, doc_title=f"{self.tenant.name} - Executive Resume")

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
        """Synthesize tailored executive CV matching JD priorities."""
        t = self.tenant
        ta = t.tracks.track_a
        tb = t.tracks.track_b

        if evaluation.track == "TRACK_A":
            summary = (
                f"Senior Engineering Leader & Chief Embedded Systems Architect with 15+ years professional experience and "
                f"8+ years directorship managing cross-functional teams up to 30 engineers. Deep technical mastery in Model-Based Design "
                f"(MATLAB/Simulink/Stateflow), EV Powertrains (VCU/MCU/Inverters/BMS), PMSM FOC motor control, AUTOSAR, and ISO 26262 ASIL D compliance."
            )
            skills = ", ".join(ta.core_competencies[:10])
        else:
            summary = (
                f"Quantitative Software Engineer & Automated Trading Architect. Creator of AURA (24/7 automated spot & equity execution engine). "
                f"Expert in walk-forward optimization, successive halving, multi-layer risk management, PAXG defensive overlays, and high-throughput Python/C++ architectures."
            )
            skills = ", ".join(tb.core_competencies[:8])

        return f"""# {t.name}
**{t.location_current}** | **Email:** {t.email} | **Phone:** {t.phone}  
**Website:** {t.links.website} | **GitHub:** {t.links.github} | **LinkedIn:** {t.links.linkedin}

---

## Executive Summary
{summary}

## Tailored Competencies for {job.company} ({job.title})
* **Core Technical Stack:** {skills}
* **Product Showcase:** EduTrace ({t.product_engineering_showcase.url if t.product_engineering_showcase else 'edutrace.net'}) & AURA ({t.links.aura_showcase})

---

{self.master_cv}
"""

    def _draft_cover_letter(self, job: JobListing, evaluation: ScoringEvaluation) -> str:
        """Draft tailored, direct, metric-driven cover letter."""
        t = self.tenant
        if evaluation.track == "TRACK_A":
            body = (
                f"I am writing to express my strong interest in the **{job.title}** position at **{job.company}**.\n\n"
                f"With over 15 years of professional engineering experience—including 8+ years leading multi-disciplinary engineering teams of up to 30 engineers—my background directly aligns with your requirements for high-reliability embedded software, Model-Based Design (MBD), and powertrain control systems.\n\n"
                f"Throughout my career across defense electronics and automotive platforms, I have directed end-to-end architectures from concept to dyno characterization and mass production, adhering strictly to ISO 26262 ASIL D, ASPICE, and AUTOSAR standards.\n\n"
                f"I would welcome the opportunity to discuss how my leadership and technical ownership can drive the next milestones for {job.company}."
            )
        else:
            body = (
                f"I am writing to present my candidacy for the **{job.title}** role at **{job.company}**.\n\n"
                f"As the architect of **AURA** (https://www.auratrading.org/), a proprietary 24/7 algorithmic execution system spanning crypto spot and equity markets, I have developed rigorous walk-forward optimization pipelines, successive halving parameters, dynamic risk regime detectors, and low-latency exchange interfaces in Python 3.11 and C++.\n\n"
                f"I am eager to bring this proven algorithmic engineering rigour to {job.company}'s quantitative strategies."
            )

        return f"""# Cover Letter

**Candidate:** {t.name}  
**Contact:** {t.email} | {t.phone} | {t.location_current}  
**Position:** {job.title}  
**Target Organization:** {job.company} ({job.location or 'Global'})  

---

Dear Hiring Committee at {job.company},

{body}

Sincerely,  
**{t.name}**  
{t.links.website}
"""

    def _draft_linkedin_guidance(self, job: JobListing, evaluation: ScoringEvaluation) -> str:
        """Step-by-step guidance for manual LinkedIn updates."""
        t = self.tenant
        if evaluation.track == "TRACK_A":
            headline = f"Director of Embedded Software & MBD | Automotive & Defense Electronics | ISO 26262 ASIL D | Team Leadership (30+ Eng)"
            keywords = "Model-Based Design, MATLAB/Simulink, ISO 26262, AUTOSAR, PMSM Motor Control, EV Powertrain, Engineering Management"
        else:
            headline = f"Quantitative Software Engineer | Algorithmic Trading Systems (AURA) | High-Performance Python & C++ | Risk Regimes"
            keywords = "Quantitative Development, Algorithmic Execution, Walk-Forward Optimization, CCXT, Risk Management, Systemd"

        return f"""# LinkedIn Guidance & Keyword Optimization for {job.company}

### 1. Recommended Headline:
`{headline}`

### 2. Priority Skills to Spotlight on LinkedIn:
- {keywords}

### 3. Tailored Connection Note / InMail Copy:
"Hello, I noticed {job.company}'s open role for {job.title}. With 15+ years in embedded systems leadership / quantitative software engineering, I'd welcome the chance to connect and share insights on system architecture and scaling."
"""

    def draft_queued_jobs(self, job_id: Optional[str] = None) -> List[ApplicationPackage]:
        """Draft application packages for all QUEUED jobs (or specific job ID)."""
        if job_id:
            job = self.repo.get_job_by_id(job_id)
            jobs = [job] if job else []
        else:
            jobs = self.repo.list_jobs(status=JobStatus.QUEUED, limit=50)

        if not jobs:
            console.print("[yellow]No QUEUED jobs found ready for drafting.[/yellow]")
            return []

        console.print(f"[bold cyan]Drafting Application Packages in /inbox/ for {len(jobs)} QUEUED opportunities...[/bold cyan]")
        packages: List[ApplicationPackage] = []

        for j in jobs:
            evals = self.repo.get_evaluations_for_job(j.id)
            if not evals:
                # generate evaluation if missing
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
                f"[bold]Resume PDF:[/bold] {pkg.resume_pdf_path}\n"
                f"[bold]Cover Letter PDF:[/bold] {pkg.cover_letter_pdf_path}\n"
                f"[bold]LinkedIn Guidance:[/bold] {pkg.linkedin_prompt_path}",
                title=f"Staged Application ({pkg.track})",
                border_style="green"
            ))

        return packages
