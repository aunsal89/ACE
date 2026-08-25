"""Career Engine Command Line Interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import load_engine_config, load_tenant_profile, TenantManager
from src.database.connection import init_db
from src.database.models import JobStatus, TrackType
from src.database.repository import JobRepository
from src.sourcing.manager import SourcingManager, SCRAPER_REGISTRY
from src.scoring.scorer import OpportunityScorer
from src.applicator.generator import ApplicationGenerator
from src.utils.hashing import generate_deduplication_hash, normalize_company, normalize_title
from src.utils.notifications import NotificationService

console = Console()


def cmd_init_db(args: argparse.Namespace) -> None:
    """Initialize the SQLite database schema."""
    config = load_engine_config()
    init_db(config.database.db_path)
    repo = JobRepository(config.database.db_path)
    tenant = load_tenant_profile(config=config)
    repo.register_or_update_tenant(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        email=tenant.email,
        config_path=str(config.multi_tenancy.tenants_dir / tenant.tenant_id / "profile.yaml")
    )
    console.print(f"[bold green]✓ Database initialized successfully at:[/bold green] {config.database.db_path}")
    console.print(f"[bold green]✓ Active tenant registered:[/bold green] {tenant.name} ([cyan]{tenant.tenant_id}[/cyan])")


def cmd_status(args: argparse.Namespace) -> None:
    """Display system overview and database statistics."""
    config = load_engine_config()
    tenant = load_tenant_profile(config=config)
    repo = JobRepository(config.database.db_path)
    stats = repo.get_stats()

    console.print(Panel.fit(
        f"[bold cyan]Career Engine & Portfolio Synchronizer[/bold cyan] v{config.engine.version}\n"
        f"[bold]Environment:[/bold] {config.engine.environment} | [bold]Log Level:[/bold] {config.engine.log_level}\n"
        f"[bold]Active Tenant:[/bold] [yellow]{tenant.name}[/yellow] ([cyan]{tenant.tenant_id}[/cyan])\n"
        f"[bold]DB Path:[/bold] {config.database.db_path}\n"
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


def cmd_show_tenant(args: argparse.Namespace) -> None:
    """Display active tenant profile and dual-track goals."""
    config = load_engine_config()
    tenant = load_tenant_profile(tenant_id=args.tenant_id, config=config)

    console.print(Panel(
        f"[bold green]Tenant:[/bold green] {tenant.name} ([cyan]{tenant.tenant_id}[/cyan])\n"
        f"[bold]Email:[/bold] {tenant.email} | [bold]Phone:[/bold] {tenant.phone}\n"
        f"[bold]Current Location:[/bold] {tenant.location_current}\n"
        f"[bold]Portfolio URL:[/bold] {tenant.links.website}\n"
        f"[bold]AURA Yield URL:[/bold] {tenant.links.aura_showcase}\n"
        f"[bold]CV Markdown Truth:[/bold] {tenant.sources_of_truth.cv_markdown}",
        title=f"Tenant Profile: {tenant.name}",
        border_style="green"
    ))


def cmd_list_jobs(args: argparse.Namespace) -> None:
    """List job listings in database."""
    config = load_engine_config()
    repo = JobRepository(config.database.db_path)
    status_filter = JobStatus(args.status) if args.status else None
    track_filter = TrackType(args.track) if args.track else None

    jobs = repo.list_jobs(status=status_filter, track=track_filter, limit=args.limit)

    if not jobs:
        console.print("[yellow]No job listings found matching criteria.[/yellow]")
        return

    table = Table(title=f"Job Listings ({len(jobs)} shown)", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Company", style="green")
    table.add_column("Location", style="dim")
    table.add_column("Track", style="yellow")
    table.add_column("Status", style="bold")

    for j in jobs:
        status_color = "cyan" if j.status == JobStatus.DISCOVERED else "green" if j.status == JobStatus.QUEUED else "red" if j.status == JobStatus.REJECTED else "white"
        table.add_row(
            j.id[:8],
            j.title[:30],
            j.company[:20],
            (j.location or "N/A")[:18],
            j.assigned_track.value,
            f"[{status_color}]{j.status.value}[/{status_color}]"
        )

    console.print(table)


def cmd_source(args: argparse.Namespace) -> None:
    """Execute the multi-channel sourcing pipeline."""
    manager = SourcingManager()
    manager.run_sourcing_pipeline(scraper_name=args.scraper, dry_run=args.dry_run)


def cmd_score(args: argparse.Namespace) -> None:
    """Evaluate discovered opportunities against tenant criteria."""
    scorer = OpportunityScorer()
    scorer.run_scoring_batch(job_id=args.job_id, auto_queue=args.auto_queue)


def cmd_draft(args: argparse.Namespace) -> None:
    """Draft application packages into /inbox/."""
    drafter = ApplicationGenerator()
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
    table.add_column("Track", style="yellow")
    table.add_column("Status", style="bold")
    table.add_column("Resume PDF", style="cyan")
    table.add_column("Cover Letter PDF", style="cyan")

    for p in pkgs:
        table.add_row(
            p.job_id[:8],
            p.track,
            p.status.value,
            Path(p.resume_pdf_path or "").name,
            Path(p.cover_letter_pdf_path or "").name
        )

    console.print(table)


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a staged application package and mark as APPLIED."""
    config = load_engine_config()
    tenant = load_tenant_profile(config=config)
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
    else:
        console.print(f"[bold red]Could not find job with ID {args.job_id}[/bold red]")


