# CLAUDE.md — Autonomous Career Engine (ACE) Reference

Autonomous AI-driven career orchestration engine created by **Ahmet Halit Ünsal** (`github.com/aunsal89/ACE`).

---

## Environment & Commands

- **Python Environment:** `/home/nsl/miniconda3/envs/lnxenv/bin/python`
- **Dependencies:** `pip install -r requirements.txt`

### Common CLI Commands

```bash
# Interactive setup & onboarding wizard
python run.py setup

# Run end-to-end pipeline (Sourcing -> AI Scoring -> Dossier Drafting -> Dashboard)
python run.py pipeline
python run.py pipeline --refresh-models
python run.py pipeline --dry-run

# Import / parse candidate CV (.pdf, .md, .txt)
python run.py import-cv path/to/cv.pdf

# Manage candidate profiles
python run.py tenant list
python run.py tenant switch <tenant_id>
python run.py tenant show [tenant_id]
python run.py tenant create

# Review dashboard & listings
python run.py dashboard
python run.py list-jobs --status QUEUED
python run.py status

# Staged dossier actions
python run.py stage <job_id>
python run.py approve <job_id>
python run.py reject <job_id>

# Testing & diagnostics
pytest tests/
python run.py test-notify
python run.py refresh-models
```

---

## Key Technical Invariants

1. **Path Resolution:** All paths are resolved dynamically via `src.config.PROJECT_ROOT = Path(__file__).resolve().parent.parent`. No hardcoded `/home/nsl` paths in source modules.
2. **Multi-Tenant Device Isolation:** Candidate profiles live in `config/tenants/<tenant_id>/` with their own `sources/` (`Experience.md`, `Education.md`, `Toolbox.md`, `Summary.md`).
3. **LLM Client & Dynamic OpenRouter:**
   - Evaluates opportunities with Gemini (`gemini-2.5-flash`), dynamic OpenRouter free-tier ranking cascade, Anthropic, OpenAI, or deterministic rule evaluation.
   - Pydantic schema validation (`OpportunityEvaluationSchema`) with automatic json repair and bounds normalization.
4. **Staged Dossiers in `/inbox/`:**
   - Publication-quality PDFs generated via `render_markdown_to_pdf` (`fpdf2`).
   - Staged alongside `Job_Details.md` and `LinkedIn_Guidance.md`.
5. **Review Dashboard (`inbox/index.html`):**
   - Self-contained single-file HTML report with interactive SVG charts, Boolean search, and action triggers.
