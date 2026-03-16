"""Tests for parse_fss_pdf.py — runs against real PDF FSS2505_06.pdf if present."""

import json
from pathlib import Path

import pytest

from kr_enforcement_cases.parse_fss_pdf import (
    ExtractedCase,
    _extract_header_dates,
    _split_sections,
    extract_pdf,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "fss_enforcement"
FIXTURE_PDF = RAW_DIR / "FSS2505_06.pdf"


# ─── Unit tests (no PDF dependency) ───────────────────────────────────────────

class TestSplitSections:
    def test_all_five_sections(self):
        text = (
            "공개번호: FSS/2505-06\n"
            "회사의 회계처리\n본문 s1\n"
            "위반 지적\n본문 s2\n"
            "판단 근거\n본문 s3\n"
            "감사절차 미흡\n본문 s4\n"
            "시사점\n본문 s5\n"
        )
        sections = _split_sections(text)
        assert set(sections) == {"s1", "s2", "s3", "s4", "s5"}
        assert "본문 s1" in sections["s1"]
        assert "본문 s5" in sections["s5"]

    def test_partial_sections(self):
        text = "회사의 회계처리\n본문\n판단 근거\n판단"
        sections = _split_sections(text)
        assert "s1" in sections
        assert "s3" in sections
        assert "s2" not in sections

    def test_no_headers_returns_empty(self):
        text = "아무 섹션 헤더 없음. 단순한 텍스트."
        assert _split_sections(text) == {}

    def test_alternate_s2_header(self):
        text = "회사의 회계처리\n내용\n위반내용\n지적내용\n시사점\n결론"
        sections = _split_sections(text)
        assert "s2" in sections

    def test_alternate_s2_지적사항(self):
        text = "회사의 회계처리\n내용\n지적사항\n내용\n시사점\n결론"
        sections = _split_sections(text)
        assert "s2" in sections


class TestExtractHeaderDates:
    def test_extracts_both_dates(self):
        text = (
            "공개번호: FSS/2505-06\n"
            "결정일: 2024-09-30\n"
            "회계결산일: 2023-12-31\n"
        )
        결정일, 회계결산일 = _extract_header_dates(text)
        assert 결정일 == "2024-09-30"
        assert 회계결산일 == "2023-12-31"

    def test_missing_dates_returns_empty(self):
        text = "단순한 텍스트, 날짜 없음."
        결정일, 회계결산일 = _extract_header_dates(text)
        assert 결정일 == ""
        assert 회계결산일 == ""

    def test_slash_date_format(self):
        text = "결정일: 2024/09/30\n회계결산일: 2023/12/31"
        결정일, 회계결산일 = _extract_header_dates(text)
        assert 결정일 == "2024/09/30"
        assert 회계결산일 == "2023/12/31"


class TestExtractPdfFailsGracefully:
    def test_nonexistent_file(self):
        result = extract_pdf(Path("/nonexistent/path/fake.pdf"))
        assert result.extract_status == "failed"
        assert result.full_text == ""
        assert result.sections == {}


# ─── Integration test (requires pdfplumber + actual PDF) ──────────────────────

@pytest.mark.skipif(
    not FIXTURE_PDF.exists(),
    reason="FSS2505_06.pdf not downloaded",
)
class TestExtractRealPdf:
    def test_extract_status_not_failed(self):
        result = extract_pdf(FIXTURE_PDF)
        assert result.extract_status in ("ok", "partial", "image_pdf")

    def test_공개번호_parsed(self):
        result = extract_pdf(FIXTURE_PDF)
        assert result.공개번호 == "FSS/2505-06"

    def test_full_text_nonempty(self):
        result = extract_pdf(FIXTURE_PDF)
        if result.extract_status != "image_pdf":
            assert len(result.full_text) > 100

    def test_dataclass_serialisable(self):
        """ExtractedCase must round-trip through JSON."""
        import dataclasses
        result = extract_pdf(FIXTURE_PDF)
        data = dataclasses.asdict(result)
        json_str = json.dumps(data, ensure_ascii=False)
        restored = json.loads(json_str)
        assert restored["공개번호"] == result.공개번호