def cmd_reject(args: argparse.Namespace) -> None:
    """Reject a job opportunity."""
    config = load_engine_config()
    tenant = load_tenant_profile(config=config)
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
    else:
        console.print(f"[bold red]Could not find job with ID {args.job_id}[/bold red]")


def cmd_test_dedup(args: argparse.Namespace) -> None:
    """Run deduplication hashing tests on sample inputs."""
    samples = [
        ("Baykar Teknoloji A.Ş.", "Gömülü Yazılım Lideri (m/w/d)", "Istanbul", "https://kariyer.baykartech.com/job/101?utm_source=linkedin"),
        ("Baykar", "Gömülü Yazılım Lideri", "Istanbul", "https://kariyer.baykartech.com/job/101"),
        ("ASELSAN Elektronik Sanayi ve Ticaret A.Ş.", "Lead Embedded Software Architect [Remote]", "Ankara", "https://aselsan.com/careers/99"),
        ("Aselsan", "Lead Embedded Software Architect", "Ankara", "https://aselsan.com/careers/99?ref=jobboard"),
    ]

    table = Table(title="Deduplication Hashing Demonstration", show_header=True, header_style="bold blue")
    table.add_column("Raw Input (Company | Title | Location | URL)", style="dim")
    table.add_column("Normalized Key", style="yellow")
    table.add_column("Generated Hash (SHA-256)", style="bold green")

    for comp, titl, loc, url in samples:
        norm_comp = normalize_company(comp)
        norm_titl = normalize_title(titl)
        h = generate_deduplication_hash(company=comp, title=titl, location=loc, url=url)
        table.add_row(f"{comp} | {titl} | {loc} | {url[:30]}...", f"{norm_comp}::{norm_titl}", h[:16] + "...")

    console.print(table)


