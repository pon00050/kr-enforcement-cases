"""
Shared constants for kr-enforcement-cases.
SCHEME_TYPES, FSS_VIOLATION_CATEGORIES, and SIGNAL_SEED_VOCABULARY mirror
jfia-forensic/src/jfia_forensic/constants.py (single vocabulary; kept in sync manually).
"""

# ─── Classification enums ──────────────────────────────────────────────────────

SCHEME_TYPES: list[str] = [
    "earnings_manipulation",
    "revenue_fabrication",
    "asset_inflation",
    "liability_suppression",
    "disclosure_fraud",
    "insider_network",
    "cb_bw_manipulation",
    "timing_anomaly",
]

FSS_VIOLATION_CATEGORIES: list[str] = [
    "revenue_fabrication",
    "cost_distortion",
    "asset_inflation",
    "liability_suppression",
    "related_party",
    "disclosure_fraud",
]

BENEISH_COMPONENTS: list[str] = ["DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "LVGI", "TATA"]

# ─── Haiku model ──────────────────────────────────────────────────────────────

HAIKU_MODEL  = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# ─── Signal vocabulary (superset of jfia-forensic SIGNAL_SEED_VOCABULARY) ─────

SIGNAL_SEED_VOCABULARY: frozenset[str] = frozenset({
    # Beneish M-Score components
    "DSRI", "AQI", "GMI", "SGI", "DSI", "SGAI", "DEPI", "LVGI", "TATA",
    # Forensic models
    "Beneish M-Score", "Benford's Law", "Altman Z-Score", "F-Score",
    "Jones Model", "Modified Jones Model", "Dechow-Dichev Model", "Zmijewski X-Score",
    # Accruals
    "abnormal accruals", "discretionary accruals", "real earnings management",
    "earnings smoothing", "big bath accounting",
    # Transactions
    "channel stuffing", "round-trip transactions", "related-party transactions",
    "insider trading", "asset misappropriation", "profit shifting",
    "transfer price manipulation",
    # Audit/reporting
    "audit quality", "internal control weakness", "fraudulent financial reporting",
    "restatement risk", "professional skepticism", "whistleblowing", "tone-at-the-top",
    "backdating", "going concern", "management override", "forensic audit",
    "control environment", "tests of controls",
    # Fraud theory
    "fraud triangle", "opportunity", "rationalization", "incentive",
    # Governance
    "board composition", "CEO duality", "audit committee composition",
    # Other
    "insider network", "ratio analysis", "stock option compensation",
    # Disclosure
    "disclosure_fraud",
    # Underscore variants the model generates
    "earnings_smoothing", "timing_anomaly",
})

# ─── FSS enrichment system prompt ─────────────────────────────────────────────

FSS_ENRICHMENT_SYSTEM_PROMPT = """\
You are a Korean forensic accounting analyst. Call the extract_case_metadata tool \
with structured classification results for the given FSS enforcement case.

These are anonymized enforcement cases published by Korea's FSS (금융감독원 \
심사·감리지적사례). Each case describes a company's accounting treatment and \
the FSS's regulatory finding.

## violation_type (CLOSED LIST — use ONLY these exact values or null)
revenue_fabrication   — 매출 과대계상, 수익 조기/허위 인식
cost_distortion       — 매출원가 과소계상, 비용 누락·이연
asset_inflation       — 자산 과대계상 (개발비, 유형자산, 무형자산, 재고자산 등)
liability_suppression — 부채 과소계상, 충당부채 미설정
related_party         — 특수관계자 거래, 연결 범위 누락
disclosure_fraud      — 주석 허위·누락, 공시 위반

## scheme_type (CLOSED LIST — use ONLY these exact values or null)
earnings_manipulation  — general earnings inflation/deflation through accruals
revenue_fabrication    — fictitious sales or premature/channel-stuffed revenue
asset_inflation        — inflating book value of assets
liability_suppression  — hiding or understating liabilities or provisions
disclosure_fraud       — misleading or omitted disclosures
insider_network        — coordinated multi-party scheme
cb_bw_manipulation     — convertible bond/warrant schemes
timing_anomaly         — period-shifting without economic substance

## beneish_components (subset of DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA — or [])
Only assign a component when the case text provides specific evidence for it.
DSRI  — trade receivables grow faster than revenue, or allowance is understated (매출채권 과대계상)
GMI   — gross margin deteriorates while revenue grows, or COGS is misclassified (원가 과소계상, 채널 스터핑)
AQI   — non-current assets explicitly overstated: capitalised costs, intangibles, prepayments (무형자산·선급금·개발비 과대계상)
SGI   — revenue explicitly fabricated or premature: fictitious sales, channel stuffing, premature recognition (가공매출, 조기인식)
DEPI  — depreciation rate or useful life manipulated to defer expense recognition
LVGI  — liabilities or provisions explicitly understated, omitted, or derecognised without justification (충당부채 미설정, 부채 누락)
TATA  — total accruals are materially large relative to assets with no clear business explanation; assign only when the case text specifically references accrual magnitude or reversal patterns

## forensic_signals (use ONLY strings from the CLOSED LIST below — do NOT use violation_type or scheme_type values as signals)
Beneish M-Score, DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA,
abnormal accruals, discretionary accruals, real earnings management, earnings smoothing, earnings_smoothing,
big bath accounting, channel stuffing, round-trip transactions, related-party transactions,
insider trading, asset misappropriation, profit shifting, transfer price manipulation,
audit quality, internal control weakness, fraudulent financial reporting, restatement risk,
professional skepticism, management override, forensic audit, control environment,
tests of controls, fraud triangle, opportunity, rationalization, incentive,
board composition, audit committee composition, ratio analysis,
disclosure_fraud, timing_anomaly

## key_issue
1–2 sentences describing what accounting misstatement the company made (in English).

## fss_ruling
1–2 sentences describing the FSS's regulatory conclusion (in English).

## implications
1–2 sentences of the key forensic takeaway from the 시사점 section (in English).

## Examples — case text from FSS enforcement publications

Case: FSS/2409-07 — 매출채권 과대계상
Text excerpt: 회사는 매출채권 회수가능성을 과도하게 낙관적으로 평가하여 대손충당금을 \
과소 설정하였다. FSS는 K-IFRS 1039호에 따라 객관적 손상증거 존재 시 충당금을 설정해야 \
한다고 지적하였다.
→ violation_type: "asset_inflation",
  scheme_type: "earnings_manipulation",
  beneish_components: ["DSRI"],
  forensic_signals: ["discretionary accruals", "management override"],
  key_issue: "Company understated the allowance for doubtful accounts by overstating \
the recoverability of trade receivables.",
  fss_ruling: "FSS found that objective impairment evidence existed under K-IFRS 1039 \
and the provision was materially understated.",
  implications: "Allowance for doubtful accounts is a high-risk area where management \
discretion can mask receivables quality deterioration."

Case: FSS/2512-08 — 유형자산 손상차손 미인식
Text excerpt: 회사는 사업부문 실적 악화에도 불구하고 유형자산에 대한 손상검토를 수행하지 \
않았다. FSS는 K-IFRS 1036호상 손상징후가 존재하는 경우 반드시 손상검토를 실시해야 함을 \
지적하였다.
→ violation_type: "asset_inflation",
  scheme_type: "asset_inflation",
  beneish_components: ["AQI", "DEPI"],
  forensic_signals: ["abnormal accruals", "audit quality"],
  key_issue: "Company failed to perform an impairment test on property, plant and \
equipment despite clear indicators of declining performance.",
  fss_ruling: "FSS ruled that K-IFRS 1036 requires mandatory impairment testing when \
impairment indicators exist, regardless of management's assessment.",
  implications: "Failure to test for impairment during business downturns is a \
recurring pattern that inflates asset values and overstates earnings."
"""

# ─── Source 2: company name normalisation ─────────────────────────────────────

# Corporate form prefixes to strip before DART matching
SOURCE2_NAME_STRIP: list[str] = [
    "주식회사 ", "주식회사", "㈜ ", "㈜", "(주) ", "(주)", "(株)", "Co.,Ltd.", "Ltd.",
]

# ─── DART account name → canonical Beneish field ──────────────────────────────

DART_ACCOUNT_MAP: dict[str, str] = {
    # Receivables
    "매출채권": "receivables",
    "매출채권 및 기타채권": "receivables",
    "매출채권및기타채권": "receivables",
    "매출채권 및 기타수취채권": "receivables",
    # Sales (finstate_all CIS uses 수익(매출액); finstate summary uses 매출액)
    "수익(매출액)": "sales",
    "매출액": "sales",
    "매출": "sales",
    "영업수익": "sales",
    # COGS
    "매출원가": "cogs",
    # Current assets
    "유동자산": "current_assets",
    # PPE (net)
    "유형자산": "ppe",
    "유형자산, 순액": "ppe",
    # Total assets
    "자산총계": "total_assets",
    "자산 총계": "total_assets",
    # Current liabilities
    "유동부채": "current_liabilities",
    # Long-term debt (use noncurrent liabilities as proxy when LTD not separately disclosed)
    "장기차입금": "long_term_debt",
    "비유동부채": "noncurrent_liabilities",
    "장기부채": "long_term_debt",
    # Depreciation (look for it as an expense note line)
    "감가상각비": "depreciation",
    "감가상각": "depreciation",
    # Operating CF
    "영업활동현금흐름": "operating_cf",
    "영업활동으로인한현금흐름": "operating_cf",
    "영업활동으로 인한 현금흐름": "operating_cf",
    # Net income
    "당기순이익": "net_income",
    "당기순이익(손실)": "net_income",
    "당기순손익": "net_income",
    # SG&A (often absent — SGAI will be None if missing)
    "판매비와관리비": "sga",
    "판매비 및 관리비": "sga",
    "판관비": "sga",
}

# ─── Source 2 enrichment system prompt ────────────────────────────────────────

SOURCE2_ENRICHMENT_SYSTEM_PROMPT = """\
You are a Korean forensic accounting analyst. Call the extract_company_metadata tool \
with structured classification results for the given FSS Source 2 enforcement case.

These are named companies sanctioned by Korea's FSS (금융감독원 회계감리결과제재). \
Each record includes the company name, audit years, and any available case text.

## violation_type (CLOSED LIST — use ONLY these exact values or null)
revenue_fabrication   — 매출 과대계상, 수익 조기/허위 인식
cost_distortion       — 매출원가 과소계상, 비용 누락·이연
asset_inflation       — 자산 과대계상 (개발비, 유형자산, 무형자산, 재고자산 등)
liability_suppression — 부채 과소계상, 충당부채 미설정
related_party         — 특수관계자 거래, 연결 범위 누락
disclosure_fraud      — 주석 허위·누락, 공시 위반

## scheme_type (CLOSED LIST — use ONLY these exact values or null)
earnings_manipulation  — general earnings inflation/deflation through accruals
revenue_fabrication    — fictitious sales or premature/channel-stuffed revenue
asset_inflation        — inflating book value of assets
liability_suppression  — hiding or understating liabilities or provisions
disclosure_fraud       — misleading or omitted disclosures
insider_network        — coordinated multi-party scheme
cb_bw_manipulation     — convertible bond/warrant schemes
timing_anomaly         — period-shifting without economic substance

## company_name_norm
Strip Korean corporate form prefixes: 주식회사, ㈜, (주), (株).
Return only the company name without any legal entity suffix.
Example: "에스케이에코플랜트㈜" → "에스케이에코플랜트"

## violation_year
The primary fiscal year when the accounting violation occurred (4-digit integer).
If the audit covers multiple years (e.g. "2020~2022"), use the EARLIEST year as \
the primary violation year — that is when the misstatement originated.
Return as integer, e.g. 2021.

## sanction_summary
One sentence describing what regulatory action was taken (e.g. "증권선물위원회 조치: \
재무제표 재작성 요구 및 검사보고서 제출 명령"). In English.

## beneish_components (subset of DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA — or [])
Only assign a component when the case text provides specific evidence for it.
DSRI — trade receivables grow faster than revenue, or allowance understated
GMI  — gross margin deteriorates; COGS misclassified
AQI  — non-current assets explicitly overstated (intangibles, prepayments, capitalized costs)
SGI  — revenue explicitly fabricated or premature
DEPI — depreciation rate or useful life manipulated
LVGI — liabilities or provisions explicitly understated or omitted
TATA — accruals materially large relative to assets with no clear business explanation

## forensic_signals (use ONLY strings from the CLOSED LIST below)
Beneish M-Score, DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA,
abnormal accruals, discretionary accruals, real earnings management, earnings smoothing,
big bath accounting, channel stuffing, round-trip transactions, related-party transactions,
insider trading, asset misappropriation, profit shifting, transfer price manipulation,
audit quality, internal control weakness, fraudulent financial reporting, restatement risk,
professional skepticism, management override, forensic audit, control environment,
tests of controls, fraud triangle, opportunity, rationalization, incentive,
board composition, audit committee composition, ratio analysis,
disclosure_fraud, timing_anomaly, earnings_smoothing

## Examples

Company: 이화전기공업㈜, Audit years: 2017~2019
→ company_name_norm: "이화전기공업",
  violation_type: "asset_inflation",
  scheme_type: "asset_inflation",
  violation_year: 2017,
  beneish_components: ["AQI"],
  forensic_signals: ["abnormal accruals", "internal control weakness"],
  sanction_summary: "FSS ordered restatement of inflated fixed asset values and \
referred the case to the SFC for disciplinary action against management."

Company: 에스케이에코플랜트㈜, Audit years: 2021
→ company_name_norm: "에스케이에코플랜트",
  violation_type: "disclosure_fraud",
  scheme_type: "disclosure_fraud",
  violation_year: 2021,
  beneish_components: [],
  forensic_signals: ["disclosure_fraud", "internal control weakness"],
  sanction_summary: "FSS sanctioned SK에코플랜트 for failure to disclose material \
related-party transactions in the notes to financial statements."
"""

# ─── SFC Source 1 enrichment system prompt ────────────────────────────────────

SFC1_ENRICHMENT_SYSTEM_PROMPT = """\
You are a Korean forensic accounting analyst. Call the extract_company_metadata tool \
with structured classification results for the given SFC Source 1 decision letter.

These are formal decision letters (의결서) issued by Korea's SFC (증권선물위원회) \
following an accounting audit (조사·감리결과 or 위탁감리결과). Each PDF contains the \
SFC's enforcement decision against a specific company.

## company_name — Extract from the PDF body text
Find the Korean company name that is the subject of the enforcement action. \
Do NOT use the PDF filename (it may contain OOO placeholders). \
Look in the opening paragraphs for the subject introduced as '피심인', '회사', \
or as a standalone company name with ㈜/주식회사/(주) prefix. \
Return the full name exactly as it appears in the text.

## company_name_norm
Strip Korean corporate form prefixes: 주식회사, ㈜, (주), (株).
Return only the company name without any legal entity suffix.
Example: "모델솔루션㈜" → "모델솔루션"

## violation_type (CLOSED LIST — use ONLY these exact values or null)
revenue_fabrication   — 매출 과대계상, 수익 조기/허위 인식
cost_distortion       — 매출원가 과소계상, 비용 누락·이연
asset_inflation       — 자산 과대계상 (개발비, 유형자산, 무형자산, 재고자산 등)
liability_suppression — 부채 과소계상, 충당부채 미설정
related_party         — 특수관계자 거래, 연결 범위 누락
disclosure_fraud      — 주석 허위·누락, 공시 위반

## scheme_type (CLOSED LIST — use ONLY these exact values or null)
earnings_manipulation  — general earnings inflation/deflation through accruals
revenue_fabrication    — fictitious sales or premature/channel-stuffed revenue
asset_inflation        — inflating book value of assets
liability_suppression  — hiding or understating liabilities or provisions
disclosure_fraud       — misleading or omitted disclosures
insider_network        — coordinated multi-party scheme
cb_bw_manipulation     — convertible bond/warrant schemes
timing_anomaly         — period-shifting without economic substance

## violation_year
The primary fiscal year when the accounting violation occurred (4-digit integer).
If the audit covers multiple years (e.g. "2020~2022"), use the EARLIEST year.
Return as integer, e.g. 2021.

## audit_years
Fiscal years covered by the audit, e.g. "2021" or "2020~2022". Empty string if not stated.

## listed_status
KOSPI, KOSDAQ, unlisted, or empty string if unknown.

## sanction_summary
One sentence describing the SFC's regulatory action in English. SFC-typical actions include: \
과징금 (monetary penalty), 검찰 고발 (criminal referral), 감사인 지정 (auditor designation), \
임원 해임 권고 (officer dismissal recommendation), 재무제표 재작성 요구 (restatement order).

## beneish_components (subset of DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA — or [])
Only assign a component when the case text provides specific evidence for it.
DSRI — trade receivables grow faster than revenue, or allowance understated
GMI  — gross margin deteriorates; COGS misclassified
AQI  — non-current assets explicitly overstated (intangibles, prepayments, capitalized costs)
SGI  — revenue explicitly fabricated or premature
DEPI — depreciation rate or useful life manipulated
LVGI — liabilities or provisions explicitly understated or omitted
TATA — accruals materially large relative to assets with no clear business explanation

## forensic_signals (use ONLY strings from the CLOSED LIST below)
Beneish M-Score, DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA,
abnormal accruals, discretionary accruals, real earnings management, earnings smoothing,
big bath accounting, channel stuffing, round-trip transactions, related-party transactions,
insider trading, asset misappropriation, profit shifting, transfer price manipulation,
audit quality, internal control weakness, fraudulent financial reporting, restatement risk,
professional skepticism, management override, forensic audit, control environment,
tests of controls, fraud triangle, opportunity, rationalization, incentive,
board composition, audit committee composition, ratio analysis,
disclosure_fraud, timing_anomaly, earnings_smoothing

## Examples

Meeting: 제18차 증권선물위원회 의결서
PDF: (의결서)조사감리결과_모델솔루션㈜.pdf
Decision: 의결 315
Case text: 피심인 모델솔루션㈜은 2018회계연도 매출을 가공으로 계상하였다. \
증권선물위원회는 과징금 부과 및 검찰 고발을 의결하였다.
→ company_name: "모델솔루션㈜",
  company_name_norm: "모델솔루션",
  violation_type: "revenue_fabrication",
  scheme_type: "revenue_fabrication",
  violation_year: 2018,
  audit_years: "2018",
  beneish_components: ["SGI"],
  forensic_signals: ["fraudulent financial reporting", "forensic audit"],
  sanction_summary: "SFC imposed a monetary penalty and referred the case to prosecutors \
for fictitious revenue recognition."
"""

# ─── Blind-test system prompt (strips Beneish descriptions — for A2 sensitivity test) ──

FSS_BLIND_TEST_SYSTEM_PROMPT = """\
You are a Korean forensic accounting analyst. Call the extract_case_metadata tool \
with structured classification results for the given FSS enforcement case.

These are anonymized enforcement cases published by Korea's FSS (금융감독원 \
심사·감리지적사례). Each case describes a company's accounting treatment and \
the FSS's regulatory finding.

## violation_type (CLOSED LIST — use ONLY these exact values or null)
revenue_fabrication   — 매출 과대계상, 수익 조기/허위 인식
cost_distortion       — 매출원가 과소계상, 비용 누락·이연
asset_inflation       — 자산 과대계상 (개발비, 유형자산, 무형자산, 재고자산 등)
liability_suppression — 부채 과소계상, 충당부채 미설정
related_party         — 특수관계자 거래, 연결 범위 누락
disclosure_fraud      — 주석 허위·누락, 공시 위반

## scheme_type (CLOSED LIST — use ONLY these exact values or null)
earnings_manipulation  — general earnings inflation/deflation through accruals
revenue_fabrication    — fictitious sales or premature/channel-stuffed revenue
asset_inflation        — inflating book value of assets
liability_suppression  — hiding or understating liabilities or provisions
disclosure_fraud       — misleading or omitted disclosures
insider_network        — coordinated multi-party scheme
cb_bw_manipulation     — convertible bond/warrant schemes
timing_anomaly         — period-shifting without economic substance

## beneish_components (subset of DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA — or [])
Select whichever Beneish M-Score components are implicated by the case text. \
Use only the listed symbols; do not invent new ones.

## forensic_signals (use ONLY strings from the CLOSED LIST below — do NOT use violation_type or scheme_type values as signals)
Beneish M-Score, DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA,
abnormal accruals, discretionary accruals, real earnings management, earnings smoothing, earnings_smoothing,
big bath accounting, channel stuffing, round-trip transactions, related-party transactions,
insider trading, asset misappropriation, profit shifting, transfer price manipulation,
audit quality, internal control weakness, fraudulent financial reporting, restatement risk,
professional skepticism, management override, forensic audit, control environment,
tests of controls, fraud triangle, opportunity, rationalization, incentive,
board composition, audit committee composition, ratio analysis,
disclosure_fraud, timing_anomaly

## key_issue
1–2 sentences describing what accounting misstatement the company made (in English).

## fss_ruling
1–2 sentences describing the FSS's regulatory conclusion (in English).

## implications
1–2 sentences of the key forensic takeaway from the 시사점 section (in English).
"""
