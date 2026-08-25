"""Configuration schema and loader for Career Engine using Pydantic V2."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import yaml
from pydantic import BaseModel, Field, field_validator

# Automatically discover and load .env files
for _candidate_env in [
    Path("/home/nsl/Portfolio/.env"),
    Path(__file__).resolve().parent.parent / ".env",
    Path.cwd() / ".env",
]:
    if _candidate_env.exists():
        load_dotenv(_candidate_env, override=False)


class EngineSettings(BaseModel):
    name: str = "Career Engine"
    version: str = "0.2.0"
    environment: str = "production"
    data_dir: Path = Field(default_factory=lambda: Path("/home/nsl/Portfolio/career-engine/data"))
    inbox_dir: Path = Field(default_factory=lambda: Path("/home/nsl/Portfolio/career-engine/inbox"))
    log_level: str = "INFO"

    @field_validator("data_dir", "inbox_dir", mode="before")
    @classmethod
    def parse_path(cls, v: Any) -> Path:
        return Path(v).expanduser().resolve() if v else Path(".")


class DatabaseSettings(BaseModel):
    db_path: Path = Field(default_factory=lambda: Path("/home/nsl/Portfolio/career-engine/data/career_engine.db"))
    wal_mode: bool = True
    timeout_seconds: float = 30.0
    foreign_keys: bool = True

    @field_validator("db_path", mode="before")
    @classmethod
    def parse_db_path(cls, v: Any) -> Path:
        return Path(v).expanduser().resolve() if v else Path("career_engine.db")


class LLMModelConfig(BaseModel):
    model: str
    temperature: float = 0.2
    max_output_tokens: int = 4096


class LLMSettings(BaseModel):
    default_provider: str = "google-genai"
    fallback_chain: List[str] = Field(default_factory=lambda: ["google-genai", "anthropic", "openai"])
    providers: Dict[str, LLMModelConfig] = Field(default_factory=dict)


class ScraperConfig(BaseModel):
    enabled: bool = True
    priority: int = 1


class SourcingSettings(BaseModel):
    request_timeout: int = 20
    max_retries: int = 3
    rate_limit_per_minute: int = 30
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 CareerEngine/0.2.0"
    scrapers: Dict[str, ScraperConfig] = Field(default_factory=dict)


class MultiTenancySettings(BaseModel):
    active_tenant: str = "aunsal"
    tenants_dir: Path = Field(default_factory=lambda: Path("/home/nsl/Portfolio/career-engine/config/tenants"))

    @field_validator("tenants_dir", mode="before")
    @classmethod
    def parse_tenants_dir(cls, v: Any) -> Path:
        return Path(v).expanduser().resolve() if v else Path("config/tenants")


class EngineConfig(BaseModel):
    engine: EngineSettings = Field(default_factory=EngineSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    sourcing: SourcingSettings = Field(default_factory=SourcingSettings)
    multi_tenancy: MultiTenancySettings = Field(default_factory=MultiTenancySettings)


# --- Tenant Profile Schemas ---

class CompensationConfig(BaseModel):
    min_monthly_net_usd: float = 8600.0
    currency: str = "USD"
    period: str = "monthly"
    type: str = "net_inflation_hedged"


class ExperienceRequirements(BaseModel):
    min_total_years: int = 15
    min_leadership_years: int = 8
    max_team_size_managed: int = 30


class TrackAProfile(BaseModel):
    name: str = "Embedded Software Leadership / Directorship"
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
    name: str = "Quantitative Developer / Algorithmic Trading"
    enabled: bool = True
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
    name: str = "EduTrace"
    url: str = "https://edutrace.net"
    repo: str = "MysApp"
    summary: str = ""
    stack: List[str] = Field(default_factory=list)


class TenantLinks(BaseModel):
    website: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    aura_showcase: Optional[str] = None
    edutrace_showcase: Optional[str] = None


class SourcesOfTruth(BaseModel):
    cv_markdown: Optional[Path] = None
    education_markdown: Optional[Path] = None
    skills_toolbox: Optional[Path] = None
    portfolio_root: Optional[Path] = None

    @field_validator("cv_markdown", "education_markdown", "skills_toolbox", "portfolio_root", mode="before")
    @classmethod
    def parse_path_opt(cls, v: Any) -> Optional[Path]:
        return Path(v).expanduser().resolve() if v else None


class GenerationPreferences(BaseModel):
    tailored_cv_format: str = "markdown_and_pdf"
    cover_letter_format: str = "markdown_and_pdf"
    staging_inbox: Path = Field(default_factory=lambda: Path("/home/nsl/Portfolio/career-engine/inbox"))
    tone: str = "Executive, Highly Competent, Metric-Driven, Direct"

    @field_validator("staging_inbox", mode="before")
    @classmethod
    def parse_inbox_path(cls, v: Any) -> Path:
        return Path(v).expanduser().resolve() if v else Path("inbox")


class TenantProfile(BaseModel):
    tenant_id: str
    name: str
    email: str
    phone: Optional[str] = None
    location_current: str = "Ankara, Turkey"
    links: TenantLinks = Field(default_factory=TenantLinks)
    sources_of_truth: SourcesOfTruth = Field(default_factory=SourcesOfTruth)
    tracks: TracksConfig = Field(default_factory=TracksConfig)
    product_engineering_showcase: Optional[ProductEngineeringShowcase] = None
    generation_preferences: GenerationPreferences = Field(default_factory=GenerationPreferences)


def load_engine_config(config_path: Optional[str | Path] = None) -> EngineConfig:
    """Load and validate the engine configuration from YAML."""
    if config_path is None:
        config_path = Path("/home/nsl/Portfolio/career-engine/config/config.yaml")
    else:
        config_path = Path(config_path).expanduser().resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Engine configuration not found at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    return EngineConfig.model_validate(raw_data)


def load_tenant_profile(tenant_id: Optional[str] = None, config: Optional[EngineConfig] = None) -> TenantProfile:
    """Load and validate a tenant profile from YAML."""
    if config is None:
        config = load_engine_config()

    target_tenant_id = tenant_id or config.multi_tenancy.active_tenant
    tenant_file = config.multi_tenancy.tenants_dir / target_tenant_id / "profile.yaml"

    if not tenant_file.exists():
        raise FileNotFoundError(f"Tenant profile not found for '{target_tenant_id}' at {tenant_file}")

    with open(tenant_file, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    return TenantProfile.model_validate(raw_data)


class TenantManager:
    """Manages multiple tenant profiles for multi-tenant execution."""

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
        return [
            d.name for d in tenants_dir.iterdir()
            if d.is_dir() and (d / "profile.yaml").exists()
        ]