def cmd_pipeline(args: argparse.Namespace) -> None:
    """Execute end-to-end career sourcing, scoring, and application drafting pipeline."""
    config = load_engine_config()
    tenant_mgr = TenantManager(config)
    notifier = NotificationService()

    if getattr(args, "all_tenants", False):
        tenant_ids = tenant_mgr.list_available_tenants()
    elif getattr(args, "tenant_id", None):
        tenant_ids = [args.tenant_id]
    else:
        tenant_ids = [config.multi_tenancy.active_tenant]

    console.print(Panel(
        f"[bold cyan]Career Engine Autonomous Pipeline[/bold cyan]\n"
        f"Processing {len(tenant_ids)} tenant(s): {', '.join(tenant_ids)}\n"
        f"Database: {config.database.db_path}\n"
        f"Inbox: {config.engine.inbox_dir}\n"
        f"Notifications: Telegram={'[green]ON[/green]' if notifier.telegram_enabled else '[dim]OFF[/dim]'} | Gmail={'[green]ON[/green]' if notifier.email_enabled else '[dim]OFF[/dim]'}",
        title="Pipeline Execution",
        border_style="cyan"
    ))

    for tid in tenant_ids:
        tenant = tenant_mgr.get_tenant(tid)
        console.print(f"\n[bold yellow]>>> Processing Tenant: {tenant.name} ({tenant.tenant_id})[/bold yellow]")

        # Phase 1: Sourcing
        console.print("[bold blue]1. Running Multi-Channel Sourcing Pipeline...[/bold blue]")
        sourcing_mgr = SourcingManager(config=config, tenant=tenant)
        source_res = sourcing_mgr.run_sourcing_pipeline(scraper_name=getattr(args, "scraper", None), dry_run=getattr(args, "dry_run", False))

        if getattr(args, "dry_run", False):
            console.print("[yellow]Dry-run enabled: skipping scoring, drafting, and notifications.[/yellow]")
            continue

        # Phase 2: Scoring
        console.print("[bold blue]2. Running Opportunity Scoring Engine...[/bold blue]")
        scorer = OpportunityScorer(config=config, tenant=tenant)
        evals = scorer.run_scoring_batch(auto_queue=True)
        queued_count = sum(1 for e in evals if getattr(e, "recommendation", None) and e.recommendation.value == "QUEUE")

        # Phase 3: Drafting
        console.print("[bold blue]3. Drafting Tailored Application Packages into /inbox/...[/bold blue]")
        drafter = ApplicationGenerator(config=config, tenant=tenant)
        pkgs = drafter.draft_queued_jobs()

        # Phase 4: Dispatch Notifications
        notifier.notify_pipeline_run(
            tenant_name=tenant.name,
            total_discovered=source_res.get("total_discovered", 0),
            new_jobs=source_res.get("new_jobs", 0),
            queued_count=queued_count,
            staged_packages=len(pkgs)
        )

    console.print("\n[bold green]✓ End-to-End Pipeline Execution Finished.[/bold green]")


