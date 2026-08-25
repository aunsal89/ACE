# ARCHITECTURAL BLUEPRINT & AGENT DIRECTIVE
**Project:** Autonomous Career Engine, Portfolio Synchronizer & Multi-Tenant Job Hunting Platform  
**Host Environment:** `homlnx` (Ubuntu x86_64, Conda env `lnxenv`, Python 3.12, `agy` CLI)  
**Target Repository:** `https://github.com/aunsal89/Portfolio` (Deployed via Vercel to `https://www.ahmethalitunsal.com/`)

---

## 1. EXECUTIVE CONTEXT & USER PROFILE

### 1.1 Professional Identity & Dual-Track Goals
*   **Track A: Embedded Software Leadership / Directorship**
    *   **Background:** 8+ years in engineering management and team leadership. Deep specialization in embedded software architectures and system control algorithm development using Model-Based Design (MBD).
    *   **Target Locations:** Primary base in Istanbul (family relocation) or executive/director-level presence in Ankara.
    *   **Target Sectors:** Defense electronics and automotive technologies.
    *   **Compensation Baseline:** High-earning domestic positions exceeding a current baseline of **$8,600 USD/month net (inflation-hedged)**.
*   **Track B: Quantitative Developer / Algorithmic Trading**
    *   **Initiative:** Proprietary algorithmic trading architecture ("AURA"), expanding from cryptocurrency to live equity/stock market execution.
    *   **Target Roles:** Quantitative software engineering, automated strategy development, and algorithmic execution.
    *   **Geographic Scope:** Global tech and financial hubs across Europe, China, and APAC (excluding the US market at this time).
    *   **Showcase Asset:** `https://www.auratrading.org/` (integrating dual yields: crypto + equities).

### 1.2 Long-Term Commercial Vision (Multi-Tenant Architecture)
This system is initially configured for personal career acceleration but must be engineered with clean separation of concerns so it can later be packaged and offered as a managed SaaS / micro-service for high-tier professionals.

---

## 2. SYSTEM ARCHITECTURE

```text
                                  +-------------------------------------------------------------+
                                  |                     SOURCING LAYER                          |
                                  |  - Google Jobs API (Global Quant / EU / APAC)               |
                                  |  - 3rd-Party Guest LinkedIn Scraper (Apify API)             |
                                  |  - Custom Portal Scrapers (Baykar, Aselsan, Vizyoner Genc)  |
                                  +------------------------------+------------------------------+
                                                                 |
                                                                 v
+----------------------------------------------------------------+-------------------------------------------------------------+
|                                                   homlnx ORCHESTRATION LAYER                                                 |
|                                                                                                                              |
|  +------------------------+      +---------------------------+      +-----------------------------------------------------+  |
|  |     SQLite / DuckDB    | ---> |     Scoring Engine        | ---> |                     agy CLI Engine                  |  |
|  | (Deduplication & State)|      | (Comp, Tech Stack, Region)|      | (Tailored Resumes, Cover Letters, Git Commits, Web) |  |
|  +------------------------+      +---------------------------+      +--------------------------+--------------------------+  |
+------------------------------------------------------------------------------------------------|-----------------------------+
                                                                                                 |
                                                                 +-------------------------------+------------------------------+
                                                                 |                                                              |
                                                                 v                                                              v
                                              +--------------------------------------+      +--------------------------------------+
                                              |          APPROVAL INBOX              |      |             PORTFOLIO SYNC           |
                                              |  - Staged Application Packages       |      |  - ahmethalitunsal.com (via Vercel)  |
                                              |  - Guided LinkedIn Update Prompts    |      |  - auratrading.org (Yield Merging)   |
                                              +--------------------------------------+      +--------------------------------------+
```

---

## 3. CORE SUB-SYSTEMS & DIRECTIVES

