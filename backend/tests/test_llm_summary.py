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
from services.llm_summary import (
    _clean_summary_text,
    build_summary_prompt,
    summarize_retrofit_calculation,
)
from services.retrofit_calculator import calculate_retrofit_options


def _mock_payload():
    return json.loads((BACKEND_ROOT / "data" / "mock_retrofit_calculation_request.json").read_text())


class LlmSummaryTests(unittest.TestCase):
    @patch("services.llm_summary.urlopen")
    def test_fallback_summary_without_api_key(self, mock_urlopen):
        # Simulate connection error
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")
        
        request = RetrofitCalculationRequest(**_mock_payload())
        calculation = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        response = summarize_retrofit_calculation(calculation)

        self.assertEqual(response.summary_source, "fallback")
        self.assertIn("deterministic engine", response.llm_summary)
        self.assertEqual(response.calculation.address, calculation.address)

    @patch("services.llm_summary.urlopen")
    def test_successful_local_llm_summary(self, mock_urlopen):
        import io
        
        # Simulate successful OpenAI-compatible response
        mock_response_body = json.dumps({
            "choices": [{"message": {"content": "This is a local LLM summary."}}]
        }).encode("utf-8")
        
        mock_response = io.BytesIO(mock_response_body)
        mock_urlopen.return_value.__enter__.return_value = mock_response

        request = RetrofitCalculationRequest(**_mock_payload())
        calculation = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        response = summarize_retrofit_calculation(calculation)

        self.assertEqual(response.summary_source, "local_llm")
        self.assertEqual(response.llm_summary, "This is a local LLM summary.")
        self.assertEqual(response.calculation.address, calculation.address)

    def test_prompt_includes_ranked_facts(self):
        request = RetrofitCalculationRequest(**_mock_payload())
        calculation = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        prompt = build_summary_prompt(calculation)

        self.assertIn("deterministic engine is the source of truth", prompt)
        self.assertIn("ranked_options", prompt)
        self.assertIn("60 words maximum", prompt)

    def test_summary_cleanup_removes_markdown_markers(self):
        summary = _clean_summary_text(
            "# What To Do First\n"
            "**Start with Rooftop Solar PV.** It has the best savings.\n"
            "1. **Next step:** confirm the incentive paperwork."
        )

        self.assertNotIn("#", summary)
        self.assertNotIn("**", summary)
        self.assertIn("Start with Rooftop Solar PV.", summary)
        self.assertIn("Next step: confirm the incentive paperwork.", summary)

    @patch("services.llm_summary.urlopen")
    def test_summary_endpoint_returns_calculation_and_summary(self, mock_urlopen):
        client = TestClient(app)

        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        response = client.post("/summarize-retrofit/", json=_mock_payload())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary_source"], "fallback")
        self.assertIn("calculation", payload)
        self.assertIn("llm_summary", payload)
        self.assertGreaterEqual(len(payload["calculation"]["ranked_options"]), 1)


if __name__ == "__main__":
    unittest.main()
