"""Configuration schema and loader for Autonomous Career Engine using Pydantic V2."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import yaml
from pydantic import BaseModel, Field, field_validator

# Determine project root dynamically (OS-agnostic)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Automatically discover and load .env files
for _candidate_env in [
    PROJECT_ROOT / ".env",
    Path.cwd() / ".env",
    Path.home() / ".ace" / ".env",
]:
    if _candidate_env.exists():
        load_dotenv(_candidate_env, override=False)


def _resolve_project_path(v: Any, default_relative: str = ".") -> Path:
    """Resolve a path against PROJECT_ROOT if not already absolute."""
    if not v:
        return (PROJECT_ROOT / default_relative).resolve()
    p = Path(v).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (PROJECT_ROOT / p).resolve()


class EngineSettings(BaseModel):
    name: str = "Autonomous Career Engine"
    version: str = "0.3.0"
    environment: str = "production"
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    inbox_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "inbox")
    log_level: str = "INFO"

    @field_validator("data_dir", mode="before")
    @classmethod
    def parse_data_dir(cls, v: Any) -> Path:
        return _resolve_project_path(v, "data")

    @field_validator("inbox_dir", mode="before")
    @classmethod
    def parse_inbox_dir(cls, v: Any) -> Path:
        return _resolve_project_path(v, "inbox")


class DatabaseSettings(BaseModel):
    db_path: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "career_engine.db")
    wal_mode: bool = True
    timeout_seconds: float = 30.0
    foreign_keys: bool = True

    @field_validator("db_path", mode="before")
    @classmethod
    def parse_db_path(cls, v: Any) -> Path:
        return _resolve_project_path(v, "data/career_engine.db")


class LLMModelConfig(BaseModel):
    model: Optional[str] = None
    models: Optional[List[str]] = None
    temperature: float = 0.2
    max_output_tokens: int = 4096


class LLMSettings(BaseModel):
    default_provider: str = "google-genai"
    fallback_chain: List[str] = Field(default_factory=lambda: ["google-genai", "openrouter"])
    providers: Dict[str, LLMModelConfig] = Field(default_factory=dict)


class ScraperConfig(BaseModel):
    enabled: bool = True
    priority: int = 1
    since_date: Optional[str] = None

    model_config = {"extra": "allow"}


class SourcingSettings(BaseModel):
    request_timeout: int = 35
    max_retries: int = 3
    rate_limit_per_minute: int = 30
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 AutonomousCareerEngine/0.3.0"
    )
    scrapers: Dict[str, ScraperConfig] = Field(default_factory=dict)


class MultiTenancySettings(BaseModel):
    active_tenant: str = "default"
    tenants_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "config" / "tenants")

    @field_validator("tenants_dir", mode="before")
    @classmethod
    def parse_tenants_dir(cls, v: Any) -> Path:
        return _resolve_project_path(v, "config/tenants")


class EngineConfig(BaseModel):
    engine: EngineSettings = Field(default_factory=EngineSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    sourcing: SourcingSettings = Field(default_factory=SourcingSettings)
    multi_tenancy: MultiTenancySettings = Field(default_factory=MultiTenancySettings)


# --- Tenant Profile Schemas ---

class CompensationConfig(BaseModel):
    min_monthly_net_usd: float = 6000.0
    currency: str = "USD"
    period: str = "monthly"
    type: str = "net"


class ExperienceRequirements(BaseModel):
    min_total_years: int = 5
    min_leadership_years: int = 0
    max_team_size_managed: int = 0


class TrackAProfile(BaseModel):
    name: str = "Primary Target Career Track"
    enabled: bool = True
    target_titles: List[str] = Field(default_factory=list)
    target_sectors: List[str] = Field(default_factory=list)
    target_locations: List[str] = Field(default_factory=list)
    compensation: CompensationConfig = Field(default_factory=CompensationConfig)
    experience_requirements: ExperienceRequirements = Field(default_factory=ExperienceRequirements)
    core_competencies: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)


class ShowcaseAsset(BaseModel):
    name: str
    url: str
    summary: str = ""


class TrackBProfile(BaseModel):
    name: str = "Secondary Target Career Track"
    enabled: bool = False
    target_titles: List[str] = Field(default_factory=list)
    target_regions: List[str] = Field(default_factory=list)
    target_cities: List[str] = Field(default_factory=list)
    excluded_regions: List[str] = Field(default_factory=list)
    core_competencies: List[str] = Field(default_factory=list)
    showcase_asset: Optional[ShowcaseAsset] = None


class TracksConfig(BaseModel):
    track_a: TrackAProfile = Field(default_factory=TrackAProfile)
    track_b: TrackBProfile = Field(default_factory=TrackBProfile)


class ProductEngineeringShowcase(BaseModel):
    name: str
    url: Optional[str] = None
    repo: Optional[str] = None
    summary: str = ""
    stack: List[str] = Field(default_factory=list)


class TenantLinks(BaseModel):
    website: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio_showcase: Optional[str] = None


class SourcesOfTruth(BaseModel):
    cv_markdown: Optional[Path] = None
    education_markdown: Optional[Path] = None
    skills_toolbox: Optional[Path] = None
    portfolio_root: Optional[Path] = None

    @field_validator("cv_markdown", "education_markdown", "skills_toolbox", "portfolio_root", mode="before")
    @classmethod
    def parse_path_opt(cls, v: Any) -> Optional[Path]:
        if not v:
            return None
        p = Path(v).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (PROJECT_ROOT / p).resolve()


class GenerationPreferences(BaseModel):
    tailored_cv_format: str = "markdown_and_pdf"
    cover_letter_format: str = "markdown_and_pdf"
    staging_inbox: Path = Field(default_factory=lambda: PROJECT_ROOT / "inbox")
    tone: str = "Executive, Highly Competent, Metric-Driven, Direct"

    @field_validator("staging_inbox", mode="before")
    @classmethod
    def parse_inbox_path(cls, v: Any) -> Path:
        return _resolve_project_path(v, "inbox")


class TenantProfile(BaseModel):
    tenant_id: str
    name: str
    email: str
    phone: Optional[str] = None
    location_current: str = "Remote / Anywhere"
    links: TenantLinks = Field(default_factory=TenantLinks)
    sources_of_truth: SourcesOfTruth = Field(default_factory=SourcesOfTruth)
    tracks: TracksConfig = Field(default_factory=TracksConfig)
    product_engineering_showcase: Optional[ProductEngineeringShowcase] = None
    generation_preferences: GenerationPreferences = Field(default_factory=GenerationPreferences)


def load_engine_config(config_path: Optional[str | Path] = None) -> EngineConfig:
    """Load and validate the engine configuration from YAML."""
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "config.yaml"
    else:
        config_path = Path(config_path).expanduser().resolve()

    if not config_path.exists():
        # Fallback to default instantiated config if config.yaml does not exist
        return EngineConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    return EngineConfig.model_validate(raw_data)


def load_tenant_profile(tenant_id: Optional[str] = None, config: Optional[EngineConfig] = None) -> TenantProfile:
    """Load and validate a tenant profile from YAML."""
    if config is None:
        config = load_engine_config()

    target_tenant_id = tenant_id or config.multi_tenancy.active_tenant
    tenant_dir = config.multi_tenancy.tenants_dir / target_tenant_id
    tenant_file = tenant_dir / "profile.yaml"

    if not tenant_file.exists():
        # Check if an example profile or any tenant exists
        available = TenantManager(config).list_available_tenants()
        if available:
            # Fall back to first available tenant if active_tenant not found
            fallback_id = available[0]
            tenant_dir = config.multi_tenancy.tenants_dir / fallback_id
            tenant_file = tenant_dir / "profile.yaml"
        else:
            raise FileNotFoundError(
                f"No tenant profile found for '{target_tenant_id}' at {tenant_file}. "
                f"Please run `python run.py setup` or `python run.py tenant create` to initialize your candidate profile."
            )

    with open(tenant_file, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    # If relative paths exist inside sources_of_truth, resolve them relative to tenant_dir
    sources = raw_data.get("sources_of_truth", {})
    for key in ["cv_markdown", "education_markdown", "skills_toolbox"]:
        val = sources.get(key)
        if val and not Path(val).is_absolute():
            # Check tenant_dir / val first, then PROJECT_ROOT / val
            candidate_p = tenant_dir / val
            if candidate_p.exists():
                sources[key] = str(candidate_p.resolve())
            else:
                sources[key] = str((PROJECT_ROOT / val).resolve())
    raw_data["sources_of_truth"] = sources

    return TenantProfile.model_validate(raw_data)


class TenantManager:
    """Manages multiple tenant profiles for multi-tenant execution on a single device."""

    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or load_engine_config()
        self._tenants_cache: Dict[str, TenantProfile] = {}

    def get_tenant(self, tenant_id: Optional[str] = None) -> TenantProfile:
        tid = tenant_id or self.config.multi_tenancy.active_tenant
        if tid not in self._tenants_cache:
            self._tenants_cache[tid] = load_tenant_profile(tid, self.config)
        return self._tenants_cache[tid]

    def list_available_tenants(self) -> List[str]:
        tenants_dir = self.config.multi_tenancy.tenants_dir
        if not tenants_dir.exists():
            return []
        return sorted([
            d.name for d in tenants_dir.iterdir()
            if d.is_dir() and (d / "profile.yaml").exists()
        ])

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        email: str,
        phone: Optional[str] = None,
        location: str = "Remote / Anywhere",
        target_titles: Optional[List[str]] = None,
        target_locations: Optional[List[str]] = None,
        min_salary: float = 6000.0,
        currency: str = "USD",
        links: Optional[Dict[str, str]] = None,
    ) -> TenantProfile:
        """Dynamically create a new tenant profile and directory structure."""
        clean_id = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in tenant_id.strip().lower())
        tenant_dir = self.config.multi_tenancy.tenants_dir / clean_id
        sources_dir = tenant_dir / "sources"
        tenant_dir.mkdir(parents=True, exist_ok=True)
        sources_dir.mkdir(parents=True, exist_ok=True)

        profile_data = {
            "tenant_id": clean_id,
            "name": name.strip(),
            "email": email.strip(),
            "phone": phone.strip() if phone else None,
            "location_current": location.strip(),
            "links": links or {},
            "sources_of_truth": {
                "cv_markdown": str(sources_dir / "Experience.md"),
                "education_markdown": str(sources_dir / "Education.md"),
                "skills_toolbox": str(sources_dir / "Toolbox.md"),
            },
            "tracks": {
                "track_a": {
                    "name": "Target Career Track",
                    "enabled": True,
                    "target_titles": target_titles or ["Software Engineer", "Systems Architect"],
                    "target_locations": target_locations or [location.strip()],
                    "compensation": {
                        "min_monthly_net_usd": float(min_salary),
                        "currency": currency,
                        "period": "monthly",
                        "type": "net",
                    },
                    "experience_requirements": {
                        "min_total_years": 5,
                        "min_leadership_years": 0,
                        "max_team_size_managed": 0,
                    },
                    "core_competencies": [],
                    "exclusions": ["Junior Developer", "Intern"],
                }
            },
            "generation_preferences": {
                "tailored_cv_format": "markdown_and_pdf",
                "cover_letter_format": "markdown_and_pdf",
                "staging_inbox": str(self.config.engine.inbox_dir / clean_id),
                "tone": "Executive, Highly Competent, Metric-Driven, Direct",
            },
        }

        profile_file = tenant_dir / "profile.yaml"
        with open(profile_file, "w", encoding="utf-8") as f:
            yaml.dump(profile_data, f, sort_keys=False, allow_unicode=True)

        return self.get_tenant(clean_id)