### Sub-System A: Multi-Channel Sourcing Engine (`sourcing/`)
1. **Global Aggregator API Client:** Queries Google Jobs / SerpApi for high-paying international Quant and Embedded roles across the EU and APAC.
2. **Third-Party LinkedIn API Worker:** Interfaces with paid, headless scraping endpoints (e.g., Apify Guest Scraper) using structured boolean search filters to avoid personal account bans.
3. **Domestic Defense Scraper Suite:** Lightweight, dedicated scrapers using `httpx` and `BeautifulSoup` to poll proprietary portals:
   * Baykar Career Portal (`kariyer.baykartech.com`)
   * Aselsan Career Portal
   * Vizyoner Genç
   * TUSAŞ / Roketsan listings
4. **State Management & Deduplication:** SQLite database storing unique job hashes, status flags (`DISCOVERED`, `EVALUATED`, `QUEUED`, `APPLIED`, `REJECTED`), and timestamps.

### Sub-System B: Profile Sync & Static Site Injection (`portfolio_sync/`)
1. **Codebase Discovery:** Inspect `https://github.com/aunsal89/Portfolio` to understand content layout, component trees, and Vercel build configs.
2. **Skill & Project Injection:** Decouple hardcoded content into clean JSON/YAML data stores (e.g., `data/profile.json`, `data/projects.json`).
3. **Yield Merging for AURA:** Build data-ingestion models for `auratrading.org` that consume both cryptocurrency engine metrics and equity market backtest/live yields.

### Sub-System C: Application Generation & Review Protocol (`applicator/`)
1. **Strict Fit Scoring:** Compare incoming JDs against user profile matrices (Track A vs. Track B). Filter out low-compensation or irrelevant positions.
2. **Tailored Asset Drafting:** Generate targeted Markdown/PDF resumes and customized cover letters for scored matches.
3. **LinkedIn Guidance Mode:** For profile optimization, output step-by-step copy changes, headline adjustments, and keyword recommendations for the user to apply manually.
4. **User-in-the-Loop Safeguard:** **Never submit applications or push to production branches automatically.** Stage all items into an `/inbox` directory or isolated Git pull requests for single-action approval.

### Sub-System D: SaaS / Multi-Tenant Readiness
1. Abstract all user credentials, resume history, and filtering criteria into isolated `tenants/{tenant_id}/` configuration modules.
2. Ensure scrapers and scoring pipelines operate as stateless workers accepting tenant configs.

---

## 4. AGENT OPERATING PROTOCOL: STEP-BY-STEP ROLLOUT

When initiated, the agent must guide the user through the project in modular phases. **Do not attempt to execute all phases at once.** Proceed phase-by-phase, confirming completion of each step before advancing.

### Phase 1: Discovery & Portfolio Refactoring
* [ ] Inspect local repository structure of `Portfolio`.
* [ ] Propose and implement a data-driven content structure (moving hardcoded components to JSON/YAML).
* [ ] Validate that local builds pass and Vercel deployments remain clean.

### Phase 2: Orchestrator Foundation & Database Setup
* [ ] Scaffold the project directory layout under `~/career-engine/` on `homlnx`.
* [ ] Initialize the SQLite schema for tracking listings, application histories, and scoring logs.
* [ ] Create configuration schemas (`config.yaml`) separating user profiles from engine settings.

### Phase 3: Sourcing Modules Implementation
* [ ] Implement the Google Jobs / SerpApi ingestion module.
* [ ] Implement the Apify / 3rd-party LinkedIn Guest API consumer.
* [ ] Implement direct scrapers for Turkish defense portals (Baykar, Aselsan, Vizyoner Genç).

### Phase 4: Scoring, `agy` Integration & Drafting Pipeline
* [ ] Connect the LLM scoring layer to rank opportunities against target compensation and locations.
* [ ] Configure the `agy` execution script to read high-scoring JDs and generate tailored application artifacts into an `/inbox/` queue.
* [ ] Build interactive LinkedIn profile optimization prompts.

### Phase 5: AURA Yield Integration & Production Hardening
* [ ] Implement the multi-market data pipeline for `auratrading.org`.
* [ ] Setup systemd service/timer or cron triggers on `homlnx`.
* [ ] Document multi-tenant expansion guidelines.

---

