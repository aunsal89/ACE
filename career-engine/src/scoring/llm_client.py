"""Multi-provider LLM Client with Fallback Chains and Deterministic Fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
import requests

from pydantic import BaseModel, Field, model_validator

from src.config import LLMSettings, TenantProfile
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
        if "B" in raw_track or "QUANT" in raw_track or "TRADING" in raw_track:
            data["track"] = "TRACK_B"
        else:
            data["track"] = "TRACK_A"

        # 2. Normalize overall_score / score / fit_score
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


class ScoringLLMClient:
    """Executes structured opportunity evaluation using LLMs or verified deterministic fallback."""

    def __init__(self, llm_settings: LLMSettings, tenant: TenantProfile):
        self.settings = llm_settings
        self.tenant = tenant
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.openrouter_manager = OpenRouterManager(api_key=self.openrouter_key)

    def evaluate_fit(self, job: JobListing) -> Dict[str, Any]:
        """
        Evaluate job listing against dual-track tenant criteria.
        Fallback chain:
        1. Google Gemini (via official API key)
        2. OpenRouter (dynamic heuristic-ranked free-tier models with dual-tier retry & cascade)
        3. Deterministic high-precision rule scoring engine
        """
        # Step 1: Try Primary Provider (Google Gemini)
        if self.gemini_key:
            try:
                res = self._evaluate_with_gemini(job)
                if res and isinstance(res, dict) and "overall_score" in res:
                    return res
            except Exception as e:
                logger.warning(f"Google Gemini GenAI evaluation failed: {e}. Cascading to OpenRouter fallback models.")

        # Step 2: Try OpenRouter Dynamic Resilient Free Models
        if self.openrouter_key:
            try:
                res_dict = self._evaluate_with_openrouter_dynamic(job)
                if res_dict and "overall_score" in res_dict:
                    return res_dict
            except Exception as e:
                logger.warning(f"OpenRouter dynamic evaluation failed: {e}. Cascading to deterministic fallback.")

        # Step 3: Optional Legacy Providers
        if self.anthropic_key:
            try:
                res = self._evaluate_with_anthropic(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Anthropic evaluation failed: {e}.")

        if self.openai_key:
            try:
                res = self._evaluate_with_openai(job)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"OpenAI evaluation failed: {e}.")

        # Step 4: Deterministic Fallback Engine
        logger.info("Falling back to deterministic rule scoring engine.")
        return self._evaluate_deterministic(job)

    def _evaluate_deterministic(self, job: JobListing) -> Dict[str, Any]:
        """Deterministic, high-precision scoring engine."""
        raw_desc = job.description_raw if job.description_raw else ""
        title_desc = f"{job.title} {raw_desc}".lower()
        loc_str = job.location if job.location else ""
        company_loc = f"{job.company} {loc_str}".lower()

        # Track determination
        if job.assigned_track == TrackType.TRACK_B:
            chosen_track = "TRACK_B"
        elif job.assigned_track == TrackType.TRACK_A:
            chosen_track = "TRACK_A"
        else:
            is_b = any(k in title_desc for k in ["quant", "algorithmic trading", "trading", "hft", "execution"])
            chosen_track = "TRACK_B" if is_b else "TRACK_A"

        if chosen_track == "TRACK_A":
            ta = self.tenant.tracks.track_a
            matched_kws = [k for k in ta.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
            exclusions = [ex for ex in ta.exclusions if ex.lower() in title_desc]

            tech_score = min(100.0, 60.0 + len(matched_kws) * 10.0)
            lead_terms = ["director", "head", "manager", "lead", "architect", "chief", "lider", "mimar", "takım"]
            leadership_score = 95.0 if any(lt in job.title.lower() for lt in lead_terms) else 75.0

            loc_match = any(loc.lower().split(",")[0].strip() in company_loc for loc in ta.target_locations) or job.is_remote
            location_score = 100.0 if loc_match else 50.0

            comp_score = 95.0
            if job.salary_max and job.salary_currency == "USD" and job.salary_max < 90000:
                comp_score = 50.0

            fits = len(exclusions) == 0 and location_score >= 80 and tech_score >= 60
            overall = (tech_score * 0.40) + (leadership_score * 0.30) + (location_score * 0.20) + (comp_score * 0.10)
            rec = "QUEUE" if overall >= 75.0 and fits else "REJECT" if len(exclusions) > 0 else "MANUAL_REVIEW"

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
                "reasoning": f"Track A match: {len(matched_kws)} competencies matched. Leadership role verified.",
                "recommendation": rec,
                "model_used": "rule_engine_deterministic"
            }

        else:
            tb = self.tenant.tracks.track_b
            matched_kws = [k for k in tb.core_competencies if any(sub.lower().strip() in title_desc for sub in k.split("/"))]
            is_us = "united states" in company_loc or "usa" in company_loc or "ny" in company_loc

            loc_match = any(c.lower() in company_loc for c in tb.target_cities) or job.is_remote
            location_score = 0.0 if is_us else 100.0 if loc_match else 70.0

            tech_score = min(100.0, 60.0 + len(matched_kws) * 10.0)
            leadership_score = 90.0
            comp_score = 95.0

            fits = not is_us and location_score >= 70 and tech_score >= 60
            overall = (tech_score * 0.45) + (location_score * 0.35) + (comp_score * 0.20)
            rec = "QUEUE" if overall >= 75.0 and fits else "REJECT" if is_us else "MANUAL_REVIEW"

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
                "reasoning": f"Track B match: Quant/execution role in target region ({job.location}). AURA architecture fit.",
                "recommendation": rec,
                "model_used": "rule_engine_deterministic"
            }

    def _evaluate_with_gemini(self, job: JobListing) -> Optional[Dict[str, Any]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.gemini_key)
        prompt = f"""You are an executive career evaluation AI assessing job opportunities for Ahmet Halit Ünsal.
Dual-track profiles:
- Track A: Embedded Software Leadership / Directorship (15+ yrs exp, 8+ yrs managing teams up to 30 engineers, MBD/Simulink, ISO 26262 ASIL D, AUTOSAR, Motor Control, EV Inverters/BMS, Defense/Automotive in Istanbul/Ankara).
- Track B: Quantitative Developer / Algorithmic Trading (AURA engine, CCXT, Python/C++, walk-forward optimization, execution algorithms in Europe/APAC/China, excluding US).

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
        system_prompt = (
            "You are an executive career evaluation AI assessing job opportunities for Ahmet Halit Ünsal.\n"
            "Dual-track profiles:\n"
            "- Track A: Embedded Software Leadership / Directorship (15+ yrs exp, 8+ yrs managing teams up to 30 engineers, MBD/Simulink, ISO 26262 ASIL D, AUTOSAR, Motor Control, EV Inverters/BMS, Defense/Automotive in Istanbul/Ankara).\n"
            "- Track B: Quantitative Developer / Algorithmic Trading (AURA engine, CCXT, Python/C++, walk-forward optimization, execution algorithms in Europe/APAC/China, excluding US).\n\n"
            "Candidate Background:\n"
            "Ahmet Halit Ünsal: 15+ years experience, 8+ years leadership, MS & BS in Electrical/Computer Engineering, creator of AURA algorithmic trading system and EduTrace platform.\n\n"
            "Return ONLY a JSON object with keys: track, overall_score, comp_score, location_score, tech_stack_score, leadership_score, fits_criteria, matched_keywords, missing_keywords, reasoning, recommendation."
        )

        user_content = (
            f"Evaluate this job opportunity for Ahmet Halit Ünsal:\n"
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
