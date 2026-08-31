"""Repository for Job Listings, Scoring Evaluations, and Application State Transitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
from datetime import datetime

from src.database.connection import get_db, init_db
from src.database.models import (
    ApplicationHistory,
    ApplicationPackage,
    ApplicationPackageCreate,
    JobListing,
    JobListingCreate,
    JobStatus,
    PackageStatus,
    RecommendationType,
    ScoringEvaluation,
    ScoringEvaluationCreate,
    TenantDBRecord,
    TrackType,
)
from src.utils.hashing import (
    generate_deduplication_hash,
    generate_semantic_cluster_key,
    normalize_company,
    normalize_title,
)
from src.utils.logger import logger


class JobRepository:
    """Database repository handling CRUD, deduplication, state transitions, and audit logs."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = db_path
        init_db(self.db_path)

    # --- Tenant Operations ---

    def register_or_update_tenant(self, tenant_id: str, name: str, email: Optional[str], config_path: str) -> TenantDBRecord:
        """Register or update tenant record in SQLite."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tenants (id, name, email, config_path, is_active, updated_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    config_path = excluded.config_path,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, name, email, config_path, is_active, created_at, updated_at;
                """,
                (tenant_id, name, email, config_path)
            )
            row = cursor.fetchone()
            return TenantDBRecord(
                id=row["id"],
                name=row["name"],
                email=row["email"],
                config_path=row["config_path"],
                is_active=bool(row["is_active"]),
                created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"],
                updated_at=datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"],
            )

    # --- Job Listing Operations ---

    def upsert_job(self, job_in: JobListingCreate) -> Tuple[JobListing, bool]:
        """
        Upsert a job listing.
        If deduplication_hash already exists, updates metadata without overwriting active application states (QUEUED, APPLIED).
        Returns (JobListing, is_new).
        """
        job_id = str(uuid.uuid4())
        norm_title = job_in.normalized_title or normalize_title(job_in.title)
        norm_comp = job_in.normalized_company or normalize_company(job_in.company)
        cluster_key = job_in.semantic_cluster_key or generate_semantic_cluster_key(job_in.company, job_in.title)

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            # Check if job exists
            cursor.execute("SELECT * FROM job_listings WHERE deduplication_hash = ?;", (job_in.deduplication_hash,))
            existing = cursor.fetchone()

            if existing:
                # Update non-destructive fields
                cursor.execute(
                    """
                    UPDATE job_listings
                    SET url = COALESCE(?, url),
                        description_raw = COALESCE(?, description_raw),
                        description_cleaned = COALESCE(?, description_cleaned),
                        salary_raw = COALESCE(?, salary_raw),
                        salary_min = COALESCE(?, salary_min),
                        salary_max = COALESCE(?, salary_max),
                        salary_currency = COALESCE(?, salary_currency),
                        raw_metadata_json = COALESCE(?, raw_metadata_json),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE deduplication_hash = ?
                    RETURNING *;
                    """,
                    (
                        job_in.url,
                        job_in.description_raw,
                        job_in.description_cleaned,
                        job_in.salary_raw,
                        job_in.salary_min,
                        job_in.salary_max,
                        job_in.salary_currency,
                        job_in.raw_metadata_json,
                        job_in.deduplication_hash,
                    )
                )
                row = cursor.fetchone()
                return self._row_to_job(row), False

            # Insert new job
            cursor.execute(
                """
                INSERT INTO job_listings (
                    id, deduplication_hash, semantic_cluster_key, source, external_id,
                    title, normalized_title, company, normalized_company,
                    location, country, city, is_remote, employment_type, url,
                    description_raw, description_cleaned, salary_raw, salary_min,
                    salary_max, salary_currency, salary_period, assigned_track,
                    status, raw_metadata_json
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?
                )
                RETURNING *;
                """,
                (
                    job_id,
                    job_in.deduplication_hash,
                    cluster_key,
                    job_in.source,
                    job_in.external_id,
                    job_in.title,
                    norm_title,
                    job_in.company,
                    norm_comp,
                    job_in.location,
                    job_in.country,
                    job_in.city,
                    1 if job_in.is_remote else 0,
                    job_in.employment_type,
                    job_in.url,
                    job_in.description_raw,
                    job_in.description_cleaned,
                    job_in.salary_raw,
                    job_in.salary_min,
                    job_in.salary_max,
                    job_in.salary_currency,
                    job_in.salary_period,
                    job_in.assigned_track.value,
                    job_in.status.value,
                    job_in.raw_metadata_json,
                )
            )
            row = cursor.fetchone()
            return self._row_to_job(row), True

    def get_job_by_id(self, job_id: str) -> Optional[JobListing]:
        """Fetch a single job listing by UUID or prefix."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM job_listings WHERE id = ? OR id LIKE ? || '%' LIMIT 1;", (job_id, job_id))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def get_job_by_hash(self, dedup_hash: str) -> Optional[JobListing]:
        """Fetch a single job listing by deduplication hash."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM job_listings WHERE deduplication_hash = ?;", (dedup_hash,))
            row = cursor.fetchone()
            return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        track: Optional[TrackType] = None,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[JobListing]:
        """Query job listings with flexible filtering and pagination."""
        query = "SELECT * FROM job_listings WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.value)
        if track:
            query += " AND assigned_track = ?"
            params.append(track.value)
        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY discovered_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_job(r) for r in rows]

    def update_job_status(
        self,
        job_id: str,
        new_status: JobStatus,
        tenant_id: str,
        changed_by: str = "system",
        notes: Optional[str] = None
    ) -> Optional[JobListing]:
        """
        Update job status and atomically record an audit history entry.
        Supports full UUID or short prefix.
        """
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status FROM job_listings WHERE id = ? OR id LIKE ? || '%' LIMIT 1;", (job_id, job_id))
            current = cursor.fetchone()
            if not current:
                return None

            full_id = current["id"]
            from_status = current["status"]

            cursor.execute(
                """
                UPDATE job_listings
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                RETURNING *;
                """,
                (new_status.value, full_id)
            )
            updated_row = cursor.fetchone()

            # Record audit history
            cursor.execute(
                """
                INSERT INTO application_history (job_id, tenant_id, from_status, to_status, changed_by, notes)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (full_id, tenant_id, from_status, new_status.value, changed_by, notes)
            )

            return self._row_to_job(updated_row)

    # --- Scoring Evaluations ---

    def save_evaluation(self, eval_in: ScoringEvaluationCreate) -> ScoringEvaluation:
        """Save a scoring evaluation for a job listing."""
        eval_id = str(uuid.uuid4())
        matched_json = json.dumps(eval_in.matched_keywords)
        missing_json = json.dumps(eval_in.missing_keywords)

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scoring_evaluations (
                    id, job_id, tenant_id, track, overall_score, comp_score,
                    location_score, tech_stack_score, leadership_score, fits_criteria,
                    reasoning, matched_keywords_json, missing_keywords_json,
                    recommendation, model_used
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?
                )
                RETURNING *;
                """,
                (
                    eval_id,
                    eval_in.job_id,
                    eval_in.tenant_id,
                    eval_in.track,
                    eval_in.overall_score,
                    eval_in.comp_score,
                    eval_in.location_score,
                    eval_in.tech_stack_score,
                    eval_in.leadership_score,
                    1 if eval_in.fits_criteria else 0,
                    eval_in.reasoning,
                    matched_json,
                    missing_json,
                    eval_in.recommendation.value,
                    eval_in.model_used,
                )
            )
            row = cursor.fetchone()
            return self._row_to_evaluation(row)

    def get_evaluations_for_job(self, job_id: str) -> List[ScoringEvaluation]:
        """Get all evaluations logged for a specific job."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scoring_evaluations WHERE job_id = ? ORDER BY evaluated_at DESC;", (job_id,))
            rows = cursor.fetchall()
            return [self._row_to_evaluation(r) for r in rows]

    # --- Application Packages ---

    def save_application_package(self, pkg_in: ApplicationPackageCreate) -> ApplicationPackage:
        """Save or update an application package (Markdown CV, PDF, Cover letter)."""
        pkg_id = str(uuid.uuid4())
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO application_packages (
                    id, job_id, tenant_id, track, resume_md_path, resume_pdf_path,
                    cover_letter_md_path, cover_letter_pdf_path, linkedin_prompt_path,
                    status, notes
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?
                )
                RETURNING *;
                """,
                (
                    pkg_id,
                    pkg_in.job_id,
                    pkg_in.tenant_id,
                    pkg_in.track,
                    pkg_in.resume_md_path,
                    pkg_in.resume_pdf_path,
                    pkg_in.cover_letter_md_path,
                    pkg_in.cover_letter_pdf_path,
                    pkg_in.linkedin_prompt_path,
                    pkg_in.status.value,
                    pkg_in.notes,
                )
            )
            row = cursor.fetchone()
            return self._row_to_package(row)

    def get_application_packages(self, job_id: Optional[str] = None, tenant_id: Optional[str] = None) -> List[ApplicationPackage]:
        """List application packages with optional filtering."""
        query = "SELECT * FROM application_packages WHERE 1=1"
        params: List[Any] = []
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY created_at DESC;"

        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_package(r) for r in rows]

    # --- History & Statistics ---

    def get_history_for_job(self, job_id: str) -> List[ApplicationHistory]:
        """Get complete lifecycle audit history for a job listing."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM application_history WHERE job_id = ? ORDER BY changed_at ASC;", (job_id,))
            rows = cursor.fetchall()
            return [
                ApplicationHistory(
                    id=r["id"],
                    job_id=r["job_id"],
                    tenant_id=r["tenant_id"],
                    from_status=r["from_status"],
                    to_status=r["to_status"],
                    changed_by=r["changed_by"],
                    notes=r["notes"],
                    changed_at=datetime.fromisoformat(r["changed_at"]) if isinstance(r["changed_at"], str) else r["changed_at"],
                )
                for r in rows
            ]

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate system statistics across all tables."""
        with get_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM job_listings;")
            total_jobs = cursor.fetchone()["count"]

            cursor.execute("SELECT status, COUNT(*) as count FROM job_listings GROUP BY status;")
            status_counts = {r["status"]: r["count"] for r in cursor.fetchall()}

            cursor.execute("SELECT assigned_track, COUNT(*) as count FROM job_listings GROUP BY assigned_track;")
            track_counts = {r["assigned_track"]: r["count"] for r in cursor.fetchall()}

            cursor.execute("SELECT source, COUNT(*) as count FROM job_listings GROUP BY source;")
            source_counts = {r["source"]: r["count"] for r in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) as count FROM application_packages;")
            packages_count = cursor.fetchone()["count"]

            return {
                "total_jobs": total_jobs,
                "status_breakdown": status_counts,
                "track_breakdown": track_counts,
                "source_breakdown": source_counts,
                "total_packages": packages_count,
            }

    # --- Helper Serializers ---

    @staticmethod
    def _row_to_job(row: Any) -> JobListing:
        return JobListing(
            id=row["id"],
            deduplication_hash=row["deduplication_hash"],
            semantic_cluster_key=row["semantic_cluster_key"],
            source=row["source"],
            external_id=row["external_id"],
            title=row["title"],
            normalized_title=row["normalized_title"],
            company=row["company"],
            normalized_company=row["normalized_company"],
            location=row["location"],
            country=row["country"],
            city=row["city"],
            is_remote=bool(row["is_remote"]),
            employment_type=row["employment_type"],
            url=row["url"],
            description_raw=row["description_raw"],
            description_cleaned=row["description_cleaned"],
            salary_raw=row["salary_raw"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"],
            salary_period=row["salary_period"],
            assigned_track=TrackType(row["assigned_track"]),
            status=JobStatus(row["status"]),
            raw_metadata_json=row["raw_metadata_json"],
            discovered_at=datetime.fromisoformat(row["discovered_at"]) if isinstance(row["discovered_at"], str) else row["discovered_at"],
            updated_at=datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"],
        )

    @staticmethod
    def _row_to_evaluation(row: Any) -> ScoringEvaluation:
        return ScoringEvaluation(
            id=row["id"],
            job_id=row["job_id"],
            tenant_id=row["tenant_id"],
            track=row["track"],
            overall_score=row["overall_score"],
            comp_score=row["comp_score"],
            location_score=row["location_score"],
            tech_stack_score=row["tech_stack_score"],
            leadership_score=row["leadership_score"],
            fits_criteria=bool(row["fits_criteria"]),
            reasoning=row["reasoning"],
            matched_keywords_json=row["matched_keywords_json"],
            missing_keywords_json=row["missing_keywords_json"],
            recommendation=RecommendationType(row["recommendation"]),
            model_used=row["model_used"],
            evaluated_at=datetime.fromisoformat(row["evaluated_at"]) if isinstance(row["evaluated_at"], str) else row["evaluated_at"],
        )

    @staticmethod
    def _row_to_package(row: Any) -> ApplicationPackage:
        return ApplicationPackage(
            id=row["id"],
            job_id=row["job_id"],
            tenant_id=row["tenant_id"],
            track=row["track"],
            resume_md_path=row["resume_md_path"],
            resume_pdf_path=row["resume_pdf_path"],
            cover_letter_md_path=row["cover_letter_md_path"],
            cover_letter_pdf_path=row["cover_letter_pdf_path"],
            linkedin_prompt_path=row["linkedin_prompt_path"],
            status=PackageStatus(row["status"]),
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"],
            updated_at=datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"],
        )
