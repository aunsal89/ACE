"""Unit tests for Dynamic OpenRouter Free-Tier Router & Resilient Execution Engine."""

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from pydantic import BaseModel, Field
import httpx

from src.scoring.openrouter_router import (
    OpenRouterError,
    OpenRouterExhaustionError,
    OpenRouterManager,
    OpenRouterModelCache,
    OpenRouterModelInfo,
    OpenRouterSchemaError,
    clean_and_repair_json,
    compute_model_heuristic_score,
)


class JobScoreTestSchema(BaseModel):
    score: int
    reasoning: str
    matched_skills: list[str] = Field(default_factory=list)
    compensation_match: bool = False


class TestOpenRouterRouter(unittest.TestCase):
    def setUp(self):
        self.sample_models_payload = {
            "data": [
                {
                    "id": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "name": "NVIDIA: Nemotron 3 Ultra (free)",
                    "context_length": 1000000,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "nvidia/nemotron-3-super-120b-a12b:free",
                    "name": "NVIDIA: Nemotron 3 Super (free)",
                    "context_length": 262144,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "google/gemma-4-31b-it:free",
                    "name": "Google: Gemma 4 31B (free)",
                    "context_length": 262144,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "small/tiny-model:free",
                    "name": "Tiny Model (free)",
                    "context_length": 4096,  # Should be excluded (< 8192)
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "paid/model-pro",
                    "name": "Paid Model",
                    "context_length": 128000,
                    "pricing": {"prompt": "0.001", "completion": "0.002"},  # Should be excluded (paid)
                },
                {
                    "id": "nvidia/nemotron-3.5-content-safety:free",
                    "name": "NVIDIA Content Safety (free)",
                    "context_length": 128000,
                    "pricing": {"prompt": "0", "completion": "0"},  # Should be excluded (safety filter)
                },
                {
                    "id": "openrouter/free",
                    "name": "Free Models Router",
                    "context_length": 200000,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
            ]
        }

    def test_clean_and_repair_json(self):
        # 1. Clean JSON
        raw1 = '{"score": 95, "reasoning": "Great match", "matched_skills": ["C++", "AUTOSAR"], "compensation_match": true}'
        res1 = clean_and_repair_json(raw1)
        self.assertEqual(res1["score"], 95)
        self.assertEqual(res1["compensation_match"], True)

        # 2. Markdown wrapped
        raw2 = f"Here is the evaluation:\n```json\n{raw1}\n```\nHope this helps!"
        res2 = clean_and_repair_json(raw2)
        self.assertEqual(res2["score"], 95)

        # 3. Trailing commas repair
        raw3 = '{"score": 88, "reasoning": "Good fit", "matched_skills": ["Simulink", ], "compensation_match": false, }'
        res3 = clean_and_repair_json(raw3)
        self.assertEqual(res3["score"], 88)
        self.assertEqual(res3["matched_skills"], ["Simulink"])

    def test_compute_model_heuristic_score(self):
        ultra_model = {
            "id": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "name": "NVIDIA: Nemotron 3 Ultra (free)",
            "context_length": 1000000,
        }
        gemma_model = {
            "id": "google/gemma-4-31b-it:free",
            "name": "Google: Gemma 4 31B (free)",
            "context_length": 262144,
        }
        small_model = {
            "id": "other/small-model-7b:free",
            "name": "Small 7B",
            "context_length": 8192,
        }

        score_ultra = compute_model_heuristic_score(ultra_model)
        score_gemma = compute_model_heuristic_score(gemma_model)
        score_small = compute_model_heuristic_score(small_model)

        self.assertGreater(score_ultra, score_gemma)
        self.assertGreater(score_gemma, score_small)

    def test_discover_and_rank_models(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            manager = OpenRouterManager(api_key="mock_key", cache_path=cache_file)

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = self.sample_models_payload

            with patch("httpx.Client.get", return_value=mock_resp):
                ranked = manager.discover_and_rank_models(limit=5, force_refresh=True)

                self.assertGreater(len(ranked), 0)
                # Ensure excluded models are not present
                model_ids = [m.id for m in ranked]
                self.assertNotIn("small/tiny-model:free", model_ids)
                self.assertNotIn("paid/model-pro", model_ids)
                self.assertNotIn("nvidia/nemotron-3.5-content-safety:free", model_ids)

                # Ensure top model is ultra/super
                self.assertIn("nvidia/nemotron-3-ultra-550b-a55b:free", model_ids[0])

                # Verify cache file was written
                self.assertTrue(cache_file.exists())
                self.assertTrue(manager.is_cache_valid())

    def test_cache_expiration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            manager = OpenRouterManager(api_key="mock_key", cache_path=cache_file, cache_ttl_seconds=1)

            mock_models = [
                OpenRouterModelInfo(
                    id="nvidia/nemotron-3-super-120b-a12b:free",
                    name="NVIDIA Super",
                    context_length=262144,
                    score=9.4,
                )
            ]
            manager.save_model_cache(mock_models)
            self.assertTrue(manager.is_cache_valid())

            # Simulate expiration
            time.sleep(1.2)
            self.assertFalse(manager.is_cache_valid())

    def test_execute_with_fallback_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            manager = OpenRouterManager(api_key="mock_key", cache_path=cache_file)
            manager.discover_and_rank_models = MagicMock(
                return_value=[
                    OpenRouterModelInfo(
                        id="nvidia/nemotron-3-super-120b-a12b:free",
                        name="Nemotron Super",
                        context_length=262144,
                        score=9.4,
                    )
                ]
            )

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "score": 92,
                                "reasoning": "Excellent fit for embedded leadership.",
                                "matched_skills": ["AUTOSAR", "C++", "Simulink"],
                                "compensation_match": True,
                            })
                        }
                    }
                ]
            }

            with patch("httpx.Client.post", return_value=mock_resp):
                result = manager.execute_with_fallback(
                    prompt="Evaluate job",
                    response_schema=JobScoreTestSchema,
                    max_models=1,
                )
                self.assertIsInstance(result, JobScoreTestSchema)
                self.assertEqual(result.score, 92)
                self.assertEqual(result.compensation_match, True)
                self.assertIn("AUTOSAR", result.matched_skills)

    def test_execute_with_cascading_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            manager = OpenRouterManager(api_key="mock_key", cache_path=cache_file)
            manager.discover_and_rank_models = MagicMock(
                return_value=[
                    OpenRouterModelInfo(
                        id="model-1:free",
                        name="Model 1",
                        context_length=128000,
                        score=9.0,
                    ),
                    OpenRouterModelInfo(
                        id="model-2:free",
                        name="Model 2",
                        context_length=128000,
                        score=8.5,
                    ),
                ]
            )

            # Model 1 returns 429 rate limit repeatedly, Model 2 returns 200 success
            def mock_post(url, json=None, headers=None, **kwargs):
                req_model = json.get("model")
                mock_r = MagicMock()
                if req_model == "model-1:free":
                    mock_r.status_code = 429
                    mock_r.text = '{"error": {"message": "Rate limit reached"}}'
                else:
                    mock_r.status_code = 200
                    mock_r.json.return_value = {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"score": 85, "reasoning": "Passed on fallback model", "matched_skills": ["Quant"], "compensation_match": true}'
                                }
                            }
                        ]
                    }
                return mock_r

            with patch("httpx.Client.post", side_effect=mock_post), patch("time.sleep", return_value=None):
                result = manager.execute_with_fallback(
                    prompt="Evaluate job",
                    response_schema=JobScoreTestSchema,
                    max_models=2,
                    max_retries_per_model=2,
                )
                self.assertEqual(result.score, 85)
                self.assertEqual(result.reasoning, "Passed on fallback model")

    def test_execute_exhaustion_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.json"
            manager = OpenRouterManager(api_key="mock_key", cache_path=cache_file)
            manager.discover_and_rank_models = MagicMock(
                return_value=[
                    OpenRouterModelInfo(
                        id="model-fail:free",
                        name="Fail Model",
                        context_length=128000,
                        score=9.0,
                    )
                ]
            )

            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.text = "Service Unavailable"

            with patch("httpx.Client.post", return_value=mock_resp), patch("time.sleep", return_value=None):
                with self.assertRaises(OpenRouterExhaustionError):
                    manager.execute_with_fallback(
                        prompt="Evaluate job",
                        response_schema=JobScoreTestSchema,
                        max_models=1,
                        max_retries_per_model=2,
                    )


if __name__ == "__main__":
    unittest.main()
