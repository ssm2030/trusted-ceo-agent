"""Versioned machine-draft seeds transcribed from the nine approved Suite designs.

The seeds intentionally preserve design authority.  They are executable catalog
contracts, not expert-approved accounting conclusions or licensed standard text.
"""

from __future__ import annotations

DESIGN_REFS = (
    "docs/superpowers/specs/2026-07-17-accounting-content-suite-index.md",
    "docs/superpowers/specs/2026-07-17-accounting-content-suite-manifest.md",
    "docs/superpowers/specs/2026-07-17-accounting-review-coverage-matrix-design.md",
    "docs/superpowers/specs/2026-07-17-accounting-account-universe-gate-design.md",
    "docs/superpowers/specs/2026-07-17-accounting-core-journal-integrity-pack-design.md",
    "docs/superpowers/specs/2026-07-17-contract-revenue-pack-design.md",
    "docs/superpowers/specs/2026-07-17-cash-flow-working-capital-pack-design.md",
    "docs/superpowers/specs/2026-07-17-project-cost-allocation-pack-design.md",
    "docs/superpowers/specs/2026-07-17-accounting-norm-procedure-seed-catalog.md",
)

COMMON_NORM_IDS = (
    "N-COMMON-ASSERTION-01",
    "N-COMMON-EVIDENCE-01",
    "N-COMMON-MATERIALITY-01",
)

COMMON_PROCEDURE_IDS = (
    "P-COMMON-01",
    "P-COMMON-02",
    "P-COMMON-03",
    "P-COMMON-04",
    "P-COMMON-05",
)

PACK_SPECS = {
    "AC": {
        "pack_id": "accounting-core",
        "cycle_id": "accounting_core",
        "source_design_ref": DESIGN_REFS[4] + "#3-issue-family",
        "economic_event_types": ["journal_posting", "period_close", "ledger_reconciliation"],
        "accounts": ["all_general_ledger_accounts", "subledger_control_accounts"],
        "population_definition": "전체 분개 헤더·라인, 시산표, 전기말 확정잔액 및 보조원장",
        "mandatory_data_roles": [
            "journal_header", "journal_line", "trial_balance", "chart_of_accounts",
            "close_calendar", "user_role", "subledger_balance",
        ],
        "optional_data_roles": ["supporting_document", "related_party_ledger"],
        "norm_card_refs": [
            *COMMON_NORM_IDS, "N-KR-1008-01", "N-KR-1008-02",
            "N-KR-1008-03", "N-AUDIT-240-01",
        ],
        "procedure_card_refs": [
            *COMMON_PROCEDURE_IDS, *[f"P-AC-{number:02d}" for number in range(1, 17)],
        ],
    },
    "RV": {
        "pack_id": "contract-revenue",
        "cycle_id": "contract_revenue",
        "source_design_ref": DESIGN_REFS[5] + "#3-issue-family",
        "economic_event_types": [
            "contract", "contract_modification", "performance", "billing", "collection",
        ],
        "accounts": [
            "revenue", "accounts_receivable", "contract_asset", "contract_liability",
            "refund_liability", "contract_cost_asset",
        ],
        "population_definition": "제안부터 계약·이행·청구·채권·수금·환불까지의 Economic Event Graph",
        "mandatory_data_roles": [
            "contract", "promise", "pricing", "fulfilment", "billing", "accounting", "cash",
        ],
        "optional_data_roles": ["side_evidence", "cost"],
        "norm_card_refs": [
            *COMMON_NORM_IDS, *[f"N-KR-1115-{number:02d}" for number in range(1, 13)],
        ],
        "procedure_card_refs": [
            *COMMON_PROCEDURE_IDS, *[f"P-RV-{number:02d}" for number in range(1, 12)],
        ],
    },
    "CF": {
        "pack_id": "cash-flow-working-capital",
        "cycle_id": "cash_flow_working_capital",
        "source_design_ref": DESIGN_REFS[6] + "#2-issue-family",
        "economic_event_types": [
            "cash_transaction", "collection", "payment", "financing", "cash_forecast",
        ],
        "accounts": [
            "cash", "restricted_cash", "accounts_receivable", "accounts_payable", "debt",
        ],
        "population_definition": "은행 원천, 현금 GL, 현금흐름표와 운전자본·차입·예측 모집단",
        "mandatory_data_roles": ["bank", "cash_gl", "cashflow", "ar", "ap", "debt"],
        "optional_data_roles": [
            "factoring", "supplier_finance", "forecast", "payroll_tax", "contract",
        ],
        "norm_card_refs": [
            *COMMON_NORM_IDS, *[f"N-KR-1007-{number:02d}" for number in range(1, 8)],
            "N-KR-1109-01", "N-LIQUIDITY-01",
        ],
        "procedure_card_refs": [
            *COMMON_PROCEDURE_IDS, *[f"P-CF-{number:02d}" for number in range(1, 14)],
        ],
    },
    "CA": {
        "pack_id": "project-cost-allocation",
        "cycle_id": "project_cost_allocation",
        "source_design_ref": DESIGN_REFS[7] + "#3-issue-family",
        "economic_event_types": [
            "resource_acquisition", "resource_usage", "cost_allocation", "project_progress",
        ],
        "accounts": [
            "project_cost", "work_in_progress", "contract_cost_asset", "expense", "provision",
        ],
        "population_definition": "원가 원천·소비활동·pool·배부·프로젝트·회계처리 Cost Event Graph",
        "mandatory_data_roles": [
            "project_master", "cost_gl", "payroll", "vendor", "cost_pool", "allocation",
            "budget", "progress", "accounting", "revenue",
        ],
        "optional_data_roles": ["timesheet", "usage"],
        "norm_card_refs": [
            *COMMON_NORM_IDS, "N-COST-01", "N-KR-1002-01", "N-KR-1115-COST-01",
            "N-KR-1038-01", "N-KR-1038-02", "N-KR-1037-01",
            "N-MGMT-ALLOC-01", "N-MGMT-ALLOC-02",
        ],
        "procedure_card_refs": [
            *COMMON_PROCEDURE_IDS, *[f"P-CA-{number:02d}" for number in range(1, 15)],
        ],
    },
}

