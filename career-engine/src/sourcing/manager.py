"""Master Sourcing Pipeline Orchestrator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type
from rich.table import Table

from src.config import EngineConfig, TenantProfile, load_engine_config, load_tenant_profile
from src.database.models import JobListing, JobListingCreate
from src.database.repository import JobRepository
from src.sourcing.base import BaseScraper
from src.sourcing.google_jobs import GoogleJobsScraper
from src.sourcing.apify_linkedin import ApifyLinkedInScraper
from src.sourcing.defense.baykar import BaykarScraper
from src.sourcing.defense.aselsan import AselsanScraper
from src.sourcing.defense.vizyoner_genc import VizyonerGencScraper
from src.sourcing.defense.tusas_roketsan import TusasScraper, RoketsanScraper
from src.utils.logger import console, logger


SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {
    "google_jobs": GoogleJobsScraper,
    "apify_linkedin": ApifyLinkedInScraper,
    "baykar": BaykarScraper,
    "aselsan": AselsanScraper,
    "vizyoner_genc": VizyonerGencScraper,
    "tusas": TusasScraper,
    "roketsan": RoketsanScraper,
}


class SourcingManager:
    """Orchestrates all active scrapers, aggregates jobs, and ingests into DB with deduplication."""

    def __init__(self, config: Optional[EngineConfig] = None, tenant: Optional[TenantProfile] = None):
        self.config = config or load_engine_config()
        self.tenant = tenant or load_tenant_profile(config=self.config)
        self.repo = JobRepository(self.config.database.db_path)

    def get_active_scrapers(self, selected_scraper: Optional[str] = None) -> List[BaseScraper]:
        """Instantiate configured scrapers."""
        scrapers: List[BaseScraper] = []
        configured = self.config.sourcing.scrapers

        for name, cls in SCRAPER_REGISTRY.items():
            if selected_scraper and name != selected_scraper:
                continue
            cfg = configured.get(name)
            if cfg and not cfg.enabled:
                continue
            scrapers.append(cls(self.config.sourcing, self.tenant))

        return scrapers

    def run_sourcing_pipeline(self, scraper_name: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Execute full sourcing run across all active scrapers.
        Ingests into SQLite and deduplicates against existing records.
        """
        scrapers = self.get_active_scrapers(scraper_name)
        total_discovered = 0
        new_jobs = 0
        existing_jobs = 0
        scraper_stats: Dict[str, Dict[str, int]] = {}
        all_warnings: List[str] = []

        console.print(f"[bold cyan]Starting Sourcing Pipeline for Tenant:[/bold cyan] [yellow]{self.tenant.name}[/yellow] ([green]{len(scrapers)} scrapers active[/green])")

        for s in scrapers:
            s_name = s.source_name
            try:
                listings = s.run()
                s_new = 0
                s_dup = 0
                for job_in in listings:
                    total_discovered += 1
                    if not dry_run:
                        _, is_new = self.repo.upsert_job(job_in)
                        if is_new:
                            new_jobs += 1
                            s_new += 1
                        else:
                            existing_jobs += 1
                            s_dup += 1
                    else:
                        new_jobs += 1
                        s_new += 1

                scraper_stats[s_name] = {"total": len(listings), "new": s_new, "duplicate": s_dup}
                logger.info(f"Scraper [{s_name}]: {len(listings)} found ({s_new} new, {s_dup} existing)")

                if hasattr(s, "warnings") and s.warnings:
                    for w in s.warnings:
                        if w not in all_warnings:
                            all_warnings.append(w)
            except Exception as e:
                err_msg = f"Scraper [{s_name}] failed: {e}"
                logger.error(err_msg)
                all_warnings.append(err_msg)
                scraper_stats[s_name] = {"total": 0, "new": 0, "duplicate": 0, "error": 1}

        # Print Rich Summary Table
        table = Table(title="Sourcing Execution Summary", show_header=True, header_style="bold blue")
        table.add_column("Scraper / Channel", style="cyan")
        table.add_column("Listings Fetched", justify="right", style="bold")
        table.add_column("New Opportunities", justify="right", style="green")
        table.add_column("Deduplicated / Updated", justify="right", style="dim")

        for s_name, st in scraper_stats.items():
            table.add_row(s_name, str(st.get("total", 0)), str(st.get("new", 0)), str(st.get("duplicate", 0)))

        table.add_section()
        table.add_row("[bold]TOTAL[/bold]", f"[bold]{total_discovered}[/bold]", f"[bold green]{new_jobs}[/bold green]", f"[bold dim]{existing_jobs}[/bold dim]")
        console.print(table)

        if all_warnings:
            console.print("\n[bold yellow]⚠️  Channel Warnings / Degradation Alerts:[/bold yellow]")
            for w in all_warnings:
                console.print(f"  [yellow]• {w}[/yellow]")

        return {
            "total_discovered": total_discovered,
            "new_jobs": new_jobs,
            "existing_jobs": existing_jobs,
            "scraper_stats": scraper_stats,
            "warnings": all_warnings,
            "dry_run": dry_run
        }
