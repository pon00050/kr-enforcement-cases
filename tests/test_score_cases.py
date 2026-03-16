"""Unit tests for score_cases.py — pure functions, no I/O."""

import pytest

from kr_enforcement_cases.score_cases import (
    compute_score,
    score_beneish,
    score_kifrs,
    score_recency,
    score_structured,
)


# ─── score_beneish ─────────────────────────────────────────────────────────────

class TestScoreBeneish:
    def test_5_pts_매출(self):
        assert score_beneish("매출 과대계상") == 5

    def test_5_pts_수익인식(self):
        assert score_beneish("수익인식 기준 오류") == 5

    def test_5_pts_매출원가(self):
        assert score_beneish("매출원가 과소계상") == 5

    def test_4_pts_대손충당금(self):
        # 매출채권 contains 매출 (5pts) — use 대손충당금 which has no 5-pt overlap
        assert score_beneish("대손충당금 과소계상") == 4

    def test_4_pts_재고자산(self):
        assert score_beneish("재고자산 평가") == 4

    def test_4_pts_가공(self):
        assert score_beneish("가공 거래") == 4

    def test_3_pts_개발비(self):
        assert score_beneish("개발비 과대계상") == 3

    def test_3_pts_유형자산(self):
        assert score_beneish("유형자산 손상차손 미인식") == 3

    def test_2_pts_충당부채(self):
        assert score_beneish("충당부채 미설정") == 2

    def test_2_pts_부채(self):
        assert score_beneish("부채 관련 오류") == 2

    def test_1_pt_금융자산(self):
        assert score_beneish("금융자산 분류") == 1

    def test_0_pts_파생상품(self):
        assert score_beneish("파생상품 평가") == 0

    def test_0_pts_리스(self):
        assert score_beneish("리스 회계처리") == 0

    def test_0_pts_unknown(self):
        assert score_beneish("알수없는분야") == 0

    def test_highest_tier_wins(self):
        # 매출 (5pts) appears together with 부채 (2pts) — should return 5
        assert score_beneish("매출 및 부채 관련") == 5


# ─── score_kifrs ───────────────────────────────────────────────────────────────

class TestScoreKifrs:
    def test_2pts_1115(self):
        assert score_kifrs("기업회계기준서 제1115호") == 2

    def test_2pts_1002(self):
        assert score_kifrs("기업회계기준서 제1002호") == 2

    def test_2pts_1018(self):
        assert score_kifrs("기업회계기준서 제1018호") == 2

    def test_2pts_1011(self):
        assert score_kifrs("기업회계기준서 제1011호") == 2

    def test_1pt_1036(self):
        assert score_kifrs("기업회계기준서 제1036호") == 1

    def test_1pt_1038(self):
        assert score_kifrs("기업회계기준서 제1038호") == 1

    def test_0pts_1109(self):
        assert score_kifrs("기업회계기준서 제1109호") == 0

    def test_0pts_empty(self):
        assert score_kifrs("") == 0

    def test_higher_bonus_wins(self):
        # Both 1115 (+2) and 1036 (+1) present — should return 2
        assert score_kifrs("K-IFRS 제1115호 및 제1036호") == 2


# ─── score_recency ─────────────────────────────────────────────────────────────

class TestScoreRecency:
    def test_2pts_2025(self):
        assert score_recency("2025") == 2

    def test_2pts_2022(self):
        assert score_recency("2022") == 2

    def test_1pt_2021(self):
        assert score_recency("2021") == 1

    def test_1pt_2018(self):
        assert score_recency("2018") == 1

    def test_0pts_2017(self):
        assert score_recency("2017") == 0

    def test_0pts_empty(self):
        assert score_recency("") == 0

    def test_0pts_invalid(self):
        assert score_recency("N/A") == 0


# ─── score_structured ─────────────────────────────────────────────────────────

class TestScoreStructured:
    def test_1pt_with_number(self):
        assert score_structured("FSS/2512-10") == 1

    def test_0pts_empty(self):
        assert score_structured("") == 0

    def test_0pts_whitespace(self):
        assert score_structured("   ") == 0


# ─── compute_score (integration) ──────────────────────────────────────────────

class TestComputeScore:
    def test_tier1_high_relevance_recent(self):
        score, tier = compute_score(
            쟁점_분야="매출 과대계상",
            관련_기준서="기업회계기준서 제1115호",
            결정년도="2024",
            공개번호="FSS/2409-01",
        )
        assert score == 5 + 2 + 2 + 1  # = 10
        assert tier == 1

    def test_tier2_moderate(self):
        score, tier = compute_score(
            쟁점_분야="충당부채 미설정",
            관련_기준서="기업회계기준서 제1037호",
            결정년도="2020",
            공개번호="FSS/2001-05",
        )
        # 2 (beneish) + 0 (kifrs) + 1 (recency) + 1 (structured) = 4
        assert score == 4
        assert tier == 2

    def test_tier3_low_relevance(self):
        score, tier = compute_score(
            쟁점_분야="파생상품 평가",
            관련_기준서="기업회계기준서 제1109호",
            결정년도="2015",
            공개번호="FSS/1501-01",
        )
        # 0 + 0 + 0 + 1 = 1
        assert score == 1
        assert tier == 3

    def test_tier_boundary_7_is_tier1(self):
        score, tier = compute_score(
            쟁점_분야="개발비 과대계상",   # 3
            관련_기준서="기업회계기준서 제1038호",  # 1
            결정년도="2023",               # 2
            공개번호="FSS/2301-01",        # 1
        )
        assert score == 7
        assert tier == 1

    def test_tier_boundary_6_is_tier2(self):
        score, tier = compute_score(
            쟁점_분야="개발비 과대계상",   # 3
            관련_기준서="기업회계기준서 제1038호",  # 1
            결정년도="2020",               # 1
            공개번호="FSS/2001-01",        # 1
        )
        assert score == 6
        assert tier == 2

    def test_tier_boundary_3_is_tier3(self):
        score, tier = compute_score(
            쟁점_분야="파생상품",   # 0
            관련_기준서="기업회계기준서 제1109호",  # 0
            결정년도="2022",               # 2
            공개번호="FSS/2201-01",        # 1
        )
        assert score == 3
        assert tier == 3
