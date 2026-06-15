import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from schemas import RetrofitCalculationRequest
from services.incentive_index import IncentiveIndex
from services.llm_summary import build_summary_prompt, summarize_retrofit_calculation
from services.retrofit_calculator import calculate_retrofit_options


def _mock_payload():
    return json.loads((BACKEND_ROOT / "data" / "mock_retrofit_calculation_request.json").read_text())


class LlmSummaryTests(unittest.TestCase):
    def test_fallback_summary_without_api_key(self):
        request = RetrofitCalculationRequest(**_mock_payload())
        calculation = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            response = summarize_retrofit_calculation(calculation)

        self.assertEqual(response.summary_source, "fallback")
        self.assertIn("deterministic engine", response.llm_summary)
        self.assertEqual(response.calculation.address, calculation.address)

    def test_prompt_includes_ranked_facts_and_citations(self):
        request = RetrofitCalculationRequest(**_mock_payload())
        calculation = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        prompt = build_summary_prompt(calculation)

        self.assertIn("deterministic engine is the source of truth", prompt)
        self.assertIn("ranked_options", prompt)
        self.assertIn("citations", prompt)

    def test_summary_endpoint_returns_calculation_and_summary(self):
        client = TestClient(app)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            response = client.post("/summarize-retrofit/", json=_mock_payload())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary_source"], "fallback")
        self.assertIn("calculation", payload)
        self.assertIn("llm_summary", payload)
        self.assertGreaterEqual(len(payload["calculation"]["ranked_options"]), 1)


if __name__ == "__main__":
    unittest.main()