# id, title, review lens/assertions, deterministic procedure summary, quantification output.
ISSUE_ROWS = (
    ("AC-01", "원천·원장 모집단 불완전", "완전성", "파일·기간·sequence·합계 대사", "누락 Coverage"),
    ("AC-02", "차변·대변 불균형", "정확성", "분개·기간·원장별 균형검사", "불균형 금액"),
    ("AC-03", "시산표·원장 불일치", "완전성·정확성", "account roll-up 대사", "계정별 차이"),
    ("AC-04", "기초·기말 roll-forward 오류", "정확성·기간", "전기말-당기초, 증감 재수행", "잔차"),
    ("AC-05", "보조원장·총계정원장 불일치", "완전성·실재", "AR·AP·cash·project 대사", "object별 차이"),
    ("AC-06", "중복·분할 중복 분개", "발생·정확성", "exact·near duplicate 검사", "중복 후보금액"),
    ("AC-07", "기간말·마감후·소급 분개", "기간·발생", "close timestamp 정렬", "cutoff 후보"),
    ("AC-08", "관리자·수동·승인우회 분개", "발생·통제", "권한·creator/approver·source 검사", "override 후보"),
    ("AC-09", "비정상 계정조합·방향", "분류·정확성", "account-pair·normal balance 검사", "재분류 후보"),
    ("AC-10", "역분개·취소·대체 누락", "완전성·기간", "reversal pairing", "미역분개·이중반영"),
    ("AC-11", "가수·미결·suspense 장기잔액", "분류·평가", "aging·movement 분석", "정리 필요잔액"),
    ("AC-12", "미지급·충당부채 누락", "완전성·평가", "후속지급·계약·반복비용 search", "미인식 후보"),
    ("AC-13", "회계정책·추정·전기오류 혼동", "표시·기간", "변경 전후·승인·적용기간 비교", "처리분류 후보"),
    ("AC-14", "자산화·비용화·손상 위험", "분류·평가", "account/activity/benefit 검사", "자산조정 후보"),
    ("AC-15", "관계회사·특수관계 흔적", "표시·발생", "master·bank·counterparty 연결", "전문가 Trigger"),
    ("AC-16", "경영진 편향·분개 집중", "발생·평가", "사용자·시간·계정·KPI 영향 집중도", "fraud-risk 후보"),
    ("RV-01", "계약 식별·회수가능성", "발생·권리", "계약요건·승인·회수증거", "계약 성립 경계"),
    ("RV-02", "계약 결합·변경 누락", "정확성·기간", "고객·시점·가격·변경 연결", "재평가 대상"),
    ("RV-03", "약속·수행의무 식별", "분류·정확성", "promise graph·별도효익 검사", "수행의무 후보"),
    ("RV-04", "거래가격·변동대가", "정확성·평가", "price waterfall·constraint", "가격 조정"),
    ("RV-05", "독립판매가격 배분", "배분·정확성", "SSP 근거·상대배분 재수행", "배분차이"),
    ("RV-06", "기간·시점 인식", "기간·발생", "통제이전·기간요건 검사", "인식방식 후보"),
    ("RV-07", "진행률 측정", "정확성·기간", "input/output 재수행", "누적수익 차이"),
    ("RV-08", "검수·개통·cutoff", "발생·기간", "계약-로그-검수-분개 정렬", "조기·지연수익"),
    ("RV-09", "본인·대리인 총액·순액", "분류·정확성", "통제·재고·가격·책임 검사", "gross/net 후보"),
    ("RV-10", "라이선스·접근권·사용권", "기간·분류", "권리성격·업데이트·지원 연결", "인식패턴 후보"),
    ("RV-11", "계약잔액 분류", "분류·완전성", "이행·청구·지급 순서 재수행", "AR/CA/CL 재분류"),
    ("RV-12", "유의적 금융요소", "측정·분류", "지급시점·상업적 이유·할인", "금융효과 후보"),
    ("RV-13", "환불·SLA credit·할인", "완전성·평가", "후속 credit·클레임·usage 검사", "환불부채·가격조정"),
    ("RV-14", "계약획득·이행원가", "평가·분류", "증분성·직접관련·회수성 검사", "자산화·비용화"),
    ("RV-15", "취소·side agreement", "발생·기간", "CRM·이메일·해지·후속행동 연결", "계약조건 수정"),
    ("RV-16", "채권·계약자산 손상", "평가", "aging·회수·신용정보", "ECL 검토 후보"),
    ("CF-01", "은행·GL 대사차이", "회계", "bank reconciliation", "미기록·미결 차이"),
    ("CF-02", "현금·현금성자산·제한현금 분류", "회계", "조건·만기·위험 검사", "재분류 후보"),
    ("CF-03", "영업·투자·재무 분류 오류", "회계", "transaction classification", "현금흐름표 조정"),
    ("CF-04", "비현금거래 혼입·누락", "회계", "GL-cash trace", "비현금 조정"),
    ("CF-05", "재무활동 부채 roll-forward 오류", "회계", "debt bridge", "설명되지 않은 변동"),
    ("CF-06", "공급자금융·reverse factoring", "회계·진단", "계약·지급조건·공시 검사", "분류·집중위험"),
    ("CF-07", "매출채권 회수악화", "회계·진단", "aging·cohort·subsequent cash", "ECL·현금전환"),
    ("CF-08", "매입채무 지급지연", "회계·진단", "DPO·overdue·terms", "현금보전·체납위험"),
    ("CF-09", "손익-영업현금흐름 괴리", "진단", "EBITDA/operating profit bridge", "원인기여도"),
    ("CF-10", "고객·공급자 집중", "진단", "concentration·scenario", "유동성 노출"),
    ("CF-11", "팩토링·채권양도", "회계·진단", "derecognition·recourse 검사", "차입·매각 후보"),
    ("CF-12", "covenant·차입 유동성", "회계·진단", "covenant recompute", "위반·분류 Trigger"),
    ("CF-13", "세금·급여·필수지급 체납", "회계·진단", "due-payment matching", "미지급·법적 Trigger"),
    ("CF-14", "기간말 window dressing", "통제·진단", "pre/post cash pattern", "일시적 개선 후보"),
    ("CF-15", "현금예측 편향·runway", "진단", "forecast backtest·scenario", "자금부족 시점"),
    ("CF-16", "계속기업 전조", "전문가 Trigger", "liquidity stress synthesis", "추가 평가 Packet"),
    ("CA-01", "GL-프로젝트 원가 불일치", "회계·통제", "population reconciliation", "누락·orphan 원가"),
    ("CA-02", "직접·간접원가 오분류", "회계·관리", "activity·beneficiary 검사", "재분류 후보"),
    ("CA-03", "원가 pool 비동질", "관리·통제", "pool composition", "분리 pool 후보"),
    ("CA-04", "배부기준 인과관계 부족", "관리", "driver comparison", "마진 왜곡"),
    ("CA-05", "배부율 계산 오류", "회계·관리", "rate reperformance", "배부차이"),
    ("CA-06", "중복·누락·미배부", "회계·통제", "allocation completeness", "오류금액"),
    ("CA-07", "유휴조업도·비정상 낭비", "회계·관리", "capacity·waste separation", "비용화 후보"),
    ("CA-08", "근로시간·인력 원가 귀속 오류", "회계·관리", "payroll-timesheet-project 대사", "프로젝트 이동"),
    ("CA-09", "외주·인프라·공통서비스 귀속", "회계·관리", "invoice·usage matching", "원가 재귀속"),
    ("CA-10", "WIP·진척률·예정원가 오류", "회계", "roll-forward·ETC backtest", "WIP 조정"),
    ("CA-11", "계약획득·이행원가 자산화", "회계", "eligibility·amortisation", "자산·비용 후보"),
    ("CA-12", "개발·교육·유지보수 자산화", "회계", "IAS 38/IFRS 15 scope", "자산조정 후보"),
    ("CA-13", "손실·부담계약 누락", "회계", "unavoidable cost vs benefit", "충당부채 후보"),
    ("CA-14", "변경계약·scope creep", "회계·관리", "contract-budget-actual bridge", "미청구·손실 영향"),
    ("CA-15", "프로젝트 마진 왜곡", "관리", "alternate allocation sensitivity", "정상화 마진"),
    ("CA-16", "관계회사·부서간 cross-charge", "회계·세무 Trigger", "counterparty·policy 검사", "세무·공시 Trigger"),
)

