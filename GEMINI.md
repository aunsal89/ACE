# GEMINI.md — Autonomous Career Engine (ACE) Architecture & Directives

Comprehensive architectural guide, operational directives, and codebase reference for **Autonomous Career Engine (ACE)** at **[github.com/aunsal89/ACE](https://github.com/aunsal89/ACE)**, architected and created by **Ahmet Halit Ünsal**.

---

## 1. System Identity & Core Purpose

**Autonomous Career Engine (ACE)** is a generalized, cross-platform, AI-orchestrated career intelligence platform. It runs on user demand across Windows, macOS, and Linux to:
1. **Source Opportunities Autonomously:** Continuously scrape and ingest live job listings across Google Jobs, Gmail LinkedIn IMAP alerts, Apify LinkedIn, and domestic defense portals (Baykar, Aselsan, Vizyoner Genç, TUSAŞ, Roketsan).
2. **Dynamic Multi-Tenant Ingestion:** Ingest arbitrary candidate CVs (PDF, Markdown, TXT), extract structured career history, education, and skills using Generative AI (Gemini / OpenRouter) or deterministic heuristic extractors, and isolate profiles under `config/tenants/<tenant_id>/`.
3. **Multi-Model Fit Scoring:** Score job opportunities against candidate preferences (target titles, locations, compensation floor, exclusions) using Google Gemini (`gemini-2.5-flash`), dynamic OpenRouter free-tier cascade ($0 cost), Claude, OpenAI, or deterministic rule evaluation.
4. **Tailored Application Staging (`/inbox/`):** Synthesize job-tailored Resumes (`.pdf` / `.md`), metric-driven Cover Letters (`.pdf` / `.md`), LinkedIn outreach guidance, and metadata briefs staged in `/inbox/<tenant_id>/`.
5. **Interactive Review Dashboard (`inbox/index.html`):** Render a responsive, zero-dependency executive dashboard with dynamic SVG analytics, multi-term Boolean search, click-to-filter geography/taxonomy charts, and terminal action triggers.

---

## 2. Host Environment, Toolchain & Operational Rules

* **Development Host:** `vsmlnx` (Ubuntu x86_64)
* **Conda Environment:** `lnxenv` (Python 3.11)
* **Strict Python Interpreter:** `/home/nsl/miniconda3/envs/lnxenv/bin/python` (all development, script execution, testing, and CLI jobs MUST explicitly invoke this binary on `vsmlnx`).
* **Cross-Platform Target:** Fully compatible with Linux, macOS, and Windows with dynamic `pathlib.Path` relative path resolution from `PROJECT_ROOT`.
* **Verified Dependencies (`requirements.txt`):**
  - Parsing & Documents: `pypdf`, `fpdf2`
  - Data & Schemas: `pydantic`, `pyyaml`, `rich`, `python-dotenv`
  - Network & Scraping: `httpx`, `beautifulsoup4`, `requests`
  - Generative AI SDKs: `google-genai`, `anthropic`, `openai`
  - Testing: `pytest`, `pytest-cov`, `pytest-asyncio`
* **Brevity & Token Efficiency Directives:** Status reports and explanations must remain ultra-concise, high-signal, and minimal in token usage unless the user explicitly requests deep-dive details.
* **Mandatory Smoke Testing:** Every new feature, module addition, or bug fix MUST be subjected to an end-to-end smoke test (CLI simulation, test suite verification in `lnxenv`) prior to completion.
* **Atomic Commits & Branch Protection:** The `main` branch is **strictly protected**. AI agents and contributors MUST NEVER push directly to `main`. All updates, bug fixes, and features MUST follow the protocols detailed in [CONTRIBUTING.md](CONTRIBUTING.md) (committed atomically to a newly created branch, pushed to `origin`, and submitted as a Pull Request for manual review and merge).

---

## 3. Repository Architecture & Layout

```text
ACE/
├── LICENSE                    # GNU AGPL-3.0 (Copyright (c) 2026 Ahmet Halit Ünsal)
├── README.md                  # Public open-source guide, features & quickstart
├── CONTRIBUTING.md            # Official contributing & git workflow guidelines
├── GEMINI.md                  # Gemini architectural reference & operational rules
├── CLAUDE.md                  # Claude CLI & commands reference
├── TODO.md                    # Multi-phase milestone tracker
├── requirements.txt           # Unified dependency manifest
├── run.py                     # Root executable CLI entry point
├── .env.example               # Annotated credentials template (Gemini, OpenRouter, SerpApi, etc.)
├── .gitignore                 # Tenant dynamic isolation, DB, inbox staging exclusions, fonts
├── config/
│   ├── config.yaml            # Engine core configuration (relative paths, LLM, sourcing)
│   ├── profile.example.yaml   # Generalized candidate profile template
│   └── tenants/               # Local candidate tenants (isolated, git-ignored)
│       └── .gitkeep
├── data/                      # Local SQLite database & dynamic OpenRouter model cache
│   ├── career_engine.db       # Job listings, scoring evaluations, application packages
│   ├── fonts/                 # Dynamically cached Unicode TTF fonts (git-ignored)
│   └── openrouter_free_models.json
├── inbox/                     # Staged application dossiers & review dashboard
│   ├── index.html             # Self-contained, responsive HTML review dashboard
│   └── <tenant_id>/           # Tenant-isolated staged application packages
│       └── <date>/
│           └── <company>_<role>_<short_id>/
├── src/
│   ├── cli.py                 # Central CLI commands (setup, tenant, import-cv, pipeline, etc.)
│   ├── config.py              # OS-agnostic dynamic path resolution & TenantManager
│   ├── database/              # SQLite connection, Pydantic/SQLAlchemy models & repository
│   ├── sourcing/              # Multi-channel scrapers (Google Jobs, Gmail IMAP, Apify, Baykar, Aselsan, etc.)
│   ├── scoring/               # Fit evaluation, LLM client & OpenRouter dynamic router
│   ├── applicator/            # Resume & Cover Letter drafting pipeline
│   └── utils/                 # PDF renderer, CV parser, HTML dashboard, notifications, hashing, logger
└── tests/                     # 34 unit and integration tests across 7 test modules
```

---

## 4. Technical Invariants & System Modules

### 4.1 Multi-Tenant Device Management & Unified Preferences
- Multiple candidate profiles can coexist on one machine.
- Each tenant profile resides in `config/tenants/<tenant_id>/profile.yaml` with unified `preferences:` (target titles, locations, compensation, experience requirements, core competencies, exclusions) and its own `sources/` (`Experience.md`, `Education.md`, `Toolbox.md`, `Summary.md`).
- Active tenant is dynamically tracked in `config.yaml` or overridden via `--tenant-id <id>`.
- Default fallback: If no tenants exist, running `python run.py pipeline` automatically launches `interactive_setup_wizard`.

### 4.2 Universal PDF & Document CV Parser (`src/utils/cv_parser.py`)
- Extracts raw text via `pypdf` from `.pdf`, `.md`, or `.txt`.
- Structures text into Markdown sources of truth using Gemini / OpenRouter or deterministic regex heuristic section segmenters.
- Invoked via `python run.py import-cv <path_to_cv> [--tenant-id <id>]` or through the interactive setup wizard.

### 4.3 Resilient Multi-Provider LLM Scoring (`src/scoring/`)
- Evaluates candidate fit against target titles, locations, compensation minimums, and tech stack competencies directly from candidate preferences and CV markdown.
- **Dynamic OpenRouter Router:** Queries `https://openrouter.ai/api/v1/models`, discovers active zero-cost models, ranks them via heuristic formula, and executes with two-level retry and cascading fallback.
- **Deterministic Rule Fallback:** Evaluates keywords and location criteria even during total API outage.

### 4.4 Staged Application Generation (`src/applicator/`)
- Staged into `inbox/<tenant_id>/<date>/<company>_<role>_<id>/`.
- Synthesizes tailored Markdown and renders publication-quality vector PDFs (`render_markdown_to_pdf`).
- **Dynamic Unicode Fonts:** Automatically downloads NotoSans TTFs into `data/fonts/` (git-ignored) on-demand across Linux, macOS, and Windows.
- Includes comprehensive `Job_Details.md` with 1-click review CLI action triggers (`python run.py approve <id>`, `python run.py reject <id>`).

### 4.5 Executive Review Dashboard (`inbox/<tenant_id>/index.html` and `inbox/index.html`)
- Completely self-contained HTML page generated by `src/utils/dashboard.py`.
- Features real-time SVG analytics, interactive filters, Boolean search (`+`, `,`), force-stage triggers (`python run.py stage <id>`), and developer promotion & donation modals.
- Isolates candidate reviews under `inbox/<tenant_id>/index.html` with relative dossier linking.

### 4.6 Targeted Company Career Portals (`config/tenants/<tenant_id>/target_companies.yaml`)
- In addition to aggregators (Google Jobs, LinkedIn), users can define custom company career portals (ASML, Apple, Baykar, ASELSAN, Siemens, etc.).
- Managed via CLI (`python run.py companies list|add|remove`) or directly in YAML.
- Defaults and open-source template available in `config/target_companies.example.yaml`.

---

## 5. CLI Command Matrix

| Command | Action |
| :--- | :--- |
| `python run.py setup` | Guided interactive setup wizard for API keys and candidate CV |
| `python run.py pipeline [--refresh-models] [--dry-run]` | End-to-end multi-channel sourcing, scoring, drafting, and notification |
| `python run.py companies list` | List configured target companies and career portals for active candidate |
| `python run.py companies add <name> <url>` | Add or update a targeted company career portal |
| `python run.py companies remove <name>` | Remove a target company from the candidate target list |
| `python run.py import-cv <path_to_cv>` | Ingest PDF/MD CV and extract structured sources |
| `python run.py tenant list` | List all local candidate tenants with active status |
| `python run.py tenant switch <tenant_id>` | Switch active candidate tenant |
| `python run.py tenant show [tenant_id]` | Display tenant configuration, target preferences, and CV sources |
| `python run.py tenant create` | Interactive prompt to onboard a new candidate |
| `python run.py dashboard` | Regenerate HTML review dashboard in `inbox/<tenant_id>/index.html` |
| `python run.py status` | Display system overview and database pipeline stats |
| `python run.py list-jobs [--status]` | View job listings in database |
| `python run.py stage <job_id>` | Force stage application dossier for a specific listing |
| `python run.py approve <job_id>` | Mark job status as `APPLIED` |
| `python run.py reject <job_id>` | Mark job status as `REJECTED` |
| `python run.py test-notify` | Test Telegram and Gmail SMTP delivery |
| `python run.py refresh-models` | Refresh OpenRouter free-tier cache |
