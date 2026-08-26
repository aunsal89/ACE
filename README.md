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
|  - Generated Assets: Tailored Resume (.md + .pdf), Cover Letter (.md + .pdf), LinkedIn Guidance   |
+----------------------------------------------------------------------------------------------------+
                         │                                                  │
                         ▼                                                  ▼
+------------------------------------+             +-------------------------------------------------+
|     4. REAL-TIME NOTIFICATIONS     |             |         5. AUTOMATED GIT SYNCHRONIZATION        |
|  - Telegram Bot: Instant summary   |             |  - Staged packages auto-committed & pushed     |
|  - Gmail SMTP: Styled HTML report  |             |  - Fetch from any PC via `git pull origin main` |
+------------------------------------+             +-------------------------------------------------+
```

---

## 📁 Repository & Directory Hierarchy

```text
portfolio/
├── CLAUDE.md                  # Claude frontend reference
├── GEMINI.md                  # Comprehensive architectural reference & system directives
├── README.md                  # User guide & operations manual
├── .env                       # Central credentials & API keys
├── web/                       # Astro 6 + React 19 Portfolio Frontend (ahmethalitunsal.com)
│   ├── src/content/           # Master Markdown sources of truth (CV, Projects, Toolbox)
│   └── src/components/        # Hero, Timeline, Ventures, Education, Skills, Contact
└── career-engine/             # Autonomous Career Engine Orchestrator
    ├── run.py                 # CLI executable entry point
    ├── config/                # config.yaml & tenants/aunsal/profile.yaml
    ├── data/                  # SQLite DB (career_engine.db) & OpenRouter cache (openrouter_free_models.json)
    ├── deploy/systemd/        # Systemd timer & service unit templates
    ├── inbox/                 # Staged application packages organized by Track and Date
    │   ├── track_a_embedded/  # Track A: Embedded Leadership (MBD, ISO 26262, AUTOSAR, Motor Control)
    │   │   └── YYYY-MM-DD/    # Dated batch run folder
    │   │       └── <company>_<role>_<id>/
    │   │           ├── Resume_Ahmet_Halit_Unsal_<company>.md
    │   │           ├── Resume_Ahmet_Halit_Unsal_<company>.pdf
    │   │           ├── Cover_Letter_<company>.md
    │   │           ├── Cover_Letter_<company>.pdf
    │   │           └── LinkedIn_Guidance.md
    │   └── track_b_quant/     # Track B: Quantitative Development (AURA, Algorithmic Execution)
    │       └── YYYY-MM-DD/
    │           └── <company>_<role>_<id>/
    ├── src/                   # Core Python pipeline modules
    │   ├── sourcing/          # Multi-channel job board and domestic portal scrapers
    │   ├── scoring/           # LLM fit scorer & dynamic OpenRouter free-tier router
    │   ├── applicator/        # Markdown & Unicode PDF generator
    │   ├── database/          # SQLite models, repository & deduplication
    │   ├── notifications/     # Telegram & Gmail notification dispatcher
    │   └── utils/             # Hashing, Unicode PDF renderer & Git sync
    └── tests/                 # Full unit test suite (32 unit tests)
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

### 3. Application Generation & Remote Git Sync
- For every job scored $\ge 80$ (`QUEUED`), the engine drafts:
  - Tailored Executive Resume in Markdown and high-resolution Unicode PDF.
  - Custom, metric-driven Cover Letter in Markdown and Unicode PDF.
  - LinkedIn Headline & Outreach Guidance prompts.
- Packages are saved into `/inbox/<track>/<YYYY-MM-DD>/<company>_<role>_<id>/`.
- **Automated Git Push:** On pipeline completion, the server automatically commits the staged files and pushes to GitHub `origin/main`. You can inspect and review formatted PDFs from any laptop or mobile device by running `git pull origin main`.

### 4. Notifications & Alerts
- **Telegram Bot:** Sends an immediate digest showing newly discovered jobs, queued matches, staged application links, and any non-fatal quota warnings (e.g. Apify free tier limit).
- **Gmail SMTP:** Delivers a cleanly styled HTML email report summarizing pipeline metrics and staged applications.

---

## 📋 Application Tracking & Review Workflow

How to track which opportunities are new, queued, applied, or rejected:

```text
[DISCOVERED] ──(Score ≥ 80)──► [QUEUED] ──(Drafting)──► [STAGED IN /INBOX/]
                                                                │
                                   ┌────────────────────────────┴────────────────────────────┐
                                   ▼                                                         ▼
                           [User Approves & Applies]                                 [User Rejects]
                           python run.py approve <job_id>                     python run.py reject <job_id>
                                   │                                                         │
                                   ▼                                                         ▼
                               [APPLIED]                                                 [REJECTED]
```

### Review Commands

```bash
# 1. View overall database metrics and state breakdown
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py status

# 2. List all staged application packages in /inbox/ with their IDs and paths
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py list-inbox

# 3. List jobs filtered by status (QUEUED, APPLIED, REJECTED, DISCOVERED)
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py list-jobs --status QUEUED

# 4. After submitting an application on a company portal, mark it as APPLIED:
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py approve <job_id>

# 5. If an opportunity does not match personal preferences, mark it as REJECTED:
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py reject <job_id>
```

---

## 🧪 Single Manual Trial Run Guide

To test the entire pipeline end-to-end and observe the results:

### Step 1: Trigger the Service or CLI Pipeline

**Option A: Via Systemd (Production execution mode)**
```bash
sudo systemctl start career-sourcing.service
```

**Option B: Via Python CLI directly**
```bash
cd /home/nsl/Portfolio/career-engine
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py pipeline --refresh-models
```

### Step 2: What to Watch For & Expected Results

1. **Systemd Journal Logs:**
   ```bash
   journalctl -u career-sourcing.service -f
   ```
   *Expected output:* Sourcing listing count → OpenRouter model refresh → Scoring evaluations → Staged inbox packages → Notification dispatch → Git auto-commit & push.

2. **Generated Inbox Files (`career-engine/inbox/`):**
   ```bash
   find career-engine/inbox/ -type f
   ```
   *Expected files created:*
   - `career-engine/inbox/track_a_embedded/YYYY-MM-DD/<comp>_<role>_<id>/Resume_Ahmet_Halit_Unsal_<comp>.pdf`
   - `career-engine/inbox/track_a_embedded/YYYY-MM-DD/<comp>_<role>_<id>/Cover_Letter_<comp>.pdf`
   - `career-engine/inbox/track_a_embedded/YYYY-MM-DD/<comp>_<role>_<id>/LinkedIn_Guidance.md`

3. **Notifications Received:**
   - **Telegram:** Message from your bot with total listings discovered, queued count, and staged packages.
   - **Gmail:** Email to `aunsal89@gmail.com` with a styled HTML execution report.

4. **Remote GitHub Repository:**
   - On your local PC/Mac: Run `git pull origin main`. The generated PDFs, cover letters, and guidance documents will be immediately available locally for review.

---

## ⚙️ Scheduling & Automation (`systemd`)

The system uses a weekly `systemd` timer configured for **every Monday at 08:00 AM**:

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

- **Catch-up resilience (`Persistent=true`):** If `vsmlnx` is offline Monday at 08:00 AM, the job triggers immediately upon boot.
- **Jitter protection (`RandomizedDelaySec=300`):** Adds a random 0–5 minute offset to prevent thundering herd API requests.

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

Full suite passes 32 unit tests across configuration, database, deduplication hashing, OpenRouter dynamic router resilience, scoring, PDF rendering, and multi-channel sourcing.
