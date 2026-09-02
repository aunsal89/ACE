"""
Autonomous Career Engine (ACE) Command Line Interface.
Cross-Platform Autonomous Job Sourcing, LLM Fit Scoring & Tailored Application Drafter.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict
import yaml

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from src.config import load_engine_config, load_tenant_profile, TenantManager, PROJECT_ROOT, EngineConfig, TenantProfile
from src.database.connection import init_db
from src.database.models import JobStatus, TrackType
from src.database.repository import JobRepository
from src.sourcing.manager import SourcingManager, SCRAPER_REGISTRY
from src.scoring.scorer import OpportunityScorer
from src.scoring.openrouter_router import OpenRouterManager
from src.applicator.generator import ApplicationGenerator
from src.utils.dashboard import generate_inbox_dashboard
from src.utils.hashing import generate_deduplication_hash, normalize_company, normalize_title
from src.utils.notifications import NotificationService
from src.utils.cv_parser import extract_text_from_file, parse_cv_with_llm, save_parsed_cv_to_tenant

console = Console()

BANNER = """[bold cyan]╔═══════════════════════════════════════════════════════════════════════════╗
║                  Autonomous Career Engine (ACE) v0.3.0                    ║
║   Autonomous Sourcing, LLM Fit Scoring & Tailored Application Dossiers   ║
║   Architect: Ahmet Halit Ünsal (github.com/aunsal89/ACE)                  ║
║   Sponsor / Donate: github.com/sponsors/aunsal89 | Open Source (AGPL-3.0) ║
╚═══════════════════════════════════════════════════════════════════════════╝[/bold cyan]"""


def _ensure_active_tenant(config: Optional[EngineConfig] = None, requested_id: Optional[str] = None) -> TenantProfile:
    """Ensure at least one tenant exists; if none, auto-launch setup wizard."""
    cfg = config or load_engine_config()
    mgr = TenantManager(cfg)
    available = mgr.list_available_tenants()

    if requested_id:
        try:
            return mgr.get_tenant(requested_id)
        except Exception as e:
            console.print(f"[bold red]Tenant '{requested_id}' not found. Available tenants: {', '.join(available) or 'None'}[/bold red]")
            sys.exit(1)

    if not available:
        console.print(BANNER)
        console.print("[yellow]No candidate profiles detected on this device. Launching interactive setup...[/yellow]\n")
        return interactive_setup_wizard(cfg)

    # Check if active_tenant in config is valid
    if cfg.multi_tenancy.active_tenant in available:
        return mgr.get_tenant(cfg.multi_tenancy.active_tenant)

    # Otherwise return the first available
    return mgr.get_tenant(available[0])


def interactive_setup_wizard(config: Optional[EngineConfig] = None) -> TenantProfile:
    """Guided interactive setup wizard for API keys, candidate profile, and CV ingestion."""
    cfg = config or load_engine_config()
    console.print(Panel.fit(
        "[bold cyan]Welcome to Autonomous Career Engine (ACE) Setup[/bold cyan]\n"
        "This wizard will configure your API credentials and onboard your candidate profile.\n"
        "All data is saved locally on your device in [bold]config/tenants/[/bold] and [bold].env[/bold].",
        title="ACE Setup Wizard",
        border_style="cyan"
    ))

    # --- 1. API Keys Setup ---
    console.print("\n[bold yellow]═══ Step 1: AI & LLM API Configuration ═══[/bold yellow]")
    console.print("[dim]Tip: You only need ONE key (e.g. Gemini free tier or OpenRouter free models) to start for $0.[/dim]\n")

    env_path = PROJECT_ROOT / ".env"
    existing_env: Dict[str, str] = {}
    if env_path.exists():
        from dotenv import dotenv_values
        existing_env = {k: v for k, v in dotenv_values(env_path).items() if v is not None}

    gemini_key = Prompt.ask(
        "Google Gemini API Key [dim](free at aistudio.google.com)[/dim]",
        default=existing_env.get("GEMINI_API_KEY", "")
    ).strip()

    openrouter_key = Prompt.ask(
        "OpenRouter API Key [dim](optional, free models cascade at openrouter.ai)[/dim]",
        default=existing_env.get("OPENROUTER_API_KEY", "")
    ).strip()

    openai_key = Prompt.ask(
        "OpenAI API Key [dim](optional)[/dim]",
        default=existing_env.get("OPENAI_API_KEY", "")
    ).strip()

    anthropic_key = Prompt.ask(
        "Anthropic API Key [dim](optional)[/dim]",
        default=existing_env.get("ANTHROPIC_API_KEY", "")
    ).strip()

    console.print("\n[bold yellow]═══ Step 2: Sourcing & Notification APIs (Optional) ═══[/bold yellow]")
    console.print("[dim]Configure live search channels, Gmail LinkedIn alert scraping, and real-time mobile notifications.[/dim]\n")

    serpapi_key = Prompt.ask(
        "SerpApi Key [dim](optional, for Google Jobs live search at serpapi.com)[/dim]",
        default=existing_env.get("SERPAPI_API_KEY", "")
    ).strip()

    apify_token = Prompt.ask(
        "Apify API Token [dim](optional, for LinkedIn job scraping at apify.com)[/dim]",
        default=existing_env.get("APIFY_API_TOKEN", "")
    ).strip()

    gmail_user = Prompt.ask(
        "Gmail Address [dim](optional, for LinkedIn job alert IMAP ingestion & SMTP email notifications)[/dim]",
        default=existing_env.get("GMAIL_IMAP_USER", existing_env.get("IMAP_USER", existing_env.get("SMTP_USER", "")))
    ).strip()

    gmail_pass = ""
    if gmail_user:
        gmail_pass = Prompt.ask(
            "Gmail App Password [dim](16-char password from myaccount.google.com/apppasswords)[/dim]",
            default=existing_env.get("GMAIL_IMAP_PASSWORD", existing_env.get("IMAP_PASSWORD", existing_env.get("SMTP_PASSWORD", "")))
        ).strip()

    telegram_token = Prompt.ask(
        "Telegram Bot Token [dim](optional, for real-time mobile job alerts)[/dim]",
        default=existing_env.get("TELEGRAM_BOT_TOKEN", "")
    ).strip()

    telegram_chat_id = ""
    if telegram_token:
        telegram_chat_id = Prompt.ask(
            "Telegram Chat ID [dim](e.g. from @userinfobot)[/dim]",
            default=existing_env.get("TELEGRAM_CHAT_ID", "")
        ).strip()

    # Save .env file
    env_content = f"""# Autonomous Career Engine (ACE) - Environment Variables
