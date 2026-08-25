# GEMINI.md — Career Engine & Portfolio Synchronizer Reference

Comprehensive architectural guide, operational directives, and codebase reference for **Ahmet Halit Ünsal**'s autonomous career orchestration system and personal portfolio at **[ahmethalitunsal.com](https://www.ahmethalitunsal.com)**.

---

## 1. Executive Context & Dual-Track Goals

### 1.1 Dual-Track Target Profiles

* **Track A: Embedded Software Leadership / Directorship (Primary Long-Term Domain)**
  * **Experience Baseline:** 15+ years professional experience, 8+ years in engineering management and team leadership.
  * **Authoritative Source of Truth:** `src/content/cv/Experience.md` (Note: GitHub personal repos reflect recent work (~1.5 years); the full depth of commercial/defense/automotive leadership spans NISO Technology Co, ECEMTAG, TÜBİTAK, TÜMOSAN, METRO CO, and Iowa State University).
  * **Core Competencies:**
    * Management of 30-engineer cross-functional teams, multi-team lead structures, SLA/milestone tracking.
    * Model-Based Design (MBD), MATLAB/Simulink, Stateflow, Physical Modeling.
    * ISO 26262 (Functional Safety ASIL), ASPICE, UN R155/R156 Cybersecurity (CSMS).
    * AUTOSAR BSW/ASW, FreeRTOS, C/C++ bare-metal & RTOS middleware.
    * EV Powertrains: ECUs, Traction Inverters, On-Board Chargers (OBCs), BMS.
    * Motor Control & Dynamics: PMSM/IPMSM, MTPA, flux-weakening, traction control, dyno characterization, HIL/MiL validation (dSpace MABX, Lauterbach Trace32).
  * **Target Locations:** Primary base in Istanbul (family relocation) or executive/director-level presence in Ankara.
  * **Target Sectors:** Defense electronics and automotive technologies.
  * **Compensation Baseline:** High-earning domestic positions exceeding a current baseline of **$8,600 USD/month net (inflation-hedged)**.

* **Track B: Quantitative Developer / Algorithmic Trading**
  * **Core Competencies:** Proprietary algorithmic trading architecture (**AURA**), expanding from 24/7 live Binance Spot execution to live equity/stock market execution. Walk-forward optimization (successive halving), multi-layer risk management (dynamic stop-loss/take-profit, regime detection, PAXG defensive overlays), CCXT, pandas, NumPy, SQLite, systemd.
  * **Target Roles:** Quantitative software engineering, automated strategy development, algorithmic execution.
  * **Geographic Scope:** Global tech and financial hubs across Europe, APAC, and China (excluding US market currently).
  * **Showcase Asset:** `https://www.auratrading.org/` (dual yield integration: crypto + equities).