ISSUE_PROCEDURE_MAP = {
    **{f"AC-{number:02d}": f"P-AC-{number:02d}" for number in range(1, 17)},
    **{f"RV-{number:02d}": f"P-RV-{min(number, 11):02d}" for number in range(1, 17)},
    **{f"CF-{number:02d}": f"P-CF-{min(number, 13):02d}" for number in range(1, 17)},
    **{f"CA-{number:02d}": f"P-CA-{min(number, 14):02d}" for number in range(1, 17)},
}

# Explicit corrections where the design's Issue numbering and procedure numbering diverge.
ISSUE_PROCEDURE_MAP.update({
    "RV-12": "P-RV-04", "RV-13": "P-RV-09", "RV-14": "P-RV-11",
    "RV-15": "P-RV-10", "RV-16": "P-RV-09", "CF-14": "P-CF-13",
    "CF-15": "P-CF-12", "CF-16": "P-CF-11", "CA-15": "P-CA-06",
    "CA-16": "P-CA-09",
})

NORM_SEED_TITLES = {
    "N-COMMON-ASSERTION-01": "거래와 잔액",
    "N-COMMON-EVIDENCE-01": "증거 강도",
    "N-COMMON-MATERIALITY-01": "중요성",
    "N-KR-1008-01": "회계정책",
    "N-KR-1008-02": "회계추정",
    "N-KR-1008-03": "전기오류",
    "N-AUDIT-240-01": "경영진 override Method",
    "N-KR-1115-01": "고객계약 식별",
    "N-KR-1115-02": "계약 결합",
    "N-KR-1115-03": "계약 변경",
    "N-KR-1115-04": "수행의무",
    "N-KR-1115-05": "거래가격",
    "N-KR-1115-06": "독립판매가격 배분",
    "N-KR-1115-07": "기간에 걸친 충족",
    "N-KR-1115-08": "한 시점 통제이전",
    "N-KR-1115-09": "진행률",
    "N-KR-1115-10": "본인·대리인",
    "N-KR-1115-11": "계약잔액",
    "N-KR-1115-12": "계약원가",
    "N-KR-1007-01": "현금과 현금성자산",
    "N-KR-1007-02": "영업활동",
    "N-KR-1007-03": "투자활동",
    "N-KR-1007-04": "재무활동",
    "N-KR-1007-05": "비현금 거래",
    "N-KR-1007-06": "재무부채 변동",
    "N-KR-1007-07": "공급자금융",
    "N-KR-1109-01": "매출채권·계약자산 기대신용손실",
    "N-LIQUIDITY-01": "경영 유동성",
    "N-COST-01": "회계원가와 관리배부 분리",
    "N-KR-1002-01": "재고원가",
    "N-KR-1115-COST-01": "계약획득·이행원가",
    "N-KR-1038-01": "교육·인력",
    "N-KR-1038-02": "개발활동",
    "N-KR-1037-01": "부담계약",
    "N-MGMT-ALLOC-01": "배부 인과관계",
    "N-MGMT-ALLOC-02": "Pool 동질성",
}