GEMINI_API_KEY={gemini_key}
OPENROUTER_API_KEY={openrouter_key}
OPENAI_API_KEY={openai_key}
ANTHROPIC_API_KEY={anthropic_key}

# Live Sourcing APIs
SERPAPI_API_KEY={serpapi_key}
APIFY_API_TOKEN={apify_token}

# Gmail LinkedIn IMAP Ingestion & SMTP Alerts
GMAIL_IMAP_USER={gmail_user}
GMAIL_IMAP_PASSWORD={gmail_pass}
IMAP_USER={gmail_user}
IMAP_PASSWORD={gmail_pass}
SMTP_USER={gmail_user}
SMTP_PASSWORD={gmail_pass}
NOTIFICATION_EMAIL={gmail_user}

# Real-Time Mobile Alerts
TELEGRAM_BOT_TOKEN={telegram_token}
TELEGRAM_CHAT_ID={telegram_chat_id}
"""
    env_path.write_text(env_content, encoding="utf-8")

    # Immediately reload environment variables into running process
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
    for k, v in [
        ("GEMINI_API_KEY", gemini_key),
        ("OPENROUTER_API_KEY", openrouter_key),
        ("OPENAI_API_KEY", openai_key),
        ("ANTHROPIC_API_KEY", anthropic_key),
        ("SERPAPI_API_KEY", serpapi_key),
        ("APIFY_API_TOKEN", apify_token),
        ("GMAIL_IMAP_USER", gmail_user),
        ("GMAIL_IMAP_PASSWORD", gmail_pass),
        ("IMAP_USER", gmail_user),
        ("IMAP_PASSWORD", gmail_pass),
        ("SMTP_USER", gmail_user),
        ("SMTP_PASSWORD", gmail_pass),
        ("NOTIFICATION_EMAIL", gmail_user),
        ("TELEGRAM_BOT_TOKEN", telegram_token),
        ("TELEGRAM_CHAT_ID", telegram_chat_id),
    ]:
        if v:
            os.environ[k] = v

    console.print("[bold green]✓ .env credentials file updated and loaded into environment successfully.[/bold green]\n")

    # --- 2. Candidate Profile Setup ---
    console.print("[bold yellow]═══ Step 3: Candidate Profile & Target Career Preferences ═══[/bold yellow]")
    full_name = Prompt.ask("Candidate Full Name (e.g. Jane Doe)").strip()
    tenant_id_default = "".join(c if c.isalnum() else "_" for c in full_name.lower().replace(" ", "_")).strip("_") or "candidate"
    tenant_id = Prompt.ask("Tenant Identifier Slug", default=tenant_id_default).strip()

    email = Prompt.ask("Email Address").strip()
    phone = Prompt.ask("Phone Number [dim](optional)[/dim]", default="").strip()
    location = Prompt.ask("Current Location (e.g. London, UK / Istanbul, Turkey / Remote)", default="Remote").strip()

    linkedin_url = Prompt.ask("LinkedIn Profile URL [dim](optional)[/dim]", default="").strip()
    github_url = Prompt.ask("GitHub Profile URL [dim](optional)[/dim]", default="").strip()
    website_url = Prompt.ask("Personal Website / Portfolio URL [dim](optional)[/dim]", default="").strip()

    target_titles_raw = Prompt.ask(
        "Target Job Titles [dim](comma-separated, e.g. Lead Systems Engineer, Software Architect)[/dim]",
        default="Senior Software Engineer, Systems Architect"
    )
    target_titles = [t.strip() for t in target_titles_raw.split(",") if t.strip()]

    target_locations_raw = Prompt.ask(
        "Target Job Locations [dim](comma-separated, e.g. London, Remote, Istanbul)[/dim]",
        default=f"{location}, Remote"
    )
    target_locations = [loc.strip() for loc in target_locations_raw.split(",") if loc.strip()]

    min_salary_str = Prompt.ask("Minimum Monthly Net Salary Expectation [USD]", default="6000")
    try:
        min_salary = float(min_salary_str.replace(",", "").replace("$", ""))
    except ValueError:
        min_salary = 6000.0

    # --- 3. CV Ingestion ---
    console.print("\n[bold yellow]═══ Step 4: CV Ingestion & Parsing ═══[/bold yellow]")
    cv_file_path = Prompt.ask("Path to your CV file [dim](PDF, Markdown, or TXT)[/dim]", default="").strip()

    parsed_sections: Dict[str, Any] = {}
    if cv_file_path and Path(cv_file_path).exists():
        console.print(f"[cyan]Extracting and structuring CV from {cv_file_path}...[/cyan]")
        try:
            raw_text = extract_text_from_file(cv_file_path)
            parsed_sections = parse_cv_with_llm(raw_text, candidate_name=full_name)
            console.print("[bold green]✓ CV successfully parsed into structured markdown sections.[/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Warning during CV extraction: {e}. Default templates will be created.[/yellow]")

    # Create tenant
    mgr = TenantManager(cfg)
    links_dict = {
        "website": website_url or None,
        "linkedin": linkedin_url or None,
        "github": github_url or None,
    }
    tenant = mgr.create_tenant(
        tenant_id=tenant_id,
        name=full_name,
        email=email,
        phone=phone or None,
        location=location,
        target_titles=target_titles,
        target_locations=target_locations,
        min_salary=min_salary,
        currency="USD",
        links=links_dict,
    )

    tenant_dir = cfg.multi_tenancy.tenants_dir / tenant.tenant_id
    if parsed_sections:
        save_parsed_cv_to_tenant(tenant_dir, parsed_sections)
    else:
        # Create starter placeholder markdown files
        sources_dir = tenant_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        (sources_dir / "Experience.md").write_text(f"# Professional Experience\n\n### Senior Engineer | Engineering Corp\n* Core achievements...", encoding="utf-8")
        (sources_dir / "Education.md").write_text(f"# Education\n\n**BSc Engineering** | University", encoding="utf-8")
        (sources_dir / "Toolbox.md").write_text(f"# Technical Skills\n\n* **Languages & Tools:** Python, C++, Linux, Git", encoding="utf-8")

    # Set as active tenant in config.yaml
    cfg_file = PROJECT_ROOT / "config" / "config.yaml"
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            cdata = yaml.safe_load(f) or {}
        cdata.setdefault("multi_tenancy", {})["active_tenant"] = tenant.tenant_id
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(cdata, f, sort_keys=False)

    # Initialize Database
    init_db(cfg.database.db_path)
    repo = JobRepository(cfg.database.db_path)
    repo.register_or_update_tenant(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        email=tenant.email,
        config_path=str(tenant_dir / "profile.yaml")
    )

    console.print(Panel(
        f"[bold green]✓ Candidate Tenant Profile Initialized Successfully![/bold green]\n\n"
        f"• [bold]Tenant ID:[/bold] [cyan]{tenant.tenant_id}[/cyan]\n"
        f"• [bold]Candidate Name:[/bold] {tenant.name} ({tenant.email})\n"
        f"• [bold]Target Titles:[/bold] {', '.join(target_titles)}\n"
        f"• [bold]Target Locations:[/bold] {', '.join(target_locations)}\n"
        f"• [bold]Profile Directory:[/bold] {tenant_dir}\n"
        f"• [bold]Database Initialized:[/bold] {cfg.database.db_path}\n\n"
        f"[bold]Next recommended command:[/bold]\n"
        f"[cyan]python run.py pipeline[/cyan] [dim](Runs multi-source scraping, LLM fit scoring & dossiers)[/dim]",
        title="Setup Complete",
        border_style="green"
    ))

    return tenant


def cmd_setup(args: argparse.Namespace) -> None:
    """Launch the interactive setup and tenant onboarding wizard."""
    config = load_engine_config()
    interactive_setup_wizard(config)


def cmd_import_cv(args: argparse.Namespace) -> None:
    """Ingest a PDF or Markdown CV for a tenant and extract structured sections."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))

    cv_path = Path(args.file_path).expanduser().resolve()
    if not cv_path.exists():
        console.print(f"[bold red]File not found:[/bold red] {cv_path}")
        sys.exit(1)

    console.print(f"[bold cyan]Ingesting CV for tenant '{tenant.name}' ({tenant.tenant_id}) from {cv_path.name}...[/bold cyan]")
    raw_text = extract_text_from_file(cv_path)
    parsed_data = parse_cv_with_llm(raw_text, candidate_name=tenant.name)

    tenant_dir = config.multi_tenancy.tenants_dir / tenant.tenant_id
    saved = save_parsed_cv_to_tenant(tenant_dir, parsed_data)

    console.print(Panel(
        f"[bold green]✓ CV successfully parsed and saved into sources for '{tenant.name}':[/bold green]\n" +
        "\n".join(f"• [cyan]{name}[/cyan] -> {p}" for name, p in saved.items()),
        title="CV Ingestion Succeeded",
        border_style="green"
    ))


