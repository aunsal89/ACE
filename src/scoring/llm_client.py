"""Multi-provider LLM Client with Fallback Chains and Deterministic Fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
import requests

from pydantic import BaseModel, Field, model_validator

from src.config import LLMSettings, TenantProfile, load_tenant_profile, load_engine_config
from src.database.models import JobListing, RecommendationType, TrackType
from src.scoring.openrouter_router import OpenRouterManager, clean_and_repair_json
from src.utils.logger import logger


class OpportunityEvaluationSchema(BaseModel):
    """Schema for LLM opportunity scoring."""
    track: Optional[str] = "GENERAL"
    overall_score: float = 70.0
    comp_score: float = 0.0
    location_score: float = 0.0
    tech_stack_score: float = 0.0
    leadership_score: float = 0.0
    fits_criteria: bool = False
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    reasoning: str = ""
    recommendation: str = "MANUAL_REVIEW"

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_dict(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. Normalize track
        data["track"] = str(data.get("track") or "GENERAL")

        # 2. Normalize overall_score
        score_val = (
            data.get("overall_score")
            if data.get("overall_score") is not None
            else data.get("score")
            if data.get("score") is not None
            else data.get("fit_score")
            if data.get("fit_score") is not None
            else data.get("total_score")
            if data.get("total_score") is not None
            else data.get("match_score")
        )
        if score_val is not None:
            try:
                data["overall_score"] = float(score_val)
            except (ValueError, TypeError):
                data["overall_score"] = 70.0
        else:
            sub_scores = [float(data.get(k, 0)) for k in ["tech_stack_score", "leadership_score", "location_score", "comp_score"] if data.get(k)]
            data["overall_score"] = sum(sub_scores) / len(sub_scores) if sub_scores else 70.0

        # Clamp overall_score to 0-100
        data["overall_score"] = max(0.0, min(100.0, float(data["overall_score"])))

        # 3. Normalize recommendation
        raw_rec = str(data.get("recommendation") or "").upper()
        if any(q in raw_rec for q in ["QUEUE", "ACCEPT", "APPLY", "APPROVE", "RECOMMEND"]):
            data["recommendation"] = "QUEUE"
        elif any(r in raw_rec for r in ["REJECT", "DECLINE", "PASS", "NO"]):
            data["recommendation"] = "REJECT"
        else:
            data["recommendation"] = "MANUAL_REVIEW"

        # 4. Normalize fits_criteria
        raw_fits = data.get("fits_criteria")
        if isinstance(raw_fits, str):
            data["fits_criteria"] = raw_fits.strip().lower() in ["true", "yes", "1", "t", "y"]
        elif raw_fits is None:
            data["fits_criteria"] = data["overall_score"] >= 75.0 and data["recommendation"] != "REJECT"

        # 5. Normalize lists
        for list_field in ["matched_keywords", "missing_keywords"]:
            val = data.get(list_field)
            if isinstance(val, str):
                data[list_field] = [s.strip() for s in val.split(",") if s.strip()]
            elif not isinstance(val, list):
                data[list_field] = []

        # 6. Normalize sub-scores
        for sub in ["comp_score", "location_score", "tech_stack_score", "leadership_score"]:
            val = data.get(sub)
            if val is not None:
                try:
                    data[sub] = max(0.0, min(100.0, float(val)))
                except (ValueError, TypeError):
                    data[sub] = 0.0

        return data


class LLMScoringClient:
    """
    Multi-provider LLM client with Google Gemini, dynamic OpenRouter free-tier cascade,
    Anthropic, OpenAI, and deterministic rule-based evaluation.
    """

    def __init__(self, settings: Optional[LLMSettings] = None, tenant: Optional[TenantProfile] = None):
        if settings is None:
            eng_cfg = load_engine_config()
            self.settings = eng_cfg.llm
        else:
            self.settings = settings

        if tenant is None:
            try:
                self.tenant = load_tenant_profile()
            except Exception:
                # Placeholder tenant if none initialized yet
                from src.config import TenantProfile
                self.tenant = TenantProfile(tenant_id="default", name="Candidate", email="candidate@example.com")
        else:
            self.tenant = tenant

        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openrouter_manager = OpenRouterManager()

    def call_raw_prompt(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Execute a raw text generation prompt using available LLM providers in fallback chain."""
        # 1. Try Gemini
        if self.gemini_key:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=self.gemini_key)
                model_name = self.settings.providers.get("google-genai", {}).model or "gemini-2.5-flash"
                contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
                cfg = types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )
                res = client.models.generate_content(model=model_name, contents=contents, config=cfg)
                if res and res.text:
                    return res.text
            except Exception as e:
                logger.warning(f"Gemini raw prompt failed: {e}")

        # 2. Try OpenRouter
        if self.openrouter_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "google/gemma-4-31b-it:free",
                    "messages": [
                        {"role": "system", "content": system_prompt or "You are a helpful AI assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2
                }
                resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"OpenRouter raw prompt failed: {e}")

        return None

    def check_location_fit(self, job_location: Optional[str], is_remote: bool) -> tuple[bool, float]:
        """
        Deterministic verification of candidate location preferences.
        Returns (is_match: bool, score: float).
        Supports universal wildcards ('Global', 'Worldwide', 'Anywhere', 'All') to accept all locations.
        """
        p = self.tenant.preferences
        target_locs = p.target_locations or []
        if not target_locs:
            return True, 100.0

        # Universal global wildcard: candidate is open to all locations worldwide (onsite, hybrid, remote)
        is_global_candidate = any(
            loc.lower().strip() in ["global", "worldwide", "anywhere", "all", "remote / anywhere", "any"]
            for loc in target_locs
        )
        if is_global_candidate:
            return True, 100.0

        user_accepts_remote = any(
            "remote" in loc.lower() or "anywhere" in loc.lower() or "global" in loc.lower()
            for loc in target_locs
        )

        if is_remote and user_accepts_remote:
            return True, 100.0

        if not job_location or not job_location.strip():
            return (True, 70.0) if user_accepts_remote else (False, 30.0)

        job_loc_lower = job_location.lower()

        # Direct token / substring / city / country matching
        for target in target_locs:
            t_lower = target.lower().strip()
            if t_lower in ["remote"]:
                continue
            parts = [part.strip() for part in t_lower.replace("/", ",").split(",") if part.strip()]
            for part in parts:
                if part in job_loc_lower or job_loc_lower in part:
                    return True, 100.0

        # If job is remote but candidate didn't explicitly include Remote
        if is_remote:
            return False, 50.0

        return False, 15.0

    def evaluate_fit(self, job: JobListing) -> OpportunityEvaluationSchema:
        """
        Evaluate candidate fit for a job listing against tenant profile.
        Executes configured fallback chain with deterministic rule fallback and programmatic guardrails.
        """
        eval_schema: Optional[OpportunityEvaluationSchema] = None

        for provider in self.settings.fallback_chain:
            try:
                if provider == "google-genai" and self.gemini_key:
                    res = self._evaluate_with_gemini(job)
                    if res:
                        eval_schema = OpportunityEvaluationSchema.model_validate(res)
                        break

                elif provider == "openrouter" and self.openrouter_key:
                    res = self._evaluate_with_openrouter_dynamic(job)
                    if res:
                        eval_schema = OpportunityEvaluationSchema.model_validate(res)
                        break

                elif provider == "anthropic" and self.anthropic_key:
                    res = self._evaluate_with_anthropic(job)
                    if res:
                        eval_schema = OpportunityEvaluationSchema.model_validate(res)
                        break

                elif provider == "openai" and self.openai_key:
                    res = self._evaluate_with_openai(job)
                    if res:
                        eval_schema = OpportunityEvaluationSchema.model_validate(res)
                        break

            except Exception as e:
                logger.warning(f"Scoring provider '{provider}' failed for job {job.id[:8]}: {e}. Falling back to next...")

        if eval_schema is None:
            logger.info(f"Using deterministic rule-based evaluation for job {job.id[:8]}")
            res = self._evaluate_deterministic(job)
            eval_schema = OpportunityEvaluationSchema.model_validate(res)

        # Programmatic Guardrail: Enforce Location Compliance
        loc_match, calc_loc_score = self.check_location_fit(job.location, job.is_remote)
        if not loc_match:
            eval_schema.location_score = min(eval_schema.location_score, calc_loc_score)
            eval_schema.fits_criteria = False
            if eval_schema.overall_score > 45.0:
                eval_schema.overall_score = round(max(15.0, eval_schema.overall_score * 0.45), 1)
            if eval_schema.recommendation == "QUEUE":
                eval_schema.recommendation = "REJECT"
            mismatch_note = f"[Location Mismatch: Job in '{job.location or 'N/A'}' does not match target locations {self.tenant.preferences.target_locations}]"
            if "location mismatch" not in eval_schema.reasoning.lower():
                eval_schema.reasoning = f"{eval_schema.reasoning} {mismatch_note}".strip()

        return eval_schema

    def _build_tenant_prompt_context(self) -> str:
        t = self.tenant
        p = t.preferences
        is_global = any(loc.lower().strip() in ["global", "worldwide", "anywhere", "all", "remote / anywhere", "any"] for loc in (p.target_locations or []))

        lines = [
            f"Candidate Name: {t.name}",
            f"Current Location: {t.location_current}",
            f"Target Roles/Titles: {', '.join(p.target_titles)}",
            f"Target Locations: {', '.join(p.target_locations)}",
            f"Min Compensation: ${p.compensation.min_monthly_net_usd:,.0f}/month {p.compensation.currency}",
            f"Core Competencies: {', '.join(p.core_competencies)}",
            f"Exclusions: {', '.join(p.exclusions)}",
        ]

        cv_path = t.sources_of_truth.cv_markdown
        if cv_path and cv_path.exists():
            cv_text = cv_path.read_text(encoding="utf-8", errors="replace")
            lines.append(f"\nCandidate Career History / CV:\n{cv_text[:3000]}")

        loc_rule = (
            "   Target Locations: Global / Worldwide (Candidate accepts all global locations worldwide, including onsite in any country, hybrid, and remote). Do NOT reject based on location."
            if is_global
            else f"   Target Locations: {', '.join(p.target_locations)}.\n"
                 "   If the job is NOT in one of the candidate's target locations (and NOT remote if remote is accepted), "
                 "   you MUST set location_score <= 25, set fits_criteria to false, and set recommendation to 'REJECT'."
        )

        lines.append(
            "\nCRITICAL EVALUATION RULES:\n"
            "1. ROLE & DOMAIN ALIGNMENT:\n"
            "   Assess whether the job matches the candidate's target roles and technical domain.\n"
            "2. STRICT LOCATION COMPLIANCE:\n"
            f"{loc_rule}\n"
            "3. EXCLUSIONS:\n"
            f"   If the job matches any of the candidate's exclusions ({', '.join(p.exclusions)}), set recommendation to 'REJECT'."
        )

        return "\n".join(lines)

    def _evaluate_deterministic(self, job: JobListing) -> Dict[str, Any]:
        title_desc = f"{job.title} {job.description_raw or ''}".lower()
        p = self.tenant.preferences
        matched_kws = [k for k in p.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
        exclusions_hit = [e for e in p.exclusions if e.lower() in title_desc]

        loc_match, location_score = self.check_location_fit(job.location, job.is_remote)

        # Title match evaluation
        title_match = any(t.lower() in title_desc for t in p.target_titles)
        tech_score = min(100.0, (60.0 if title_match else 40.0) + len(matched_kws) * 10.0)
        leadership_score = 90.0 if any(l in title_desc for l in ["lead", "director", "head", "manager", "chief", "principal", "architect"]) else 70.0
        comp_score = 85.0

        if exclusions_hit or not loc_match:
            fits = False
            overall = min(40.0, location_score) if not loc_match else 35.0
            rec = "REJECT"
        else:
            overall = (tech_score * 0.40) + (leadership_score * 0.30) + (location_score * 0.20) + (comp_score * 0.10)
            fits = overall >= 75.0 and location_score >= 60.0
            rec = "QUEUE" if fits else "MANUAL_REVIEW" if overall >= 60.0 else "REJECT"

        missing_kws = [k for k in p.core_competencies if k not in matched_kws][:4]

        return {
            "track": "GENERAL",
            "overall_score": round(overall, 1),
            "comp_score": comp_score,
            "location_score": location_score,
            "tech_stack_score": tech_score,
            "leadership_score": leadership_score,
            "fits_criteria": fits,
            "matched_keywords": matched_kws[:6],
            "missing_keywords": missing_kws,
            "reasoning": f"Deterministic evaluation: {len(matched_kws)} competencies matched. Location match: {loc_match}.",
            "recommendation": rec,
            "model_used": "rule_engine_deterministic"
        }

    def _evaluate_with_gemini(self, job: JobListing) -> Optional[Dict[str, Any]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.gemini_key)
        candidate_context = self._build_tenant_prompt_context()

        prompt = f"""You are an executive career evaluation AI assessing job opportunities for the following candidate.

{candidate_context}

Evaluate this opportunity:
Title: {job.title}
Company: {job.company}
Location: {job.location}
Description: {job.description_raw}

Return ONLY valid JSON matching this schema:
{{
  "overall_score": float between 0 and 100,
  "comp_score": float between 0 and 100,
  "location_score": float between 0 and 100,
  "tech_stack_score": float between 0 and 100,
  "leadership_score": float between 0 and 100,
  "fits_criteria": boolean,
  "matched_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["missing1"],
  "reasoning": "concise rationale string",
  "recommendation": "QUEUE", "REJECT", or "MANUAL_REVIEW"
}}
"""
        model_name = self.settings.providers.get("google-genai", {}).model or "gemini-2.5-flash"
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        raw_parsed = clean_and_repair_json(response.text)
        schema_obj = OpportunityEvaluationSchema.model_validate(raw_parsed)
        data = schema_obj.model_dump()
        data["model_used"] = f"google-genai/{model_name}"
        return data

    def _evaluate_with_openrouter_dynamic(self, job: JobListing) -> Dict[str, Any]:
        """Evaluate job listing using dynamic OpenRouter free-tier engine with schema validation & cascading resilience."""
        candidate_context = self._build_tenant_prompt_context()
        system_prompt = (
            f"You are an executive career evaluation AI assessing job opportunities for {self.tenant.name}.\n"
            f"{candidate_context}\n\n"
            "Evaluate strictly based on candidate preferences and career profile.\n"
            "Return ONLY a JSON object with keys: overall_score, comp_score, location_score, tech_stack_score, leadership_score, fits_criteria, matched_keywords, missing_keywords, reasoning, recommendation."
        )

        user_content = (
            f"Evaluate this job opportunity for {self.tenant.name}:\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location or 'N/A'}\n"
            f"Description: {job.description_raw or 'N/A'}\n\n"
            f"Return valid JSON adhering to schema (overall_score, comp_score, location_score, tech_stack_score, leadership_score, fits_criteria, matched_keywords, missing_keywords, reasoning, recommendation)."
        )

        eval_obj: OpportunityEvaluationSchema = self.openrouter_manager.execute_with_fallback(
            prompt=user_content,
            system_prompt=system_prompt,
            response_schema=OpportunityEvaluationSchema,
            max_models=5
        )

        data = eval_obj.model_dump()
        data["model_used"] = "openrouter/free-cascade"
        return data

    def _evaluate_with_anthropic(self, job: JobListing) -> Optional[Dict[str, Any]]:
        return None

    def _evaluate_with_openai(self, job: JobListing) -> Optional[Dict[str, Any]]:
        return None


# Alias for backward compatibility
ScoringLLMClient = LLMScoringClient


# Alias for backward compatibility
ScoringLLMClient = LLMScoringClient

