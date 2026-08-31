-- Career Engine SQLite Database Schema
-- Multi-tenant career orchestration, deduplication, and application state tracking.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. Tenants Table
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    config_path TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Job Listings Table
CREATE TABLE IF NOT EXISTS job_listings (
    id TEXT PRIMARY KEY,
    deduplication_hash TEXT UNIQUE NOT NULL,
    semantic_cluster_key TEXT,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    normalized_title TEXT,
    company TEXT NOT NULL,
    normalized_company TEXT,
    location TEXT,
    country TEXT,
    city TEXT,
    is_remote INTEGER NOT NULL DEFAULT 0,
    employment_type TEXT,
    url TEXT,
    description_raw TEXT,
    description_cleaned TEXT,
    salary_raw TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT,
    salary_period TEXT,
    assigned_track TEXT NOT NULL DEFAULT 'UNASSIGNED',
    status TEXT NOT NULL DEFAULT 'DISCOVERED' CHECK (status IN ('DISCOVERED', 'EVALUATED', 'QUEUED', 'APPLIED', 'REJECTED')),
    discovered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_metadata_json TEXT
);

-- 3. Scoring & Evaluation Logs Table
CREATE TABLE IF NOT EXISTS scoring_evaluations (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job_listings(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    track TEXT NOT NULL,
    overall_score REAL NOT NULL,
    comp_score REAL,
    location_score REAL,
    tech_stack_score REAL,
    leadership_score REAL,
    fits_criteria INTEGER NOT NULL DEFAULT 0,
    reasoning TEXT,
    matched_keywords_json TEXT,
    missing_keywords_json TEXT,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('QUEUE', 'REJECT', 'MANUAL_REVIEW')),
    model_used TEXT,
    evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Application Packages Table (Staging for Approval Inbox)
CREATE TABLE IF NOT EXISTS application_packages (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job_listings(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    track TEXT NOT NULL,
    resume_md_path TEXT,
    resume_pdf_path TEXT,
    cover_letter_md_path TEXT,
    cover_letter_pdf_path TEXT,
    linkedin_prompt_path TEXT,
    status TEXT NOT NULL DEFAULT 'GENERATED' CHECK (status IN ('GENERATED', 'REVIEWED', 'APPROVED', 'SUBMITTED', 'ARCHIVED')),
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. Application History & State Transition Audit Table
CREATE TABLE IF NOT EXISTS application_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES job_listings(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'system',
    notes TEXT,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast lookup, deduplication, and filtering
CREATE INDEX IF NOT EXISTS idx_jobs_dedup_hash ON job_listings(deduplication_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_cluster_key ON job_listings(semantic_cluster_key);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_listings(status);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON job_listings(source);
CREATE INDEX IF NOT EXISTS idx_jobs_track ON job_listings(assigned_track);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered_at ON job_listings(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_job_tenant ON scoring_evaluations(job_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_eval_track_score ON scoring_evaluations(track, overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_packages_job_tenant ON application_packages(job_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_history_job ON application_history(job_id);
