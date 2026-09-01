"""Pydantic data models for Database records and schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    EVALUATED = "EVALUATED"
    QUEUED = "QUEUED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


class TrackType(str, Enum):
    GENERAL = "GENERAL"
    TRACK_A = "TRACK_A"
    TRACK_B = "TRACK_B"
    UNASSIGNED = "UNASSIGNED"
    BOTH = "BOTH"


class RecommendationType(str, Enum):
    QUEUE = "QUEUE"
    REJECT = "REJECT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class PackageStatus(str, Enum):
    GENERATED = "GENERATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    ARCHIVED = "ARCHIVED"


class TenantDBRecord(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    config_path: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class JobListingCreate(BaseModel):
    deduplication_hash: str
    semantic_cluster_key: Optional[str] = None
    source: str
    external_id: Optional[str] = None
    title: str
    normalized_title: Optional[str] = None
    company: str
    normalized_company: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    is_remote: bool = False
    employment_type: Optional[str] = None
    url: Optional[str] = None
    description_raw: Optional[str] = None
    description_cleaned: Optional[str] = None
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    assigned_track: Optional[str] = "GENERAL"
    status: JobStatus = JobStatus.DISCOVERED
    raw_metadata_json: Optional[str] = None


class JobListing(JobListingCreate):
    id: str
    discovered_at: datetime
    updated_at: datetime


class ScoringEvaluationCreate(BaseModel):
    job_id: str
    tenant_id: str
    track: Optional[str] = "GENERAL"
    overall_score: float
    comp_score: Optional[float] = None
    location_score: Optional[float] = None
    tech_stack_score: Optional[float] = None
    leadership_score: Optional[float] = None
    fits_criteria: bool = False
    reasoning: Optional[str] = None
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    recommendation: RecommendationType
    model_used: Optional[str] = None


class ScoringEvaluation(BaseModel):
    id: str
    job_id: str
    tenant_id: str
    track: Optional[str] = "GENERAL"
    overall_score: float
    comp_score: Optional[float] = None
    location_score: Optional[float] = None
    tech_stack_score: Optional[float] = None
    leadership_score: Optional[float] = None
    fits_criteria: bool
    reasoning: Optional[str] = None
    matched_keywords_json: Optional[str] = None
    missing_keywords_json: Optional[str] = None
    recommendation: RecommendationType
    model_used: Optional[str] = None
    evaluated_at: datetime


class ApplicationPackageCreate(BaseModel):
    job_id: str
    tenant_id: str
    track: Optional[str] = "GENERAL"
    resume_md_path: Optional[str] = None
    resume_pdf_path: Optional[str] = None
    cover_letter_md_path: Optional[str] = None
    cover_letter_pdf_path: Optional[str] = None
    linkedin_prompt_path: Optional[str] = None
    status: PackageStatus = PackageStatus.GENERATED
    notes: Optional[str] = None


class ApplicationPackage(ApplicationPackageCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ApplicationHistoryCreate(BaseModel):
    job_id: str
    tenant_id: str
    from_status: Optional[str] = None
    to_status: str
    changed_by: str = "system"
    notes: Optional[str] = None


class ApplicationHistory(ApplicationHistoryCreate):
    id: int
    changed_at: datetime
