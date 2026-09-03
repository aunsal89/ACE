# Autonomous Career Engine (ACE) ⚡

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![AI Powered](https://img.shields.io/badge/AI-Gemini%20%7C%20OpenRouter%20%7C%20Claude-8A2BE2.svg)](https://aistudio.google.com/)
[![Cross-Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-green.svg)](https://github.com/aunsal89/ACE)
[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-ea4aaa.svg)](https://github.com/sponsors/aunsal89)

> **Autonomous Career Engine (ACE)** is a powerful, cross-platform, AI-driven career orchestration system. It autonomously sources job opportunities across live job boards and email alerts, evaluates candidate fit using cutting-edge Generative AI (Gemini, OpenRouter free models, Claude, OpenAI), extracts and structures candidate PDF resumes, and synthesizes tailored, metric-driven application dossiers (Resume PDF/MD, Cover Letter PDF/MD, LinkedIn outreach guidance, and interactive review dashboards).

---

## 🌟 Key Highlights & Capabilities

- 📄 **Universal CV Parsing (PDF, MD, TXT):** Feed your existing PDF or Markdown resume; ACE extracts and segments career history, education, and technical toolbox using generative AI and intelligent heuristic extractors.
- 👥 **Multi-Tenant Device Architecture:** Run multiple independent candidate profiles on a single device or workstation. Each candidate maintains isolated preferences, target titles, compensation filters, and staged application packages.
- 📡 **Multi-Channel Job Sourcing:**
  - **Google Jobs / SerpApi:** Aggregates live job postings matching intent.
  - **Headless Gmail LinkedIn Alert Ingestion:** Securely ingests LinkedIn Job Alert emails over IMAP with zero browser/GUI dependency.
  - **Apify LinkedIn Scraper:** Scrapes live LinkedIn postings with rate-limiting and quota-overflow fallbacks.
  - **Specialized Defense Portals:** Ingestion pipelines for ASELSAN, BAYKAR, Vizyoner Genç, TUSAŞ, and ROKETSAN.
- 🧠 **Dynamic AI Scoring & Free-Tier Cascade:**
  - Evaluates candidate fit, compensation thresholds, location/remote preferences, and keyword alignment.
  - Features **dynamic OpenRouter free-tier discovery & ranker** ($0 API cost) with automatic multi-model fallback and deterministic rule evaluation.
- 📁 **Automated Application Staging (`/inbox/`):**
  - Generates tailored, job-specific executive Resumes (`.pdf` + `.md`), customized Cover Letters (`.pdf` + `.md`), LinkedIn outreach guidance, and full metadata briefs.
- 📊 **Executive Review Dashboard (`inbox/index.html`):**
  - Self-contained, responsive HTML dashboard with interactive SVG donut/bar charts, multi-term search (`+` AND, `,` OR), dynamic geographical/role taxonomy filters, and terminal action triggers.
- 💻 **Cross-Platform & On-Demand:** Runs effortlessly on **Windows, macOS, and Linux** with simple on-demand CLI commands.

---

## 🚀 Quickstart Guide

### 1. Prerequisites & Installation

Clone the repository and install dependencies in a Python 3.10+ virtual environment:

```bash
# Clone the public repository
git clone https://github.com/aunsal89/ACE.git
cd ACE

# Create and activate virtual environment
# On Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

---

### 2. Interactive Setup Wizard (Fastest)

Run the guided onboarding wizard to configure your API keys, candidate profile, and ingest your CV in under 2 minutes:

```bash
python run.py setup
```

The wizard will interactively:
1. Prompt for your AI credentials (e.g. **Google Gemini free API key** from [Google AI Studio](https://aistudio.google.com/) or **OpenRouter**).
2. Configure optional sourcing channels (SerpApi, Apify, Gmail, Telegram).
3. Prompt for your Candidate Profile (Name, Email, Location, Target Titles, Min Net Salary).
4. Ingest and structure your existing CV (`.pdf`, `.md`, or `.txt`).
5. Initialize the local SQLite database and register your profile.

---

### 3. Run the Autonomous Pipeline

Run end-to-end multi-channel sourcing, AI scoring, application drafting, and dashboard generation:

```bash
# Execute full pipeline for active candidate
python run.py pipeline

# Or run with dynamic OpenRouter model refresh
python run.py pipeline --refresh-models

# Or run a non-destructive dry-run
python run.py pipeline --dry-run
```

Open `inbox/index.html` in your web browser to explore your interactive review dashboard and staged application dossiers!

---

## 🛠️ CLI Command Reference

| Command | Description |
| :--- | :--- |
| `python run.py setup` | Interactive step-by-step onboarding wizard for API keys and candidate CV |
| `python run.py pipeline` | Execute full multi-channel sourcing, AI scoring, drafting, and notification pipeline |
| `python run.py companies list` | List configured target companies and career portals for active candidate |
| `python run.py companies add <name> <url>` | Add or update a targeted company career portal (e.g. ASML, Baykar, Apple) |
| `python run.py companies remove <name>` | Remove a target company from the candidate's target list |
| `python run.py import-cv <path>` | Ingest a PDF, MD, or TXT CV and extract structured sources of truth |
| `python run.py tenant list` | List all configured candidate profiles on this device |
| `python run.py tenant switch <id>` | Switch the active candidate profile |
| `python run.py tenant show [id]` | Display tenant configuration, target preferences, and CV sources |
| `python run.py tenant create` | Add a new candidate tenant to this device |
| `python run.py dashboard` | Regenerate the interactive HTML review dashboard in `inbox/<tenant_id>/index.html` |
| `python run.py status` | Display system overview, tenant info, and database pipeline statistics |
| `python run.py list-jobs` | List sourced job opportunities in terminal with status and track filters |
| `python run.py score` | Run LLM fit evaluation on discovered jobs |
| `python run.py draft` | Synthesize tailored PDF/MD application dossiers into `/inbox/` |
| `python run.py stage <job_id>` | Force stage application dossier for a specific opportunity ID |
| `python run.py approve <job_id>` | Approve application and mark status as `APPLIED` |
| `python run.py reject <job_id>` | Reject an opportunity and mark status as `REJECTED` |
| `python run.py test-notify` | Send diagnostic test alerts to Telegram and Gmail SMTP |
| `python run.py refresh-models` | Discover, rank, and cache active OpenRouter zero-cost models |

---

## 🔑 Environment Configuration (`.env`)

You can create or update `.env` in the root directory (see [`.env.example`](.env.example)):

```dotenv
# --- LLM Providers (Only ONE required to start) ---
GEMINI_API_KEY=your_gemini_api_key_here          # Free at aistudio.google.com
OPENROUTER_API_KEY=your_openrouter_key_here      # Optional free models cascade
OPENAI_API_KEY=your_openai_key_here              # Optional
ANTHROPIC_API_KEY=your_anthropic_key_here        # Optional

# --- Sourcing APIs (Optional) ---
SERPAPI_API_KEY=your_serpapi_key_here            # Google Jobs live search
APIFY_API_TOKEN=your_apify_token_here            # LinkedIn live search
GMAIL_IMAP_USER=your_email@gmail.com             # Headless LinkedIn Alert ingestion
GMAIL_IMAP_PASSWORD=your_app_password_here

# --- Real-Time Mobile Alerts (Optional) ---
TELEGRAM_BOT_TOKEN=your_bot_token_here           # Real-time mobile alerts
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## 📊 Executive Review Dashboard (`inbox/index.html`)

ACE automatically compiles an interactive HTML dashboard:
- **Zero External Dependencies:** Self-contained, responsive, lightweight executive design.
- **Dynamic Visual Analytics:** Real-time SVG donut charts and interactive bar charts aggregated across geography and role taxonomy.
- **Dual-Dimension Filtering:** Filter by pipeline state (`Staged Packages`, `Queued`, `Evaluated`, `Applied`, `Rejected`) and Track.
- **Multi-Term Search:** Supports Boolean expressions (e.g. `London + Embedded`, `Remote, Singapore`).
- **1-Click Review Actions:** Instant terminal command copy (`python run.py stage <id>`, `python run.py approve <id>`).

---

## 👨‍💻 Architect & Principal Developer

**Ahmet Halit Ünsal**  
*Senior Engineering Leader & Systems Architect*  
- 🌐 **Portfolio & Case Studies:** [ahmethalitunsal.com](https://www.ahmethalitunsal.com)  
- 🔗 **LinkedIn:** [linkedin.com/in/ahmethalitunsal](https://www.linkedin.com/in/ahmethalitunsal/)  
- 🐙 **GitHub:** [github.com/aunsal89](https://github.com/aunsal89)  
- ✉️ **Email:** [aunsal89@gmail.com](mailto:aunsal89@gmail.com)  

### 💼 Hire the Creator
Ahmet brings 15+ years of professional engineering experience and 8+ years managing 30-engineer cross-functional teams across:
- **Embedded Software Leadership:** Model-Based Design (MATLAB/Simulink), ISO 26262 ASIL D, AUTOSAR, EV Powertrains (VCU, MCU, BMS, Inverters), and PMSM motor control.
- **Quantitative & High-Throughput Systems:** Architect of **AURA** (24/7 automated algorithmic trading architecture, walk-forward optimization, dynamic risk engines).

---

## ☕ Support & Sponsorship

If ACE has accelerated your career, saved you hours of application prep, or helped you land high-impact interviews, consider supporting the open-source maintenance of this project:

- 💖 **GitHub Sponsors:** [sponsor/aunsal89](https://github.com/sponsors/aunsal89)
- ☕ **Buy Me a Coffee:** [buymeacoffee.com/aunsal](https://buymeacoffee.com/aunsal)
- 🪙 **Crypto Support:**
  - **USDT (TRC-20):** `TMX4i6Q6g7dF8uT1a6z3K9vXyZ1W2M4nL5`
  - **Bitcoin (BTC):** `bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh`
  - **Ethereum (ETH):** `0x71C83f7fB008A2d3A8679A814343f8B51352eB4A`

---

## 🤝 Contributing & Git Workflow

We welcome contributions from the community! Please read our official [**Contributing & Git Workflow Guidelines**](CONTRIBUTING.md) to understand our branch protection policies, commit standards, Pull Request lifecycle, and conflict resolution protocols.

---

## 📄 License & Legal Notice

Autonomous Career Engine (ACE) is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.  
See [LICENSE](LICENSE) for full details.

```text
Copyright (C) 2026 Ahmet Halit Ünsal <aunsal89@gmail.com>
```

Under AGPL-3.0, you are free to use, inspect, and modify this software. If you run a modified version on a server or provide network access to it, you MUST make the corresponding source code publicly available under the same license with all author notices preserved. Commercial repackaging without open-source contribution is strictly prohibited.
