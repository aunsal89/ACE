# Career Engine & Portfolio Synchronizer

Autonomous career orchestration system, multi-channel job discovery, deduplication engine, and personal portfolio synchronizer for **Ahmet Halit Ünsal** ([ahmethalitunsal.com](https://www.ahmethalitunsal.com)).

## Architecture Overview

- **Sourcing Layer (`src/sourcing/`):** Multi-portal scrapers (Baykar, Aselsan, Vizyoner Genç, TUSAŞ, Roketsan) and global APIs (Google Jobs, Apify LinkedIn).
- **State & Deduplication (`src/database/`):** SQLite (WAL mode) schema tracking job listings through `DISCOVERED`, `EVALUATED`, `QUEUED`, `APPLIED`, `REJECTED` lifecycle states with SHA-256 deduplication hashing.
- **Scoring Engine (`src/scoring/`):** Dual-track matching against Track A (Embedded Software Leadership/MBD) and Track B (Quantitative Developer/Algorithmic Trading AURA).
- **Application Generator (`src/applicator/`):** Generative drafting of tailored Markdown/PDF resumes and cover letters into `/inbox/` staging area for Human-in-the-Loop review.
- **Multi-Tenant Ready (`config/tenants/`):** Clean separation of tenant criteria from orchestrator core.

## CLI Usage

```bash
# Set up database & register tenant
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py init-db

# Check status and opportunity counts
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py status

# Inspect active tenant criteria
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py show-tenant

# Test deduplication hashing normalization
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py test-dedup

# List jobs
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py list-jobs --status QUEUED
```

## Running Tests

```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python -m unittest discover -s tests
```