### 1.2 Full-Cycle Product Engineering Showcase
* **EduTrace ([edutrace.net](https://edutrace.net) / `MysApp` repo):** Special education clinical evaluation platform. React Native (Expo SDK 54), TypeScript, Supabase (PostgreSQL + RLS + Edge Functions + Realtime), offline-first sync engine, AI study plans (Gemini + OpenRouter fallback chains), EAS Build CI.

### 1.3 Long-Term Multi-Tenant Vision
Designed with strict separation of concerns to allow future packaging as a managed SaaS / micro-service platform for high-tier professionals.

---

## 2. Host Environment, Toolchain & Operational Rules

* **Host:** `vsmlnx` (Ubuntu x86_64)
* **Conda Environment:** `lnxenv` (Python 3.11)
* **Strict Python Interpreter:** `/home/nsl/miniconda3/envs/lnxenv/bin/python` (all development, script execution, testing, and daemon jobs MUST explicitly invoke this binary).
* **Verified Python Packages in `lnxenv`:**
  * Network & Scraping: `requests`, `httpx`, `beautifulsoup4`
  * Data & Schemas: `pydantic`, `pyyaml`, `rich`, `python-dotenv`
  * Generative AI SDKs: `google-genai`, `anthropic`, `openai`
* **Static Site Toolchain:** Astro 6 (`^6.3.1`), React 19 (`^19.2.6`), Tailwind CSS v4 (`^4.3.0`), TypeScript (Strict).
* **Brevity & Token Efficiency Directives:** Feedback, status reports, and explanations must remain ultra-concise, high-signal, and minimal in token usage unless the user explicitly requests exhaustive or deep-dive details on a specific subject.
* **Python Validation:** All generated or modified Python code must be checked for AST validity and, if applicable, smoke tested prior to any further development steps.
* **Atomic Commits & Lifecycle Tracking:** All project milestones, feature completions, refactors, and phase transitions must be committed atomically with clear, high-signal commit messages providing distinct anchor points throughout the project lifecycle.

---

## 3. Content Architecture & Harmonization Strategy

```text
+-----------------------------------------------------------------------------------+
|                        CENTRAL CONTENT SOURCE OF TRUTH                            |
|                            (src/content/ & src/data/)                             |
+-----------------------------------------------------------------------------------+
       |                                      |                                |
       v                                      v                                v
+----------------------+   +------------------------------------+   +----------------------+
|  PORTFOLIO WEBPAGE   |   |        LINKEDIN PROFILE            |   | TAILORED APPLICATION |
| (ahmethalitunsal.com)|   |     (Manual / Semi-guided)         |   |  PACKAGES (/inbox/)  |
|                      |   |                                    |   |                      |
| - Skill-focused hub  |   | - Streamlined experience entries   |   | - Generative AI      |
| - Comprehensive tech |   |   (Company, Title, Dates only;     |   |   synthesis per JD   |
|   taxonomy across JDs|   |   omits deep bullet points for     |   | - Target-matched CVs |
| - Concise, high-hook |   |   older roles like Tumosan)        |   |   (Markdown / PDF)   |
|   project summaries  |   | - High-level summary & headline    |   | - Custom cover letter|
| - Expandable .md repo|   |   aligned with primary target      |   | - Human approval gate|
+----------------------+   +------------------------------------+   +----------------------+
```

### 3.1 Portfolio Webpage Strategy
* **Skill-Centric Hub:** The Skills section operates as a comprehensive, living matrix. As new job descriptions (JDs) are analyzed, relevant industry skills and standards (both Embedded and Quant) are incorporated into the taxonomy.
* **Brief & Intriguing Projects:** Rather than overwhelming showcases, project entries (`Project_AURA.md`, `Project_EduTrace.md`) provide concise, high-impact overviews designed to provoke curiosity and demonstrate complete end-to-end technical and product ownership.
* **Modular Markdown Expansion:** Adding new projects or CV sections is achieved simply by dropping new `.md` files with structured frontmatter into `src/content/`.

### 3.2 LinkedIn Profile Strategy
* **Streamlined Roles:** Older experience entries (e.g., Tumosan, Metro Co) are kept clean and concise (Company, Title, Duration), avoiding clutter while preserving career trajectory.
* **Manual Updates:** The user maintains LinkedIn manually, supported by LLM-generated headline and summary suggestions.

### 3.3 Automated JD-Tailored CV Generation Pipeline
* **Dynamic Generation:** When a high-scoring JD is discovered, the orchestrator triggers generative models (`google-genai`, `anthropic`, or `openai`) via prompt templates combining the master profile and the target JD.
* **Outputs:** Generates tailored Markdown resumes and customized cover letters, with automated conversion to cleanly styled PDFs via Python tooling.
* **Staging in `/inbox/`:** In adherence to the **Human-in-the-Loop Safeguard**, generated packages are staged into an `/inbox/` folder for review and approval prior to any submission.

---

## 4. Repository Structure & Technical Invariants

```
portfolio/
├── astro.config.mjs           # Astro + React + Tailwind plugin
├── tsconfig.json              # Strict TypeScript + react-jsx
├── package.json               # Node >=22.12.0
├── CLAUDE.md                  # Claude project reference
├── GEMINI.md                  # Gemini & overall system architecture reference
├── agent_init_prompt.md       # Multi-phase blueprint and directives
├── public/
│   ├── ausnal_headshot.png    # Hero image (object-position: center 25%)
│   ├── favicon.svg / .ico
├── src/
│   ├── content.config.ts      # Collections definition (cv, projects, skills)
│   ├── styles/global.css      # Tailwind v4 @theme tokens + typography plugin
│   ├── layouts/Layout.astro   # Navbar, anchors (#ventures, #experience, #skills, #contact), footer
│   ├── pages/index.astro      # Single page composition
│   ├── components/
│   │   ├── Hero.astro         # Reads cv/Intro.md
│   │   ├── Ventures.astro     # Reads projects/*.md -> VentureTabs
│   │   ├── VentureTabs.tsx    # React client:load island
│   │   ├── Timeline.astro     # Reads cv/Experience.md -> .cv-timeline h3 styling
│   │   ├── Education.astro    # Reads cv/Education.md
│   │   ├── Skills.astro       # Reads skills/Toolbox.md (dynamic taxonomy)
│   │   └── Contact.astro      # Reads cv/Contact.md
│   └── content/
│       ├── cv/                # Intro.md, Experience.md, Education.md, Contact.md
│       ├── projects/          # Project_AURA.md, Project_EduTrace.md, ...
│       └── skills/            # Toolbox.md
└── career-engine/             # Autonomous Career Engine Orchestrator
    ├── run.py                 # CLI executable entry point
    ├── config/                # config.yaml & tenants/aunsal/profile.yaml
    ├── data/                  # SQLite database storage (career_engine.db)
    ├── inbox/                 # Staged tailored CVs, Cover Letters & PDFs
    ├── src/
    │   ├── sourcing/          # Google Jobs, LinkedIn Apify, Baykar, Aselsan, etc.
    │   ├── scoring/           # LLM fit scoring & multi-provider fallback client
    │   ├── applicator/        # Generative resume & cover letter drafting pipeline
    │   ├── database/          # SQLite schema, models & repository
    │   └── utils/             # Hashing, Unicode PDF renderer & logger
    └── tests/                 # Full unit test suite (24 tests)
```

### 4.1 Critical Codebase Rules & Invariants
1. **Astro 6 Glob Loader Casing:** `glob()` lowercases entry IDs (e.g. `Intro.md` → `intro`). Always resolve entries using case-insensitive matching (`e.id.toLowerCase() === '...'`).
2. **Heading H1 Stripping:** Markdown files begin with `# Title` for standalone readability. Components render their own section headings and strip the leading `#` with `.replace(/^#\s+.*\n+/, '')`.
3. **Tailwind v4 Native CSS:** No `tailwind.config.js`. Tokens live in `src/styles/global.css` under `@theme`. Typography plugin is declared via `@plugin "@tailwindcss/typography"`.
4. **Header Navigation Contact Link:** The header "Contact" button must link to `#contact` (not `mailto:`).
5. **Timeline DOM Selectors:** `Timeline.astro` uses scoped styles targeting `h3` and `h3 + p`. Preserve heading structure in `Experience.md`.

---

## 5. System Phased Rollout Plan

* [x] **Phase 1: Discovery, Strategy Alignment & Decoupling Preparation**
  * Repository structure inspected and documented.
  * Environment dependencies verified in `lnxenv`.
  * GitHub ecosystem audited across Track A, Track B, and App Architecture.
  * Track A authoritative CV source of truth integrated (`src/content/cv/Experience.md`).
  * Multi-surface content strategy (Web, LinkedIn, Tailored CVs) defined.
  * `GEMINI.md` created & synchronized.
* [x] **Phase 2: Orchestrator Foundation & Database Setup**
  * Scaffold orchestrator directory layout under `~/Portfolio/career-engine/` on `vsmlnx`.
  * Initialize SQLite schema for job tracking, deduplication, and application state.
  * Create configuration schemas (`config.yaml`) separating user profiles from engine settings.
* [x] **Phase 3: Sourcing Modules Implementation**
  * Google Jobs / SerpApi ingestion module.
  * Apify 3rd-party LinkedIn Guest scraper worker.
  * Domestic Turkish defense portal scrapers (Baykar, Aselsan, Vizyoner Genç, TUSAŞ/Roketsan).
* [x] **Phase 4: Scoring Engine & Generative Application Drafting Pipeline**
  * Multi-track fit scoring against compensation and location filters.
  * LLM-driven resume and cover letter drafting pipeline outputting to `/inbox/`.
  * Markdown-to-PDF formatting integration.
* [x] **Phase 5: Production Hardening & Automation Infrastructure**
  * Systemd service (`career-sourcing.service`) configured with Conda `lnxenv` interpreter, error recovery, unbuffered journal logging, and security sandboxing.
  * Systemd timer (`career-sourcing.timer`) configured for daily 08:00 AM trigger with catch-up resilience (`Persistent=true`) and jitter protection (`RandomizedDelaySec=300`).
  * End-to-end `pipeline` CLI subcommand implemented for single or multi-tenant batch sourcing, scoring, and drafting.
  * Authoritative multi-tenant SaaS architecture blueprint documented at `docs/MULTI_TENANT_ARCHITECTURE.md`.
  * (Note: AURA crypto/equity yield integration postponed for standalone algorithm development).

