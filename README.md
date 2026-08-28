# Ahmet Halit Ünsal — Autonomous Career Engine & Portfolio Architecture

Production-grade autonomous career sourcing orchestrator and personal web portfolio at **[ahmethalitunsal.com](https://www.ahmethalitunsal.com)**.

---

## 🏛️ System Architecture & Dual-Track Goals

The Career Engine runs autonomously on host `vsmlnx` (Ubuntu x86_64), discovering, evaluating, and drafting job applications for two distinct target career tracks:

```text
+----------------------------------------------------------------------------------------------------+
|                                    1. MULTI-CHANNEL SOURCING                                       |
|  - Domestic Defense Scrapers: Baykar, ASELSAN, Vizyoner Genç, TUSAŞ, Roketsan                      |
|  - Global Job Board: Google Jobs (SerpApi - 2 high-intent targeted queries)                        |
|  - LinkedIn Email Alerts: Headless Gmail IMAP Sourcing + Unauthenticated Guest Details API         |
|  - Professional Network: LinkedIn Guest Scraper (Apify with mock fixture fallback)                 |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                                    2. SCORING & FIT ENGINE                                         |
|  - Primary: Google Gemini (gemini-2.5-flash) via GEMINI_API_KEY                                    |
|  - Dynamic Fallback: OpenRouter Free-Tier Router (Heuristic Ranking + Level 1/2 Resilience)        |
|  - Deterministic Safety Net: Strict keyword & criteria evaluator (100% offline resilience)        |
|  - Tracks: Track A (Embedded Software Leadership) & Track B (Quantitative Development - AURA)      |
+----------------------------------------------------------------------------------------------------+
                                                  │
                                                  ▼
+----------------------------------------------------------------------------------------------------+
|                               3. APPLICATION PACKAGE GENERATION                                    |
|  - Outputs staged in /inbox/<track>/<YYYY-MM-DD>/<company>_<role>_<id>/                            |
|  - Generated Assets: Tailored Resume (.md + .pdf), Cover Letter (.md + .pdf),                      |
|                      LinkedIn Guidance (.md), Job Details (.md)                                    |
+----------------------------------------------------------------------------------------------------+
                                 │
                                 ▼
+----------------------------------------------------------------------------------------------------+
|                               4. VISUAL HTML REVIEW DASHBOARD                                      |
|  - Self-contained, responsive dashboard at /inbox/index.html                                       |
|  - Path-independent strictly relative links to folders, PDF resumes, and cover letters             |
|  - Search, track filtering, and one-click copy buttons for terminal approval/rejection commands     |
+----------------------------------------------------------------------------------------------------+
                          │                                                  │
                          ▼                                                  ▼
+------------------------------------+             +-------------------------------------------------+
|     5. REAL-TIME NOTIFICATIONS     |             |         6. AUTOMATED GIT SYNCHRONIZATION        |
|  - Telegram Bot: Instant summary   |             |  - Staged packages & index.html auto-pushed     |
|  - Gmail SMTP: Styled HTML report  |             |  - Systematic refresh: review via `git pull`    |
+------------------------------------+             +-------------------------------------------------+
```

---

## 📁 Repository & Directory Hierarchy

```text
portfolio/
├── CLAUDE.md                  # Claude frontend reference
├── GEMINI.md                  # Comprehensive architectural reference & system directives
├── README.md                  # Operational guide, CLI use cases & user reference
├── .env                       # Central credentials & API keys
├── web/                       # Astro 6 + React 19 Portfolio Frontend (ahmethalitunsal.com)
│   ├── src/content/           # Master Markdown sources of truth (CV, Projects, Toolbox)
│   └── src/components/        # Hero, Timeline, Ventures, Education, Skills, Contact
└── career-engine/             # Autonomous Career Engine Orchestrator
    ├── run.py                 # CLI executable entry point
    ├── config/                # config.yaml & tenants/aunsal/profile.yaml
    ├── data/                  # SQLite DB (career_engine.db) & OpenRouter cache (openrouter_free_models.json)
    ├── deploy/systemd/        # Systemd timer & service unit templates
    ├── inbox/                 # Staged application packages & review hub
    │   ├── index.html         # Self-contained HTML review dashboard (open in browser)
    │   ├── track_a_embedded/  # Track A: Embedded Leadership (MBD, ISO 26262, AUTOSAR, Motor Control)
    │   │   └── YYYY-MM-DD/    # Dated batch run folder
    │   │       └── <company>_<role>_<id>/
    │   │           ├── Resume_Ahmet_Halit_Ünsal_<company>.md
    │   │           ├── Resume_Ahmet_Halit_Ünsal_<company>.pdf
    │   │           ├── Cover_Letter_<company>.md
    │   │           ├── Cover_Letter_<company>.pdf
    │   │           ├── Job_Details.md
    │   │           └── LinkedIn_Guidance.md
    │   └── track_b_quant/     # Track B: Quantitative Development (AURA, Algorithmic Execution)
    │       └── YYYY-MM-DD/
    │           └── <company>_<role>_<id>/
    ├── src/                   # Core Python pipeline modules
    │   ├── sourcing/          # Multi-channel scrapers (Defense, Google Jobs, Gmail LinkedIn, Apify)
    │   ├── scoring/           # LLM fit scorer & dynamic OpenRouter free-tier router
    │   ├── applicator/        # Markdown & Unicode PDF generator with Education integration
    │   ├── database/          # SQLite models, repository & deduplication
    │   ├── notifications/     # Telegram & Gmail notification dispatcher
    │   └── utils/             # Dashboard generator, Unicode PDF renderer, Hashing & Git sync
    └── tests/                 # Full unit test suite (35 unit tests)
```

---

## 🔄 End-to-End Execution Flow & Guarantees

### 1. Sourcing & Deduplication Idempotency
- Every discovered job listing generates a deterministic **SHA-256 hash** derived from `(normalized_company, normalized_title, location, url)`.
- When the scraper runs, existing jobs in the database are recognized and marked as `is_new=False`.
- **Idempotency Guarantee:** Running the pipeline multiple times will **never** generate duplicate inbox packages or redundant notification alerts.

### 2. Fit Scoring & OpenRouter Resilient Cascade
- High-intent scoring evaluates candidates against dual-track constraints:
  - **Track A (Embedded Leadership):** 15+ years experience, 8+ years leadership (30+ engineers), MBD/Simulink, ISO 26262 ASIL D, AUTOSAR, Motor Control/EV, Istanbul/Ankara, $\ge \$8,600$ USD/month net.
  - **Track B (Quantitative Developer):** AURA algorithmic architecture, CCXT, walk-forward optimization, execution algorithms across Europe, APAC, and China (excluding US).
- If Gemini or OpenRouter encounters rate limits (HTTP 429) or transient outages, the system executes **Level 1 exponential backoff with jitter** and **Level 2 inter-model cascading fallback** across top free models (`nvidia/nemotron`, `minimax`, `google/gemma`). If all APIs fail, it transparently falls back to a deterministic offline evaluator.

### 3. Application Generation & Systematic Dashboard Refresh
- For every job scored $\ge 80$ (`QUEUED`), the engine drafts:
  - **Tailored Executive Resume** (Markdown + PDF) with complete professional experience and candidate education background appended at the end.
  - **Comprehensive Cover Letter** (Markdown + PDF) detailing leadership scaling, functional safety, powertrain architectures, or AURA quantitative trading systems, including direct Job URLs.
  - **`Job_Details.md`** containing original URLs, review action commands, AI match scoring rationale, and description snippets.
  - **LinkedIn Guidance** prompts for targeted outreach.
- **Visual HTML Review Dashboard:** Staged packages and state changes systematically regenerate `inbox/index.html`.
- **Automated Git Push:** On pipeline completion, the server automatically commits all staged packages and `inbox/index.html` to GitHub `origin/main`.

### 4. Remote Review Workflow via `git pull`
- Each weekly automated execution through `career-sourcing.service` systematically regenerates `inbox/index.html` and pushes changes to GitHub.
- When you run `git pull origin main` on any local PC or laptop, you can immediately double-click `career-engine/inbox/index.html` in your browser. All links to folders and PDFs work seamlessly because paths are strictly relative.

---

## 🎯 Practical CLI Use Cases & Operational Playbook

All commands must be executed using the designated Conda Python interpreter `/home/nsl/miniconda3/envs/lnxenv/bin/python` from the `career-engine/` directory.

### Use Case 1: Open and Refresh the HTML Review Dashboard
To regenerate or inspect the self-contained visual review hub at any time:
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py dashboard
```
*Action:* Open `career-engine/inbox/index.html` in any web browser to view, search, filter, and review all opportunities across Track A and Track B.

### Use Case 2: Run the Full Autonomous Pipeline Manually
To trigger a complete run (sourcing $\to$ model cache refresh $\to$ scoring $\to$ package drafting $\to$ dashboard regeneration $\to$ notification $\to$ git push):
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py pipeline --refresh-models
```

### Use Case 3: Review and Approve a Staged Opportunity
After applying to an opportunity on a company portal, mark it as `APPLIED` using its 8-character ID (found in the folder name or copied with one click from the HTML dashboard):
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py approve f82e8bc8
```
*Effect:* Atomically updates the database state to `APPLIED`, records an audit log, and immediately refreshes `inbox/index.html`.

### Use Case 4: Reject an Opportunity
If an opportunity does not match current preferences:
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py reject f82e8bc8
```
*Effect:* Updates database state to `REJECTED`, records audit history, and updates `inbox/index.html`.

### Use Case 5: Draft Staged Packages for Queued Jobs
To generate or re-draft resumes, cover letters, and `Job_Details.md` for all QUEUED opportunities:
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py draft
```

### Use Case 6: Inspect System Status and Opportunity Metrics
To inspect database aggregates, active tenant profile, and job counts across states:
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py status
```

### Use Case 7: Filter and Query Job Opportunities
```bash
# List all Track A Embedded Leadership jobs ready for review
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py list-jobs --status QUEUED --track TRACK_A

# List all Track B Quant Trading opportunities
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py list-jobs --track TRACK_B
```

### Use Case 8: Refresh OpenRouter Free Model Discovery Cache
To query OpenRouter's dynamic model catalog, rank free zero-cost models, and update `data/openrouter_free_models.json`:
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py refresh-models --limit 10
```

### Use Case 9: Test Notification Channels (Telegram & Gmail)
To verify your `.env` Telegram bot token and Gmail SMTP credentials:
```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py test-notify
```

---

## ⚙️ Scheduling & Automation (`systemd`)

The system runs automatically via a weekly `systemd` timer configured for **every Monday at 08:00 AM**:

```bash
# 1. Install unit files
sudo cp /home/nsl/Portfolio/career-engine/deploy/systemd/career-sourcing.service /etc/systemd/system/
sudo cp /home/nsl/Portfolio/career-engine/deploy/systemd/career-sourcing.timer /etc/systemd/system/

# 2. Reload daemon
sudo systemctl daemon-reload

# 3. Enable and activate weekly timer
sudo systemctl enable --now career-sourcing.timer

# 4. Check timer schedule
systemctl list-timers | grep career-sourcing
```

- **Catch-up resilience (`Persistent=true`):** If `vsmlnx` is offline Monday at 08:00 AM, the pipeline triggers immediately upon boot.
- **Jitter protection (`RandomizedDelaySec=300`):** Adds a random 0–5 minute offset to prevent thundering herd API requests.
- **Systematic Git Push & Dashboard Sync:** Every scheduled run updates `inbox/index.html` and pushes to `origin/main` so that `git pull` from any device gives the latest visual state.

---

## 🔐 Environment Configuration (`.env`)

Template located in root `/home/nsl/Portfolio/.env`:

```bash
# LLM Providers
GEMINI_API_KEY="AIzaSy..."               # Primary scoring & drafting evaluator
OPENROUTER_API_KEY="sk-or-v1-..."         # Dynamic free-tier resilient fallback router

# Notifications
TELEGRAM_BOT_TOKEN="123456789:ABC..."    # Telegram Bot API token
TELEGRAM_CHAT_ID="123456789"             # Telegram Chat / User ID
SMTP_USER="aunsal89@gmail.com"           # Gmail account for SMTP notifications
SMTP_PASSWORD="xxxx xxxx xxxx xxxx"      # Gmail 16-character App Password
NOTIFICATION_EMAIL="aunsal89@gmail.com"  # Notification recipient

# Sourcing APIs (Optional)
SERPAPI_API_KEY="xxx"                    # Google Jobs ingestion
APIFY_API_TOKEN="apify_api_xxx"          # LinkedIn Guest Scraper (falls back to mock if quota exceeded)
```

---

## 🧪 Testing Suite

```bash
/home/nsl/miniconda3/envs/lnxenv/bin/python -m pytest /home/nsl/Portfolio/career-engine/tests
```

Full suite passes **35 unit tests** across configuration, database CRUD, deduplication hashing, OpenRouter dynamic router resilience, scoring, PDF rendering with HTML entity decoding, Job Details generation, dashboard creation, and multi-channel sourcing (including headless Gmail LinkedIn email ingestion).
