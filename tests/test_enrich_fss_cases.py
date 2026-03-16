"""Tests for enrich_fss_cases.py — mocked Anthropic client."""

from unittest.mock import MagicMock, patch

import pytest

from kr_enforcement_cases.enrich_fss_cases import (
    EnrichedCase,
    _build_fallback,
    _build_prompt,
    _enrich_one,
    _parse_batch_result,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_CASE_OK = {
    "공개번호": "FSS/2409-07",
    "extract_status": "ok",
    "full_text": "회사의 회계처리\n매출채권 대손충당금 과소계상\n판단 근거\nK-IFRS 1039호 적용\n시사점\n손상 징후 검토 필요",
    "sections": {
        "s1": "회사의 회계처리\n매출채권 대손충당금 과소계상",
        "s3": "판단 근거\nK-IFRS 1039호 적용",
        "s5": "시사점\n손상 징후 검토 필요",
    },
}

SAMPLE_CASE_IMAGE = {
    "공개번호": "FSS/2409-08",
    "extract_status": "image_pdf",
    "full_text": "",
    "sections": {},
}

SAMPLE_CASE_FAILED = {
    "공개번호": "FSS/2409-09",
    "extract_status": "failed",
    "full_text": "",
    "sections": {},
}


# ─── _build_fallback ──────────────────────────────────────────────────────────

class TestBuildFallback:
    def test_default_status(self):
        fb = _build_fallback("FSS/2409-01")
        assert fb.enrichment_status == "fallback"
        assert fb.violation_type is None
        assert fb.beneish_components == []

    def test_custom_status(self):
        fb = _build_fallback("FSS/2409-01", "image_pdf")
        assert fb.enrichment_status == "image_pdf"


# ─── _build_prompt ────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_uses_sections_when_available(self):
        prompt = _build_prompt(SAMPLE_CASE_OK)
        assert "FSS/2409-07" in prompt
        assert "회사의 회계처리" in prompt
        assert "시사점" in prompt

    def test_falls_back_to_full_text(self):
        case = {
            "공개번호": "FSS/TEST-01",
            "extract_status": "partial",
            "full_text": "전체 텍스트 내용",
            "sections": {},
        }
        prompt = _build_prompt(case)
        assert "전체 텍스트 내용" in prompt

    def test_includes_case_id(self):
        prompt = _build_prompt(SAMPLE_CASE_OK)
        assert "Case ID:" in prompt


# ─── _enrich_one ──────────────────────────────────────────────────────────────

class TestEnrichOne:
    def test_image_pdf_returns_fallback(self):
        client = MagicMock()
        result = _enrich_one(client, SAMPLE_CASE_IMAGE)
        assert result.enrichment_status == "image_pdf"
        client.messages.create.assert_not_called()

    def test_failed_pdf_returns_fallback(self):
        client = MagicMock()
        result = _enrich_one(client, SAMPLE_CASE_FAILED)
        assert result.enrichment_status == "not_downloaded"
        client.messages.create.assert_not_called()

    def test_successful_enrichment(self):
        mock_input = {
            "violation_type": "asset_inflation",
            "scheme_type": "earnings_manipulation",
            "beneish_components": ["DSRI", "TATA"],
            "forensic_signals": ["discretionary accruals"],
            "key_issue": "Company understated allowance for doubtful accounts.",
            "fss_ruling": "FSS found impairment evidence existed.",
            "implications": "Receivables quality is a key forensic indicator.",
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(input=mock_input)]

        client = MagicMock()
        client.messages.create.return_value = mock_response

        result = _enrich_one(client, SAMPLE_CASE_OK)

        assert result.enrichment_status == "ok"
        assert result.violation_type == "asset_inflation"
        assert result.scheme_type == "earnings_manipulation"
        assert "DSRI" in result.beneish_components
        assert result.key_issue == "Company understated allowance for doubtful accounts."

    def test_malformed_response_returns_fallback(self):
        mock_response = MagicMock()
        mock_response.content = []  # empty content → IndexError

        client = MagicMock()
        client.messages.create.return_value = mock_response

        result = _enrich_one(client, SAMPLE_CASE_OK)
        assert result.enrichment_status == "fallback"


# ─── _parse_batch_result ──────────────────────────────────────────────────────

class TestParseBatchResult:
    def test_failed_batch_item(self):
        result = MagicMock()
        result.type = "errored"
        enriched = _parse_batch_result(result, SAMPLE_CASE_OK)
        assert enriched.enrichment_status == "fallback"

    def test_succeeded_batch_item(self):
        mock_input = {
            "violation_type": "revenue_fabrication",
            "scheme_type": "revenue_fabrication",
            "beneish_components": ["SGI", "GMI"],
            "forensic_signals": ["channel stuffing"],
            "key_issue": "Fictitious revenue was recorded.",
            "fss_ruling": "FSS found no delivery had occurred.",
            "implications": "Revenue timing is a high-risk area.",
        }
        result = MagicMock()
        result.type = "succeeded"
        result.message.content = [MagicMock(input=mock_input)]

        enriched = _parse_batch_result(result, SAMPLE_CASE_OK)
        assert enriched.enrichment_status == "ok"
        assert enriched.violation_type == "revenue_fabrication"
        assert "SGI" in enriched.beneish_components


# ─── EnrichedCase model ───────────────────────────────────────────────────────

class TestEnrichedCaseModel:
    def test_serialises_to_dict(self):
        case = EnrichedCase(
            공개번호="FSS/2409-07",
            violation_type="asset_inflation",
            scheme_type="earnings_manipulation",
            beneish_components=["DSRI"],
            forensic_signals=["audit quality"],
            key_issue="Test issue.",
            fss_ruling="Test ruling.",
            implications="Test implication.",
            enrichment_status="ok",
        )
        d = case.model_dump()
        assert d["공개번호"] == "FSS/2409-07"
        assert d["beneish_components"] == ["DSRI"]