def cmd_test_notify(args: argparse.Namespace) -> None:
    """Test Telegram bot and Gmail SMTP notifications using current .env configuration."""
    notifier = NotificationService()

    console.print(Panel(
        f"[bold cyan]Notification Service Test Diagnostic[/bold cyan]\n"
        f"• Telegram Bot Token Configured: {'[green]Yes[/green]' if notifier.telegram_token else '[red]No (TELEGRAM_BOT_TOKEN missing)[/red]'}\n"
        f"• Telegram Chat ID Configured: {'[green]Yes[/green]' if notifier.telegram_chat_id else '[red]No (TELEGRAM_CHAT_ID missing)[/red]'}\n"
        f"• Gmail SMTP User: {notifier.smtp_user or '[red]Missing (SMTP_USER)[/red]'}\n"
        f"• Gmail SMTP Pass: {'[green]Configured[/green]' if notifier.smtp_password else '[red]Missing (SMTP_PASSWORD)[/red]'}\n"
        f"• Notification Recipient Email: {notifier.notification_email or '[red]Missing[/red]'}",
        title="Notification Diagnostics",
        border_style="yellow"
    ))

    # Test Telegram
    if notifier.telegram_enabled:
        console.print("[cyan]Sending test message to Telegram...[/cyan]")
        tg_ok = notifier.send_telegram(
            "🔔 <b>Career Engine Test Notification</b>\n\n"
            "Your Telegram notification channel is correctly configured and operational! 🚀",
            parse_mode="HTML"
        )
        if tg_ok:
            console.print("[bold green]✓ Telegram test notification delivered successfully![/bold green]")
        else:
            console.print("[bold red]✗ Failed to send Telegram test notification. Check your Bot Token and Chat ID.[/bold red]")
    else:
        console.print("[yellow]⚠ Telegram notifications disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to enable).[/yellow]")

    # Test Email
    if notifier.email_enabled:
        console.print(f"[cyan]Sending test email via Gmail SMTP to {notifier.notification_email}...[/cyan]")
        email_ok = notifier.send_email(
            subject="🔔 Career Engine Test Notification",
            body_text="Your Gmail SMTP notification channel is correctly configured and operational!",
            body_html="<h3>🔔 Career Engine Test Notification</h3><p>Your Gmail SMTP notification channel is correctly configured and operational! 🚀</p>"
        )
        if email_ok:
            console.print(f"[bold green]✓ Gmail SMTP test email delivered successfully to {notifier.notification_email}![/bold green]")
        else:
            console.print("[bold red]✗ Failed to send Gmail SMTP test email. Verify your Gmail App Password and 2-Step Verification.[/bold red]")
    else:
        console.print("[yellow]⚠ Gmail notifications disabled (set SMTP_USER, SMTP_PASSWORD, and NOTIFICATION_EMAIL in .env to enable).[/yellow]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Career Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # pipeline (full automated run)
    p_pipe = subparsers.add_parser("pipeline", help="Run full sourcing, scoring, and drafting pipeline")
    p_pipe.add_argument("--tenant-id", type=str, help="Specific tenant ID (defaults to active tenant)")
    p_pipe.add_argument("--all-tenants", action="store_true", help="Process all available tenants sequentially")
    p_pipe.add_argument("--scraper", type=str, choices=list(SCRAPER_REGISTRY.keys()), help="Run specific scraper")
    p_pipe.add_argument("--dry-run", action="store_true", help="Run sourcing dry-run without persistence/scoring")
    p_pipe.set_defaults(func=cmd_pipeline)

    # test-notify
    p_notif = subparsers.add_parser("test-notify", help="Test Telegram and Gmail SMTP notification delivery")
    p_notif.set_defaults(func=cmd_test_notify)

    # init-db
    p_init = subparsers.add_parser("init-db", help="Initialize database schema")
    p_init.set_defaults(func=cmd_init_db)

    # status
    p_stat = subparsers.add_parser("status", help="View system and job statistics")
    p_stat.set_defaults(func=cmd_status)

    # show-tenant
    p_tenant = subparsers.add_parser("show-tenant", help="Display active tenant profile")
    p_tenant.add_argument("--tenant-id", type=str, default=None, help="Tenant ID")
    p_tenant.set_defaults(func=cmd_show_tenant)

    # list-jobs
    p_list = subparsers.add_parser("list-jobs", help="List stored jobs")
    p_list.add_argument("--status", type=str, choices=list(JobStatus._value2member_map_.keys()), help="Filter by status")
    p_list.add_argument("--track", type=str, choices=list(TrackType._value2member_map_.keys()), help="Filter by track")
    p_list.add_argument("--limit", type=int, default=20, help="Limit output results")
    p_list.set_defaults(func=cmd_list_jobs)

    # source
    p_source = subparsers.add_parser("source", help="Run multi-channel sourcing pipeline")
    p_source.add_argument("--scraper", type=str, choices=list(SCRAPER_REGISTRY.keys()), help="Run specific scraper")
    p_source.add_argument("--dry-run", action="store_true", help="Fetch listings without persisting to DB")
    p_source.set_defaults(func=cmd_source)

    # score
    p_score = subparsers.add_parser("score", help="Run opportunity scoring engine")
    p_score.add_argument("--job-id", type=str, help="Specific job ID to score")
    p_score.add_argument("--auto-queue", action="store_true", default=True, help="Auto-queue high scoring jobs")
    p_score.set_defaults(func=cmd_score)

    # draft
    p_draft = subparsers.add_parser("draft", help="Generate application packages into /inbox/")
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

    # test-dedup
    p_dedup = subparsers.add_parser("test-dedup", help="Test deduplication hashing algorithm")
    p_dedup.set_defaults(func=cmd_test_dedup)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