def cmd_tenant(args: argparse.Namespace) -> None:
    """Manage candidate tenants (list, create, switch, show, import-cv)."""
    config = load_engine_config()
    mgr = TenantManager(config)

    action = getattr(args, "tenant_action", None)
    if action == "list" or action is None:
        tenants = mgr.list_available_tenants()
        if not tenants:
            console.print("[yellow]No tenants configured yet. Run `python run.py setup` or `python run.py tenant create`.[/yellow]")
            return

        table = Table(title="Configured Candidate Tenants on this Device", show_header=True, header_style="bold cyan")
        table.add_column("Active", justify="center")
        table.add_column("Tenant ID", style="bold yellow")
        table.add_column("Candidate Name", style="bold")
        table.add_column("Email", style="green")
        table.add_column("Location", style="dim")
        table.add_column("Target Titles", style="cyan")

        for tid in tenants:
            t = mgr.get_tenant(tid)
            is_active = "[bold green]★ ACTIVE[/bold green]" if tid == config.multi_tenancy.active_tenant else ""
            titles = ", ".join(t.preferences.target_titles[:2]) if t.preferences.target_titles else "General"
            table.add_row(is_active, tid, t.name, t.email, t.location_current, titles)

        console.print(table)

    elif action == "create":
        interactive_setup_wizard(config)

    elif action == "switch":
        target = args.target_tenant_id
        available = mgr.list_available_tenants()
        if target not in available:
            console.print(f"[bold red]Tenant '{target}' not found. Available: {', '.join(available)}[/bold red]")
            return

        cfg_file = PROJECT_ROOT / "config" / "config.yaml"
        if cfg_file.exists():
            with open(cfg_file, "r", encoding="utf-8") as f:
                cdata = yaml.safe_load(f) or {}
            cdata.setdefault("multi_tenancy", {})["active_tenant"] = target
            with open(cfg_file, "w", encoding="utf-8") as f:
                yaml.dump(cdata, f, sort_keys=False)

        console.print(f"[bold green]✓ Active tenant switched to:[/bold green] [cyan]{target}[/cyan]")

    elif action == "show":
        tenant = _ensure_active_tenant(config, requested_id=getattr(args, "target_tenant_id", None))
        p = tenant.preferences

        console.print(Panel(
            f"[bold green]Candidate:[/bold green] {tenant.name} ([cyan]{tenant.tenant_id}[/cyan])\n"
            f"[bold]Email:[/bold] {tenant.email} | [bold]Phone:[/bold] {tenant.phone or 'N/A'}\n"
            f"[bold]Current Location:[/bold] {tenant.location_current}\n"
            f"[bold]Website:[/bold] {tenant.links.website or 'N/A'} | [bold]LinkedIn:[/bold] {tenant.links.linkedin or 'N/A'}\n\n"
            f"[bold yellow]Candidate Preferences & Target Requirements:[/bold yellow]\n"
            f"• Target Titles: {', '.join(p.target_titles)}\n"
            f"• Target Locations: {', '.join(p.target_locations)}\n"
            f"• Min Compensation: ${p.compensation.min_monthly_net_usd:,.0f}/mo {p.compensation.currency}\n"
            f"• Core Competencies: {', '.join(p.core_competencies) if p.core_competencies else 'N/A'}\n"
            f"• Target Companies: {len(tenant.target_companies)} configured\n"
            f"• Exclusions: {', '.join(p.exclusions) if p.exclusions else 'None'}\n"
            f"• CV Markdown: {tenant.sources_of_truth.cv_markdown}",
            title=f"Tenant Profile: {tenant.name}",
            border_style="green"
        ))


