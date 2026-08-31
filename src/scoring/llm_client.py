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
    track: str = "TRACK_A"
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
        raw_track = str(data.get("track") or data.get("assigned_track") or data.get("target_track") or "TRACK_A").upper()
        if "B" in raw_track or "SECONDARY" in raw_track or "QUANT" in raw_track:
            data["track"] = "TRACK_B"
        else:
            data["track"] = "TRACK_A"

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

    def evaluate_fit(self, job: JobListing) -> OpportunityEvaluationSchema:
        """
        Evaluate candidate fit for a job listing against tenant profile.
        Executes configured fallback chain with deterministic rule fallback.
        """
        for provider in self.settings.fallback_chain:
            try:
                if provider == "google-genai" and self.gemini_key:
                    res = self._evaluate_with_gemini(job)
                    if res:
                        return OpportunityEvaluationSchema.model_validate(res)

                elif provider == "openrouter" and self.openrouter_key:
                    res = self._evaluate_with_openrouter_dynamic(job)
                    if res:
                        return OpportunityEvaluationSchema.model_validate(res)

                elif provider == "anthropic" and self.anthropic_key:
                    res = self._evaluate_with_anthropic(job)
                    if res:
                        return OpportunityEvaluationSchema.model_validate(res)

                elif provider == "openai" and self.openai_key:
                    res = self._evaluate_with_openai(job)
                    if res:
                        return OpportunityEvaluationSchema.model_validate(res)

            except Exception as e:
                logger.warning(f"Scoring provider '{provider}' failed for job {job.id[:8]}: {e}. Falling back to next...")

        logger.info(f"Using deterministic rule-based evaluation for job {job.id[:8]}")
        res = self._evaluate_deterministic(job)
        return OpportunityEvaluationSchema.model_validate(res)

    def _build_tenant_prompt_context(self) -> str:
        """Construct candidate context string from tenant profile and sources of truth."""
        t = self.tenant
        ta = t.tracks.track_a
        tb = t.tracks.track_b

        lines = [
            f"Candidate Name: {t.name}",
            f"Current Location: {t.location_current}",
            f"Primary Target Track: {ta.name}",
            f"- Target Titles: {', '.join(ta.target_titles)}",
            f"- Target Locations: {', '.join(ta.target_locations)}",
            f"- Min Compensation: ${ta.compensation.min_monthly_net_usd:,.0f}/month {ta.compensation.currency}",
            f"- Core Competencies: {', '.join(ta.core_competencies)}",
            f"- Exclusions: {', '.join(ta.exclusions)}",
        ]

        if tb.enabled:
            lines.extend([
                f"Secondary Target Track: {tb.name}",
                f"- Target Titles: {', '.join(tb.target_titles)}",
                f"- Target Regions: {', '.join(tb.target_regions)}",
                f"- Target Cities: {', '.join(tb.target_cities)}",
                f"- Excluded Regions: {', '.join(tb.excluded_regions)}",
                f"- Core Competencies: {', '.join(tb.core_competencies)}",
            ])

        # Add snippet of CV if available
        cv_path = t.sources_of_truth.cv_markdown
        if cv_path and cv_path.exists():
            cv_text = cv_path.read_text(encoding="utf-8", errors="replace")
            lines.append(f"\nCandidate Career History / CV:\n{cv_text[:3000]}")

        return "\n".join(lines)

    def _evaluate_deterministic(self, job: JobListing) -> Dict[str, Any]:
        """Hard rule-based heuristic evaluator when API calls are unavailable."""
        title_desc = f"{job.title} {job.description_raw or ''}".lower()
        company_loc = f"{job.company} {job.location or ''}".lower()

        # Track assignment
        assign_track_b = False
        if self.tenant.tracks.track_b.enabled:
            tb_titles = [t.lower() for t in self.tenant.tracks.track_b.target_titles]
            if any(t in title_desc for t in tb_titles) or "quant" in title_desc or "trading" in title_desc:
                assign_track_b = True

        if not assign_track_b:
            ta = self.tenant.tracks.track_a
            matched_kws = [k for k in ta.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
            exclusions_hit = [e for e in ta.exclusions if e.lower() in title_desc]

            loc_match = any(loc.lower().split(",")[0] in company_loc for loc in ta.target_locations) or job.is_remote
            location_score = 100.0 if loc_match else 60.0

            tech_score = min(100.0, 50.0 + len(matched_kws) * 10.0)
            leadership_score = 90.0 if any(l in title_desc for l in ["lead", "director", "head", "manager", "chief", "principal", "architect"]) else 70.0
            comp_score = 85.0

            if exclusions_hit:
                fits = False
                overall = 30.0
                rec = "REJECT"
            else:
                overall = (tech_score * 0.40) + (leadership_score * 0.30) + (location_score * 0.20) + (comp_score * 0.10)
                fits = overall >= 75.0 and location_score >= 60.0
                rec = "QUEUE" if fits else "MANUAL_REVIEW" if overall >= 60.0 else "REJECT"

            return {
                "track": "TRACK_A",
                "overall_score": round(overall, 1),
                "comp_score": comp_score,
                "location_score": location_score,
                "tech_stack_score": tech_score,
                "leadership_score": leadership_score,
                "fits_criteria": fits,
                "matched_keywords": matched_kws[:6],
                "missing_keywords": [k for k in ta.core_competencies if k not in matched_kws][:4],
                "reasoning": f"Track A evaluation: {len(matched_kws)} competencies matched. Location fit: {loc_match}.",
                "recommendation": rec,
                "model_used": "rule_engine_deterministic"
            }

        else:
            tb = self.tenant.tracks.track_b
            matched_kws = [k for k in tb.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
            is_excluded = any(ex.lower() in company_loc for ex in tb.excluded_regions)

            loc_match = any(c.lower() in company_loc for c in tb.target_cities) or job.is_remote
            location_score = 0.0 if is_excluded else 100.0 if loc_match else 70.0

            tech_score = min(100.0, 60.0 + len(matched_kws) * 10.0)
            leadership_score = 90.0
            comp_score = 90.0

            fits = not is_excluded and location_score >= 70 and tech_score >= 60
            overall = (tech_score * 0.45) + (location_score * 0.35) + (comp_score * 0.20)
            rec = "QUEUE" if overall >= 75.0 and fits else "REJECT" if is_excluded else "MANUAL_REVIEW"

            return {
                "track": "TRACK_B",
                "overall_score": round(overall, 1),
                "comp_score": comp_score,
                "location_score": location_score,
                "tech_stack_score": tech_score,
                "leadership_score": leadership_score,
                "fits_criteria": fits,
                "matched_keywords": matched_kws[:6],
                "missing_keywords": [k for k in tb.core_competencies if k not in matched_kws][:4],
                "reasoning": f"Track B evaluation: Role in target region ({job.location}). Technical fit: {tech_score:.0f}%.",
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
  "track": "TRACK_A" or "TRACK_B",
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
            "Return ONLY a JSON object with keys: track, overall_score, comp_score, location_score, tech_stack_score, leadership_score, fits_criteria, matched_keywords, missing_keywords, reasoning, recommendation."
        )

        user_content = (
            f"Evaluate this job opportunity for {self.tenant.name}:\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Location: {job.location or 'N/A'}\n"
            f"Description: {job.description_raw or 'N/A'}\n\n"
            f"Return ONLY valid JSON matching schema:\n"
            f'{{"track": "TRACK_A", "overall_score": 90.0, "comp_score": 90.0, "location_score": 90.0, '
            f'"tech_stack_score": 90.0, "leadership_score": 90.0, "fits_criteria": true, '
            f'"matched_keywords": ["keyword1"], "missing_keywords": [], '
            f'"reasoning": "rationale", "recommendation": "QUEUE"}}'
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

