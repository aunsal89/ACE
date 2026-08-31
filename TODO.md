# Autonomous Career Engine (ACE) — Implementation Roadmap & TODO Tracker

> **Repository:** `github.com/aunsal89/ACE`  
> **Author & Architect:** Ahmet Halit Ünsal  
> **License:** GNU Affero General Public License v3.0 (AGPL-3.0)  
> **Status:** Phase 1 in progress

---

## Master Checklist

- [x] **Phase 1: Web Decoupling & Repository Restructuring**
  - [x] Delete `web/` directory and all legacy Astro/React static site artifacts.
  - [x] Remove hardcoded `aunsal` tenant profile and personal static markdown files from repository tracking.
  - [x] Remove `deploy/systemd/` service/timer templates (moving to 100% cross-platform on-demand execution).
  - [x] Promote `career-engine/*` layout (`src/`, `config/`, `data/`, `inbox/`, `tests/`, `run.py`, `docs/`) directly to project root.
  - [x] Create `config/profile.example.yaml` and `config/tenants/.gitkeep`.
  - [x] Update `.gitignore` for multi-tenant dynamic isolation, databases, and staged inbox files.

- [x] **Phase 2: OS-Agnostic Dynamic Path Resolution & Dependencies**
  - [x] Refactor `src/config.py` and `config/config.yaml` to eliminate all hardcoded absolute paths (`/home/nsl/...`), using dynamic `pathlib.Path` relative to project root.
  - [x] Generate comprehensive root `requirements.txt` (`pypdf`, `google-genai`, `pydantic`, `pyyaml`, `rich`, `fpdf2`, `httpx`, `beautifulsoup4`, `requests`, `python-dotenv`, `pytest`, etc.).
  - [x] Verify test suite and module execution in `lnxenv`.

- [x] **Phase 3: Generalized Multi-Tenant Provisioning & Setup Wizard**
  - [x] Implement dynamic tenant discovery & lifecycle in `src/config.py` and `src/cli.py`.
  - [x] Create interactive `python run.py setup` onboarding wizard for `.env` and new tenant profiles.
  - [x] Add `python run.py tenant [list|create|switch|show]` management subcommands.
  - [x] Add default fallback: auto-trigger `create tenant` if no tenants exist.
  - [x] Create annotated `.env.example` with clear guidelines.

- [x] **Phase 4: PDF CV Ingestion & Structured Parser**
  - [x] Implement `src/utils/cv_parser.py` using `pypdf` text extraction.
  - [x] Implement LLM structured extractor (with heuristic regex fallback) to generate `Experience.md`, `Education.md`, `Toolbox.md`, `Summary.md`.
  - [x] Implement `python run.py import-cv <path_to_pdf>` CLI command.
  - [x] Wire CV ingestion into `python run.py setup` and `python run.py tenant create`.

- [x] **Phase 5: Licensing, Legal Protection & Developer Showcase**
  - [x] Create formal `LICENSE` file (GNU AGPL-3.0 with Copyright (c) 2026 Ahmet Halit Ünsal).
  - [x] Integrate developer promotion banner, GitHub repository links, and "💼 Hire the Creator" callouts.
  - [x] Add sponsorship and donation modal (GitHub Sponsors, Buy Me a Coffee, Crypto USDT/BTC/ETH).

- [x] **Phase 6: Executive Review Dashboard Refinement & Smoke Test**
  - [x] Update `src/utils/dashboard.py` to embed developer branding and donation triggers.
  - [x] Conduct end-to-end CLI simulation and smoke testing in `lnxenv`.
  - [x] Run full test suite with 100% pass rate in `lnxenv` (35/35 passing).
  - [x] Perform end-to-end smoke test (Tenant Creation -> PDF/MD Ingestion -> Sourcing -> Scoring -> Drafting -> Dashboard Generation).

- [x] **Phase 7: Reference & Documentation Overhaul**
  - [x] Completely rewrite `GEMINI.md` for the public, open-source standalone ACE system.
  - [x] Update `CLAUDE.md` and `README.md` to reflect cross-platform installation and setup wizard.
  - [x] Document dynamic multi-tenant creation and PDF CV ingestion workflows.