def cmd_companies(args: argparse.Namespace) -> None:
    """Manage target companies and career portals for candidate tenant."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    mgr = TenantManager(config)

    action = getattr(args, "companies_action", None) or "list"

    if action == "list":
        companies = mgr.load_target_companies(tenant.tenant_id)
        if not companies:
            console.print(f"[yellow]No target companies configured for tenant '{tenant.name}' ({tenant.tenant_id}).[/yellow]")
            console.print("[dim]Add target companies with `python run.py companies add <name> <url>` or edit config/tenants/<tenant_id>/target_companies.yaml[/dim]")
            return

        table = Table(title=f"Target Companies & Career Portals ({tenant.name})", show_header=True, header_style="bold cyan")
        table.add_column("Company", style="bold yellow")
        table.add_column("Career Portal URL", style="blue")
        table.add_column("Location", style="dim")
        table.add_column("Keywords / Domain", style="dim")
        table.add_column("Status", style="green")

        for c in companies:
            status_str = "[green]ENABLED[/green]" if c.enabled else "[dim red]DISABLED[/dim red]"
            kws = ", ".join(c.keywords[:3]) if c.keywords else "All"
            table.add_row(c.name, c.url, c.location or "Global / Remote", kws, status_str)

        console.print(table)

    elif action == "add":
        name = args.name.strip()
        url = args.url.strip()
        location = getattr(args, "location", None)
        raw_kws = getattr(args, "keywords", None)
        kws = [k.strip() for k in raw_kws.split(",") if k.strip()] if raw_kws else []
        new_c = mgr.add_target_company(tenant.tenant_id, name=name, url=url, location=location, keywords=kws)
        console.print(f"[bold green]✓ Successfully added/updated target company:[/bold green] [yellow]{new_c.name}[/yellow] ([blue]{new_c.url}[/blue])")

    elif action == "remove":
        name = args.name.strip()
        removed = mgr.remove_target_company(tenant.tenant_id, name=name)
        if removed:
            console.print(f"[bold green]✓ Removed target company:[/bold green] [yellow]{name}[/yellow] from tenant '{tenant.name}'.")
        else:
            console.print(f"[yellow]Company '{name}' not found in target list for tenant '{tenant.name}'.[/yellow]")


def cmd_init_db(args: argparse.Namespace) -> None:
    """Initialize the SQLite database schema."""
    config = load_engine_config()
    init_db(config.database.db_path)
    repo = JobRepository(config.database.db_path)
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    repo.register_or_update_tenant(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        email=tenant.email,
        config_path=str(config.multi_tenancy.tenants_dir / tenant.tenant_id / "profile.yaml")
    )
    console.print(f"[bold green]✓ Database initialized successfully at:[/bold green] {config.database.db_path}")
    console.print(f"[bold green]✓ Tenant registered:[/bold green] {tenant.name} ([cyan]{tenant.tenant_id}[/cyan])")


def cmd_status(args: argparse.Namespace) -> None:
    """Display system overview and database statistics."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    repo = JobRepository(config.database.db_path)
    stats = repo.get_stats()

    console.print(BANNER)
    console.print(Panel.fit(
        f"[bold cyan]Autonomous Career Engine (ACE)[/bold cyan] v{config.engine.version}\n"
        f"[bold]Active Candidate Tenant:[/bold] [yellow]{tenant.name}[/yellow] ([cyan]{tenant.tenant_id}[/cyan])\n"
        f"[bold]Database Path:[/bold] {config.database.db_path}\n"
        f"[bold]Inbox Path:[/bold] {config.engine.inbox_dir}",
        title="System Status",
        border_style="blue"
    ))

    table = Table(title="Job Opportunity State Breakdown", show_header=True, header_style="bold magenta")
    table.add_column("Metric / State", style="dim")
    table.add_column("Count", justify="right", style="bold green")

    table.add_row("Total Discovered Listings", str(stats["total_jobs"]))
    for st in ["DISCOVERED", "EVALUATED", "QUEUED", "APPLIED", "REJECTED"]:
        count = stats["status_breakdown"].get(st, 0)
        table.add_row(f"State: {st}", str(count))

    table.add_section()
    table.add_row("Staged Application Packages", str(stats["total_packages"]))
    console.print(table)