PROCEDURE_SEED_TITLES = {
    "P-COMMON-01": "Population-first",
    "P-COMMON-02": "Hypothesis set",
    "P-COMMON-03": "Distinguishing test",
    "P-COMMON-04": "Quantification",
    "P-COMMON-05": "Stand-back",
    "P-AC-01": "Population manifest",
    "P-AC-02": "Debit-credit balance",
    "P-AC-03": "GL-TB roll-up",
    "P-AC-04": "Opening roll-forward",
    "P-AC-05": "Subledger reconciliation",
    "P-AC-06": "Duplicate detection",
    "P-AC-07": "Close and cutoff",
    "P-AC-08": "Access and approval",
    "P-AC-09": "Account pair expectation",
    "P-AC-10": "Reversal pairing",
    "P-AC-11": "Suspense aging",
    "P-AC-12": "Subsequent disbursement search",
    "P-AC-13": "Policy-estimate-error classification",
    "P-AC-14": "Capitalization screen",
    "P-AC-15": "Related-party trace",
    "P-AC-16": "Management bias stand-back",
    "P-RV-01": "Contract population reconciliation",
    "P-RV-02": "Contract term extraction",
    "P-RV-03": "Promise and obligation graph",
    "P-RV-04": "Price waterfall",
    "P-RV-05": "SSP allocation",
    "P-RV-06": "Satisfaction pattern",
    "P-RV-07": "Progress reperformance",
    "P-RV-08": "Population cutoff",
    "P-RV-09": "Contract balance roll-forward",
    "P-RV-10": "Side agreement search",
    "P-RV-11": "Contract cost",
    "P-CF-01": "Bank reconciliation",
    "P-CF-02": "Cash definition and restriction",
    "P-CF-03": "Cash flow classification",
    "P-CF-04": "Financing liability bridge",
    "P-CF-05": "Direct cash map",
    "P-CF-06": "Profit-to-cash bridge",
    "P-CF-07": "AR aging and cohort",
    "P-CF-08": "AP aging and stretch",
    "P-CF-09": "Supplier finance screen",
    "P-CF-10": "Factoring and receivable transfer",
    "P-CF-11": "Concentration stress",
    "P-CF-12": "Forecast backtest",
    "P-CF-13": "Period-end window",
    "P-CA-01": "Cost population reconciliation",
    "P-CA-02": "Directness test",
    "P-CA-03": "Pool homogeneity",
    "P-CA-04": "Allocation rate reperformance",
    "P-CA-05": "Driver causality",
    "P-CA-06": "Alternative allocation sensitivity",
    "P-CA-07": "Capacity and abnormal cost",
    "P-CA-08": "Payroll-timesheet reconciliation",
    "P-CA-09": "Vendor and usage matching",
    "P-CA-10": "WIP and progress roll-forward",
    "P-CA-11": "Estimate-to-complete backtest",
    "P-CA-12": "Contract cost asset",
    "P-CA-13": "Onerous contract",
    "P-CA-14": "Scope creep bridge",
}


def norm_source_ref(norm_id: str) -> str:
    return f"{DESIGN_REFS[8]}#{norm_id.lower()}"


def procedure_source_ref(procedure_id: str) -> str:
    if procedure_id.startswith("P-COMMON-"):
        document = DESIGN_REFS[8]
    else:
        document = PACK_SPECS[procedure_id[2:4]]["source_design_ref"].split("#", 1)[0]
    return f"{document}#{procedure_id.lower()}"
