# Ahmet Halit Ünsal — Portfolio & Autonomous Career Engine

Personal web portfolio at **[ahmethalitunsal.com](https://www.ahmethalitunsal.com)** and autonomous career sourcing orchestrator.

---

## 🏛️ Architecture Overview

```text
Portfolio/
├── web/                       # Astro 6 + React 19 + Tailwind v4 Portfolio Site
│   ├── src/content/           # Markdown sources of truth (CV, Projects, Toolbox)
│   └── src/components/        # Hero, Timeline, Ventures, Education, Skills, Contact
└── career-engine/             # Autonomous Career Engine Pipeline
    ├── src/sourcing/          # Google Jobs, LinkedIn (Apify), Defense scrapers (Baykar, Aselsan, etc.)
    ├── src/scoring/           # LLM fit scoring & dynamic OpenRouter free-tier cascade
    ├── src/applicator/        # Generative resume, cover letter & PDF drafting
    ├── src/database/          # SQLite models, migrations & repository
    ├── src/notifications/     # Telegram Bot & Gmail SMTP notification dispatcher
    ├── deploy/systemd/        # Systemd timer & service unit templates
    ├── inbox/                 # Staged application packages (Human-in-the-loop)
    └── tests/                 # Full unit test suite (32 tests)
```

---

## 🚀 Quickstart

### Web Portfolio (`web/`)
```bash
cd web
npm install
npm run dev        # local dev server on http://localhost:4321
npm run build      # static site generation to dist/
```

### Career Engine (`career-engine/`)
```bash
# Execute within Conda 'lnxenv' Python environment
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py pipeline --refresh-models

# Refresh and inspect top ranked OpenRouter free models
/home/nsl/miniconda3/envs/lnxenv/bin/python run.py refresh-models

# Run complete test suite (32 unit tests)
/home/nsl/miniconda3/envs/lnxenv/bin/python -m pytest tests
```

---

## 📚 Documentation Reference
- [`GEMINI.md`](GEMINI.md): Comprehensive architectural invariants, Conda environment specifications, LLM cascade rules, and phased development roadmaps.
- [`CLAUDE.md`](CLAUDE.md): Frontend toolchain, Astro content collections, and typography reference.
- [`career-engine/docs/MULTI_TENANT_ARCHITECTURE.md`](career-engine/docs/MULTI_TENANT_ARCHITECTURE.md): Multi-tenant enterprise SaaS blueprint.