def cmd_list_jobs(args: argparse.Namespace) -> None:
    """List job listings in database."""
    config = load_engine_config()
    repo = JobRepository(config.database.db_path)
    status_filter = JobStatus(args.status) if args.status else None
    track_filter = getattr(args, "track", None)

    jobs = repo.list_jobs(status=status_filter, track=track_filter, limit=args.limit)

    if not jobs:
        console.print("[yellow]No job listings found matching criteria.[/yellow]")
        return

    table = Table(title=f"Job Listings ({len(jobs)} shown)", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Company", style="green")
    table.add_column("Location", style="dim")
    table.add_column("Source", style="yellow")
    table.add_column("Status", style="bold")

    for j in jobs:
        status_color = "cyan" if j.status == JobStatus.DISCOVERED else "green" if j.status == JobStatus.QUEUED else "red" if j.status == JobStatus.REJECTED else "white"
        table.add_row(
            j.id[:8],
            j.title[:30],
            j.company[:20],
            (j.location or "N/A")[:18],
            j.source,
            f"[{status_color}]{j.status.value}[/{status_color}]"
        )

    console.print(table)


def cmd_source(args: argparse.Namespace) -> None:
    """Execute the multi-channel sourcing pipeline."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    manager = SourcingManager(config=config, tenant=tenant)
    manager.run_sourcing_pipeline(scraper_name=args.scraper, dry_run=args.dry_run)


def cmd_score(args: argparse.Namespace) -> None:
    """Evaluate discovered opportunities against tenant criteria."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    scorer = OpportunityScorer(config=config, tenant=tenant)
    scorer.run_scoring_batch(job_id=args.job_id, auto_queue=args.auto_queue)


def cmd_draft(args: argparse.Namespace) -> None:
    """Draft application packages into /inbox/."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    drafter = ApplicationGenerator(config=config, tenant=tenant)
    drafter.draft_queued_jobs(job_id=args.job_id)


def cmd_list_inbox(args: argparse.Namespace) -> None:
    """List all staged application packages in /inbox/."""
    config = load_engine_config()
    repo = JobRepository(config.database.db_path)
    pkgs = repo.get_application_packages()

    if not pkgs:
        console.print("[yellow]No staged packages in /inbox/.[/yellow]")
        return

    table = Table(title="Staged Application Packages in /inbox/", show_header=True, header_style="bold green")
    table.add_column("Job ID", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Resume PDF", style="cyan")
    table.add_column("Cover Letter PDF", style="cyan")
    table.add_column("Notes", style="dim")

    for p in pkgs:
        table.add_row(
            p.job_id[:8],
            p.status.value,
            Path(p.resume_pdf_path or "").name,
            Path(p.cover_letter_pdf_path or "").name,
            (p.notes or "")[:35]
        )

    console.print(table)


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a staged application package and mark as APPLIED."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config)
    repo = JobRepository(config.database.db_path)

    job = repo.update_job_status(
        job_id=args.job_id,
        new_status=JobStatus.APPLIED,
        tenant_id=tenant.tenant_id,
        changed_by="user",
        notes="Approved and submitted by user"
    )
    if job:
        console.print(f"[bold green]✓ Application for {job.company} - {job.title} marked as APPLIED.[/bold green]")
        dash_path = generate_inbox_dashboard(config=config, tenant=tenant)
        console.print(f"[bold green]✓ Review dashboard refreshed at:[/bold green] {dash_path}")
    else:
        console.print(f"[bold red]Could not find job with ID {args.job_id}[/bold red]")


def cmd_reject(args: argparse.Namespace) -> None:
    """Reject a job opportunity."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config)
    repo = JobRepository(config.database.db_path)

    job = repo.update_job_status(
        job_id=args.job_id,
        new_status=JobStatus.REJECTED,
        tenant_id=tenant.tenant_id,
        changed_by="user",
        notes="Rejected by user"
    )
    if job:
        console.print(f"[bold yellow]Job {job.company} - {job.title} marked as REJECTED.[/bold yellow]")
        dash_path = generate_inbox_dashboard(config=config, tenant=tenant)
        console.print(f"[bold green]✓ Review dashboard refreshed at:[/bold green] {dash_path}")
    else:
        console.print(f"[bold red]Could not find job with ID {args.job_id}[/bold red]")


def cmd_stage(args: argparse.Namespace) -> None:
    """Force stage an application package for a specific job ID into /inbox/."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config)
    repo = JobRepository(config.database.db_path)

    job = repo.get_job_by_id(args.job_id)
    if not job:
        console.print(f"[bold red]Could not find job with ID {args.job_id}[/bold red]")
        return

    if job.status != JobStatus.QUEUED:
        repo.update_job_status(
            job_id=job.id,
            new_status=JobStatus.QUEUED,
            tenant_id=tenant.tenant_id,
            changed_by="user",
            notes="Force-queued for application package drafting by user"
        )

    drafter = ApplicationGenerator(config=config, tenant=tenant)
    pkgs = drafter.draft_queued_jobs(job_id=job.id)
    if pkgs:
        console.print(f"[bold green]✓ Successfully force-staged application package for {job.company} - {job.title} into /inbox/![/bold green]")
    else:
        console.print("[yellow]Package drafting completed.[/yellow]")


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Generate or refresh the HTML review dashboard in /inbox/."""
    config = load_engine_config()
    tenant = _ensure_active_tenant(config, requested_id=getattr(args, "tenant_id", None))
    dash_path = generate_inbox_dashboard(config=config, tenant=tenant)
    console.print(f"[bold green]✓ HTML review dashboard generated successfully at:[/bold green] {dash_path}")


def cmd_pipeline(args: argparse.Namespace) -> None:
    """Execute end-to-end career sourcing, scoring, and application drafting pipeline."""
    config = load_engine_config()
    tenant_mgr = TenantManager(config)

    # 1. Resolve tenants (will auto-trigger setup wizard if none exist on device)
    if getattr(args, "all_tenants", False):
        tenant_ids = tenant_mgr.list_available_tenants()
    elif getattr(args, "tenant_id", None):
        tenant_ids = [args.tenant_id]
    else:
        default_tenant = _ensure_active_tenant(config)
        tenant_ids = [default_tenant.tenant_id]

    # 2. Instantiate notifier AFTER setup ensures fresh .env credentials
    notifier = NotificationService()

    console.print(BANNER)
    console.print(Panel(
        f"[bold cyan]Autonomous Career Engine Pipeline[/bold cyan]\n"
        f"Processing {len(tenant_ids)} tenant(s): {', '.join(tenant_ids)}\n"
        f"Database: {config.database.db_path}\n"
        f"Inbox: {config.engine.inbox_dir}\n"
        f"Notifications: Telegram={'[green]ON[/green]' if notifier.telegram_enabled else '[dim]OFF[/dim]'} | Gmail={'[green]ON[/green]' if notifier.email_enabled else '[dim]OFF[/dim]'}",
        title="Pipeline Execution",
        border_style="cyan"
    ))

    # Auto-refresh or discover OpenRouter models if requested or cache missing
    cache_file = PROJECT_ROOT / "data" / "openrouter_free_models.json"
    should_refresh_models = getattr(args, "refresh_models", False) or (os.environ.get("OPENROUTER_API_KEY") and not cache_file.exists())

    if should_refresh_models:
        console.print("[bold cyan]Discovering and caching active OpenRouter free models...[/bold cyan]")
        try:
            orm = OpenRouterManager()
            discovered = orm.discover_and_rank_models(force_refresh=True)
            console.print(f"[bold green]✓ Cached {len(discovered)} active OpenRouter free models at data/openrouter_free_models.json.[/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠ OpenRouter model discovery note: {e}[/yellow]")

    for tid in tenant_ids:
        tenant = tenant_mgr.get_tenant(tid)
        console.print(f"\n[bold yellow]>>> Processing Candidate Tenant: {tenant.name} ({tenant.tenant_id})[/bold yellow]")

        # Phase 1: Sourcing
        console.print("[bold blue]1. Running Multi-Channel Sourcing Pipeline...[/bold blue]")
        sourcing_mgr = SourcingManager(config=config, tenant=tenant)
        source_res = sourcing_mgr.run_sourcing_pipeline(scraper_name=getattr(args, "scraper", None), dry_run=getattr(args, "dry_run", False))

        if getattr(args, "dry_run", False):
            # Refresh HTML Review Dashboard so discovered listings are viewable
            generate_inbox_dashboard(config=config, tenant=tenant)
            console.print("\n[yellow]⚡ Dry-run mode completed: Multi-channel listings sourced and HTML dashboard refreshed at inbox/index.html.[/yellow]")
            console.print("[dim](Note: AI fit scoring and application dossier drafting into /inbox/ are bypassed in dry-run mode. Run 'python run.py pipeline' without --dry-run to generate tailored PDF resumes, cover letters, and review briefs.)[/dim]")
            continue

        # Phase 2: Scoring
        console.print("[bold blue]2. Running Opportunity Scoring Engine against Candidate Preferences...[/bold blue]")
        scorer = OpportunityScorer(config=config, tenant=tenant)
        evals = scorer.run_scoring_batch(auto_queue=True)
        queued_count = sum(1 for e in evals if getattr(e, "recommendation", None) and e.recommendation.value == "QUEUE")

        # Phase 3: Drafting
        console.print("[bold blue]3. Drafting Tailored Application Packages into /inbox/...[/bold blue]")
        drafter = ApplicationGenerator(config=config, tenant=tenant)
        pkgs = drafter.draft_queued_jobs()

        # Phase 4: Notifications
        notifier.notify_pipeline_run(
            tenant_name=tenant.name,
            total_discovered=source_res.get("total_discovered", 0),
            new_jobs=source_res.get("new_jobs", 0),
            queued_count=queued_count,
            staged_packages=len(pkgs),
            warnings=source_res.get("warnings", [])
        )

        # Phase 5: Refresh HTML Review Dashboard
        generate_inbox_dashboard(config=config, tenant=tenant)

    console.print("\n[bold green]✓ End-to-End Pipeline Execution Finished Successfully.[/bold green]")


def cmd_test_notify(args: argparse.Namespace) -> None:
    """Test Telegram bot and Gmail SMTP notifications using current .env configuration."""
    notifier = NotificationService()

    console.print(Panel(
        f"[bold cyan]Notification Service Test Diagnostic[/bold cyan]\n"
        f"• Telegram Bot Token: {'[green]Configured[/green]' if notifier.telegram_token else '[red]Missing (TELEGRAM_BOT_TOKEN)[/red]'}\n"
        f"• Telegram Chat ID: {'[green]Configured[/green]' if notifier.telegram_chat_id else '[red]Missing (TELEGRAM_CHAT_ID)[/red]'}\n"
        f"• Gmail SMTP User: {notifier.smtp_user or '[red]Missing (SMTP_USER)[/red]'}\n"
        f"• Notification Recipient Email: {notifier.notification_email or '[red]Missing[/red]'}",
        title="Notification Diagnostics",
        border_style="yellow"
    ))

    if notifier.telegram_enabled:
        console.print("[cyan]Sending test message to Telegram...[/cyan]")
        tg_ok = notifier.send_telegram(
            "🔔 <b>Autonomous Career Engine Test Notification</b>\n\n"
            "Your Telegram notification channel is correctly configured! 🚀",
            parse_mode="HTML"
        )
        if tg_ok:
            console.print("[bold green]✓ Telegram test notification delivered successfully![/bold green]")
        else:
            console.print("[bold red]✗ Failed to send Telegram notification. Check Bot Token and Chat ID.[/bold red]")
    else:
        console.print("[yellow]⚠ Telegram notifications disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env).[/yellow]")

    if notifier.email_enabled:
        console.print(f"[cyan]Sending test email via Gmail SMTP to {notifier.notification_email}...[/cyan]")
        email_ok = notifier.send_email(
            subject="🔔 Autonomous Career Engine Test Notification",
            body_text="Your Gmail SMTP notification channel is operational!",
            body_html="<h3>🔔 Autonomous Career Engine Test Notification</h3><p>Your notification channel is operational! 🚀</p>"
        )
        if email_ok:
            console.print(f"[bold green]✓ Gmail SMTP test email delivered successfully to {notifier.notification_email}![/bold green]")
        else:
            console.print("[bold red]✗ Failed to send Gmail SMTP email.[/bold red]")


def cmd_refresh_models(args: argparse.Namespace) -> None:
    """Discover, rank, and cache active OpenRouter free models."""
    mgr = OpenRouterManager()
    models = mgr.discover_and_rank_models(limit=args.limit, force_refresh=True)
    console.print(f"[bold green]✓ Discovered and cached {len(models)} ranked OpenRouter free models.[/bold green]")
    for i, m in enumerate(models, 1):
        console.print(f" {i:2d}. [bold cyan]{m.id:<50}[/bold cyan] (Score: [yellow]{m.score:4.2f}[/yellow] | Ctx: {m.context_length:,} tokens | {m.name})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Career Engine (ACE) CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    p_setup = subparsers.add_parser("setup", help="Interactive setup wizard for API keys and candidate onboarding")
    p_setup.set_defaults(func=cmd_setup)

    # import-cv
    p_imp = subparsers.add_parser("import-cv", help="Ingest a PDF or Markdown CV and extract structured sources")
    p_imp.add_argument("file_path", type=str, help="Path to CV file (.pdf, .md, .txt)")
    p_imp.add_argument("--tenant-id", type=str, help="Tenant ID (defaults to active tenant)")
    p_imp.set_defaults(func=cmd_import_cv)

    # tenant
    p_ten = subparsers.add_parser("tenant", help="Manage candidate tenants on this device")
    p_ten_sub = p_ten.add_subparsers(dest="tenant_action", help="Tenant actions")

    p_ten_list = p_ten_sub.add_parser("list", help="List all candidate tenants")
    p_ten_list.set_defaults(func=cmd_tenant)

    p_ten_create = p_ten_sub.add_parser("create", help="Create a new candidate tenant")
    p_ten_create.set_defaults(func=cmd_tenant)

    p_ten_switch = p_ten_sub.add_parser("switch", help="Switch active tenant")
    p_ten_switch.add_argument("target_tenant_id", type=str, help="Tenant ID to activate")
    p_ten_switch.set_defaults(func=cmd_tenant)

    p_ten_show = p_ten_sub.add_parser("show", help="Show tenant profile details")
    p_ten_show.add_argument("target_tenant_id", type=str, nargs="?", help="Tenant ID to display")
    p_ten_show.set_defaults(func=cmd_tenant)

    # companies (manage target companies and career portals)
    p_comp = subparsers.add_parser("companies", help="Manage target company career portals for candidate tenant")
    p_comp_sub = p_comp.add_subparsers(dest="companies_action", help="Companies actions")

    p_comp_list = p_comp_sub.add_parser("list", help="List configured target companies")
    p_comp_list.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_comp_list.set_defaults(func=cmd_companies)

    p_comp_add = p_comp_sub.add_parser("add", help="Add or update a target company career portal")
    p_comp_add.add_argument("name", type=str, help="Company name (e.g., 'ASML', 'Baykar')")
    p_comp_add.add_argument("url", type=str, help="Career portal URL (e.g., 'https://www.asml.com/en/careers')")
    p_comp_add.add_argument("--location", type=str, help="Company headquarters or target location")
    p_comp_add.add_argument("--keywords", type=str, help="Comma-separated focus keywords or tags")
    p_comp_add.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_comp_add.set_defaults(func=cmd_companies)

    p_comp_rem = p_comp_sub.add_parser("remove", help="Remove a target company from candidate target list")
    p_comp_rem.add_argument("name", type=str, help="Company name to remove")
    p_comp_rem.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_comp_rem.set_defaults(func=cmd_companies)

    # pipeline (full automated run)
    p_pipe = subparsers.add_parser("pipeline", help="Run full sourcing, scoring, and drafting pipeline")
    p_pipe.add_argument("--tenant-id", type=str, help="Specific tenant ID (defaults to active tenant)")
    p_pipe.add_argument("--all-tenants", action="store_true", help="Process all available tenants sequentially")
    p_pipe.add_argument("--scraper", type=str, choices=list(SCRAPER_REGISTRY.keys()), help="Run specific scraper")
    p_pipe.add_argument("--dry-run", action="store_true", help="Run sourcing dry-run without persistence/scoring")
    p_pipe.add_argument("--refresh-models", action="store_true", help="Refresh OpenRouter free model cache before execution")
    p_pipe.set_defaults(func=cmd_pipeline)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Generate or refresh HTML review dashboard in /inbox/")
    p_dash.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_dash.set_defaults(func=cmd_dashboard)

    # refresh-models
    p_ref = subparsers.add_parser("refresh-models", help="Discover and cache active OpenRouter free models")
    p_ref.add_argument("--limit", type=int, default=10, help="Number of models to rank and display")
    p_ref.set_defaults(func=cmd_refresh_models)

    # test-notify
    p_notif = subparsers.add_parser("test-notify", help="Test Telegram and Gmail SMTP notification delivery")
    p_notif.set_defaults(func=cmd_test_notify)

    # init-db
    p_init = subparsers.add_parser("init-db", help="Initialize database schema")
    p_init.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_init.set_defaults(func=cmd_init_db)

    # status
    p_stat = subparsers.add_parser("status", help="View system and job statistics")
    p_stat.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_stat.set_defaults(func=cmd_status)

    # list-jobs
    p_list = subparsers.add_parser("list-jobs", help="List stored jobs")
    p_list.add_argument("--status", type=str, choices=list(JobStatus._value2member_map_.keys()), help="Filter by status")
    p_list.add_argument("--track", type=str, choices=list(TrackType._value2member_map_.keys()), help="Filter by track")
    p_list.add_argument("--limit", type=int, default=20, help="Limit output results")
    p_list.set_defaults(func=cmd_list_jobs)

    # source
    p_source = subparsers.add_parser("source", help="Run multi-channel sourcing pipeline")
    p_source.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_source.add_argument("--scraper", type=str, choices=list(SCRAPER_REGISTRY.keys()), help="Run specific scraper")
    p_source.add_argument("--dry-run", action="store_true", help="Fetch listings without persisting to DB")
    p_source.set_defaults(func=cmd_source)

    # score
    p_score = subparsers.add_parser("score", help="Run opportunity scoring engine")
    p_score.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_score.add_argument("--job-id", type=str, help="Specific job ID to score")
    p_score.add_argument("--auto-queue", action="store_true", default=True, help="Auto-queue high scoring jobs")
    p_score.set_defaults(func=cmd_score)

    # draft
    p_draft = subparsers.add_parser("draft", help="Generate application packages into /inbox/")
    p_draft.add_argument("--tenant-id", type=str, help="Tenant ID")
    p_draft.add_argument("--job-id", type=str, help="Specific job ID to draft")
    p_draft.set_defaults(func=cmd_draft)

    # list-inbox
    p_inbox = subparsers.add_parser("list-inbox", help="List staged application packages in /inbox/")
    p_inbox.set_defaults(func=cmd_list_inbox)

    # approve
    p_appr = subparsers.add_parser("approve", help="Approve staged package and mark as APPLIED")
    p_appr.add_argument("job_id", type=str, help="Job ID to approve")
    p_appr.set_defaults(func=cmd_approve)

    # reject
    p_rej = subparsers.add_parser("reject", help="Reject a job listing")
    p_rej.add_argument("job_id", type=str, help="Job ID to reject")
    p_rej.set_defaults(func=cmd_reject)

    # stage
    p_stage = subparsers.add_parser("stage", help="Force stage application package for a specific job ID into /inbox/")
    p_stage.add_argument("job_id", type=str, help="Job ID or prefix to force stage")
    p_stage.set_defaults(func=cmd_stage)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
