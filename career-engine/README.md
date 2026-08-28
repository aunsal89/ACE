# Career Engine & Portfolio Synchronizer

Autonomous career orchestration system, multi-channel job discovery, deduplication engine, and personal portfolio synchronizer for **Ahmet Halit Ünsal** ([ahmethalitunsal.com](https://www.ahmethalitunsal.com)).

## Architecture Overview

- **Sourcing Layer (`src/sourcing/`):** Multi-portal scrapers (Baykar, Aselsan, Vizyoner Genç, TUSAŞ, Roketsan) and global APIs (Google Jobs, Apify LinkedIn).
- **State & Deduplication (`src/database/`):** SQLite (WAL mode) schema tracking job listings through `DISCOVERED`, `EVALUATED`, `QUEUED`, `APPLIED`, `REJECTED` lifecycle states with SHA-256 deduplication hashing.
- **Scoring Engine (`src/scoring/`):** Dual-track matching against Track A (Embedded Software Leadership/MBD) and Track B (Quantitative Developer/Algorithmic Trading AURA).
- **Application Generator (`src/applicator/`):** Generative drafting of tailored Markdown/PDF resumes (with Education), cover letters (with Job URLs), and `Job_Details.md` into `/inbox/` staging area.
- **Review Dashboard (`src/utils/dashboard.py`):** Standalone, responsive HTML review hub at `inbox/index.html` with real-time filtering, job metadata, one-click terminal commands, and relative paths.
- **Multi-Tenant Ready (`config/tenants/`):** Clean separation of tenant criteria from orchestrator core.

## CLI Usage

```bash
# Full automated sourcing, scoring, drafting, and dashboard pipeline
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py pipeline

# Generate or refresh HTML review dashboard at inbox/index.html
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py dashboard

# Approve a staged job (marks as APPLIED and updates dashboard)
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py approve <job_id>

# Reject a staged job (marks as REJECTED and updates dashboard)
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py reject <job_id>

# Draft application packages for all queued jobs
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py draft

# Check system status and opportunity breakdown
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py status

# List jobs by status or track
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py list-jobs --status QUEUED --track TRACK_A
```

## Running Tests

```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python -m pytest tests
```

