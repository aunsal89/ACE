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
            self.master_cv = "# Professional Experience\n\n15+ years experience in embedded systems and leadership."

        edu_path = self.tenant.sources_of_truth.education_markdown
        if edu_path and edu_path.exists():
            self.master_education = edu_path.read_text(encoding="utf-8")
        else:
            self.master_education = (
                "**MSc, Advanced Control Theory** | Istanbul Technical University | 2014 – 2016\n\n"
                "**BSc, Electrical & Computer Engineering** | Iowa State University | 2007 – 2011"
            )

    def generate_package(self, job: JobListing, evaluation: ScoringEvaluation) -> ApplicationPackageCreate:
        """Generate tailored Resume.md, Cover_Letter.md, LinkedIn_Guidance.md, Job_Details.md, and PDFs."""
        track = evaluation.track
        track_folder = "track_a_embedded" if track == "TRACK_A" else "track_b_quant"
        date_folder = datetime.now().strftime("%Y-%m-%d")

        comp_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.company).strip("_").lower()
        job_slug = re.sub(r"[^a-zA-Z0-9]", "_", job.title[:20]).strip("_").lower()
        package_dir = self.inbox_dir / track_folder / date_folder / f"{comp_slug}_{job_slug}_{job.id[:8]}"
        package_dir.mkdir(parents=True, exist_ok=True)

        # 1. Draft Tailored Resume Markdown (with Experience and Education)
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

        # Clean education section for markdown resume
        edu_body = self.master_education.replace("# Education", "").strip()

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

---

## Education

{edu_body}
"""

    def _draft_cover_letter(self, job: JobListing, evaluation: ScoringEvaluation) -> str:
        """Draft tailored, comprehensive, metric-driven executive cover letter."""
        t = self.tenant
        if evaluation.track == "TRACK_A":
            body = (
                f"I am writing to express my strong interest in the **{job.title}** position at **{job.company}**.\n\n"
                f"With over 15 years of professional engineering experience—including 8+ years leading and directing multi-disciplinary engineering organizations of up to 30 engineers across 4 team leads—my background directly aligns with {job.company}'s requirements for high-reliability embedded software architecture, Model-Based Design (MBD), and mission-critical powertrain controls.\n\n"
                f"Throughout my leadership tenure across automotive and defense electronics programs (NISO Technology, ECEMTAG, TÜBİTAK, TÜMOSAN), I have directed full product lifecycles from initial concept and dynamic modeling to dyno characterization and mass production. I maintain strict enforcement of **ISO 26262 ASIL D functional safety**, **ASPICE Level 2/3 processes**, **UN R155/R156 cybersecurity (CSMS)**, and **AUTOSAR** layered architectures across FreeRTOS and bare-metal platforms.\n\n"
                f"On the technical front, I bring hands-on mastery in MATLAB/Simulink/Stateflow physical modeling, PMSM/IPMSM Field-Oriented Control (FOC, MTPA, flux-weakening), and complex EV powertrain controls (VCU, MCU, Traction Inverters, OBC, BMS). Complementing this is extensive experience establishing automated Hardware-in-the-Loop (HIL) simulation testbenches (dSpace MABX, Lauterbach Trace32) and Git-based CI/CD pipelines that dramatically compress verification cycles and eliminate integration bottlenecks.\n\n"
                f"Beyond embedded systems, my end-to-end technical leadership is demonstrated in platforms like EduTrace (edutrace.net), highlighting my ability to scale complex architectures and bridge software, hardware, and product teams. I would welcome the opportunity to discuss how my technical ownership, executive leadership, and delivery focus can accelerate the engineering milestones at {job.company}."
            )
        else:
            body = (
                f"I am writing to present my candidacy for the **{job.title}** position at **{job.company}**.\n\n"
                f"As the architect and developer of **AURA** (https://www.auratrading.org/), a proprietary 24/7 automated algorithmic trading and execution architecture spanning live crypto spot and equity markets, I combine deep quantitative software engineering with rigorous mathematical modeling and high-throughput system design.\n\n"
                f"My quantitative background encompasses building continuous walk-forward optimization pipelines, successive halving parameter selection, multi-regime volatility detection, and multi-layered risk management engines featuring dynamic stop-loss/take-profit triggers and PAXG defensive overlays. I architect low-latency execution pipelines using modern Python 3.11 (AsyncIO, NumPy, pandas) and C++, interfacing directly with high-frequency exchange APIs (CCXT, WebSockets) and maintaining 24/7 reliability via Linux systemd daemons and telemetry watchdogs.\n\n"
                f"In addition to quantitative finance, my track record in full-cycle product engineering (e.g., EduTrace at https://edutrace.net) underscores my disciplined approach to data structures, offline-first local state management, and multi-model AI workflows. I maintain rigorous test harnesses and analytical telemetry to ensure flawless runtime execution under high-stress market conditions.\n\n"
                f"I am eager to leverage this proven algorithmic engineering rigour, quantitative modeling acumen, and low-latency infrastructure design to drive outsized returns and system resilience for {job.company}'s quantitative strategies."
            )

        return f"""# Cover Letter

**Candidate:** {t.name}  
**Contact:** {t.email} | {t.phone} | {t.location_current}  
**Position:** {job.title}  
**Target Organization:** {job.company} ({job.location or 'Global'})  
**Job URL:** {job.url or 'N/A'}  

---

Dear Hiring Team & Leadership at {job.company},

{body}

Sincerely,  
**{t.name}**  
{t.links.website} | {t.links.linkedin} | {t.links.github}
"""

    def _draft_job_details(self, job: JobListing, evaluation: ScoringEvaluation, comp_slug: str) -> str:
        """Create a comprehensive Job_Details.md containing metadata, URLs, review commands, and evaluation notes."""
        t = self.tenant
        return f"""# Job Overview & Review Actions: {job.title}

## Target Organization & Metadata
* **Company:** {job.company}
* **Position:** {job.title}
* **Location:** {job.location or 'Not specified'} {'(Remote)' if job.is_remote else ''}
* **Source:** {job.source}
* **Discovered At:** {job.discovered_at.strftime('%Y-%m-%d %H:%M:%S') if job.discovered_at else 'N/A'}
* **Assigned Track:** {job.assigned_track.value}
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
                title=f"Staged Application ({pkg.track})",
                border_style="green"
            ))

        # Regenerate inbox dashboard
        generate_inbox_dashboard(config=self.config, tenant=self.tenant)
        console.print("[bold green]✓ Inbox review dashboard updated at inbox/index.html[/bold green]")

        return packages

