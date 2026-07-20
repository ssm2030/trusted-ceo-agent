# Trusted CEO Agent

Trusted CEO Agent는 회사 데이터를 근거로 경영진이 아직 인지하지 못한 문제를 찾고, 그 문제를 사람이 검토할 수 있는 `Finding`과 의사결정 자료로 구조화하는 고신뢰 진단 엔진입니다.

이 시스템은 회계사·세무사·노무사·변호사 또는 CEO의 최종 판단을 대체하지 않습니다. 결정적 계산과 증거 추적은 코드가 맡고, AI는 승인된 지식과 출력 계약 안에서 가설·반증·추가 검증안을 작성하며, 중요한 범위·승인·최종 판단은 사람에게 남깁니다.

> **현재 성숙도:** 전문 분석 런타임과 웹 투영 구조는 구현돼 있으나, 회계 전문 콘텐츠의 권한은 아직 `machine_draft`/`Boundary`입니다. “시니어 회계사급 1차 검토”는 목표 품질이며, 외부 전문가 비교평가를 통과하기 전에는 달성됐다고 표시하지 않습니다.

## 무엇을 해결하는가

일반적인 경영 분석은 이미 알려진 KPI를 요약하거나 사용자가 질문한 원인을 확인하는 데 머무르기 쉽습니다. Trusted CEO Agent는 다음 흐름으로 알려지지 않은 문제 후보를 탐색합니다.

```text
회사 원천 데이터
  → 전처리·정규화·계보 보존
  → 결정적 Fact·Signal
  → 공통 Economic Event
  → 회계·노무·법무·세무 applicability routing
  → Signal Case Queue
  → 사건별 단계적 심층 분석
  → 증거·반증이 연결된 Finding
  → 관계·충돌·Issue Cluster 통합
  → Completion 판정
  → Final Result Converter
  → 웹 탭 2 결과
```

시스템이 찾으려는 대표 문제는 다음과 같습니다.

- 회계 무결성, 분개 이상, 기간귀속과 결산 통제 문제
- 계약·매출·채권·계약부채의 불일치
- 현금흐름 분류, 운전자본, 회수·지급 및 유동성 위험
- 프로젝트 원가귀속, 간접비 배부, WIP와 손실계약 후보
- 공통 경제적 사건에서 파생되는 법무·노무·세무 검토 필요성
- CEO가 우선 확인하거나 전문가에게 전달해야 할 의사결정 쟁점

## 기술적 원리

### 네 층과 Trust Kernel

1. **Evidence Core**
   원본을 보존하고 입력 품질, Canonical Fact, 계산, Source lineage와 분석 가능 범위를 관리합니다.
2. **Pack Stack**
   Mission·Domain·Problem Pack이 적용 지식, 절차, 금지 범위와 권한을 제공합니다.
3. **Bounded AI Reasoning**
   모델은 자유형 결론이 아니라 동결된 Job과 허용된 ID·주장 유형 안에서만 초안을 작성합니다.
4. **Human Decision**
   사용자는 데이터 의미, 분석 범위, 이슈 disposition과 최종 전달을 승인·수정·기각합니다.

Trust Kernel은 네 층 전체에 원본 불변성, revision CAS, 승인 무결성, authority 상한, hash, 검증과 감사 추적을 강제합니다.

### 전문 사고법 + 규범지식 + 절차 + 반증

전문 분석은 단순 체크리스트 수를 늘리는 방식이 아닙니다. 선택된 Issue Family는 D1~D12 깊이 계약을 통해 다음을 연결해야 합니다.

- 사건과 모집단
- 계정·주장·의사결정 영향
- 정상 기대관계
- 오류 가설과 정상 대안 가설
- 적용 규범과 시행일·관할
- 가설을 구별하는 절차
- 지지 증거와 반대 증거
- 오류·노출 금액의 정량화
- 조건부 회계처리·조치 후보
- Cross-domain Trigger
- 한계와 권한
- 정답·반증·회귀 사례

따라서 추론 품질은 모델의 유창성보다 **누락을 막는 절차, 반증을 요구하는 계약, 결정적 계산, 승인된 지식과 회귀평가**로 높입니다.

### 회계 64 Issue Family

초기 B2B 서비스업 회계 Suite는 다음 네 묶음으로 구성됩니다.

| Pack | 범위 | Family |
|---|---|---:|
| Accounting Core | 원장·시산표·보조원장·분개·결산 무결성 | AC-01~AC-16 |
| Contract & Revenue | 계약·수행의무·매출·채권·계약잔액 | RV-01~RV-16 |
| Cash Flow & Working Capital | 현금·현금흐름 분류·회수·지급·유동성 | CF-01~CF-16 |
| Project Cost & Allocation | 직접·간접원가·배부·WIP·손실계약 | CA-01~CA-16 |

64개는 품질을 보장하는 숫자가 아니라 초기 Coverage seed입니다. 각 Family의 공식 규범 연결, 합성 Oracle, 회귀테스트와 전문가 승격이 품질을 결정합니다.

### 사건별 오케스트레이션

- 모든 이상신호를 한 번의 거대한 프롬프트에 넣지 않습니다.
- Signal Case를 우선순위 큐에 넣고 기본적으로 한 건씩 심층 분석합니다.
- 동일한 불변 Fact와 Knowledge Release를 사용하는 독립 계산만 제한적으로 병렬화합니다.
- Cross-domain 충돌, 전사 중요도, 최종 Grade와 CEO 문구는 Join 이후 하나의 Integrator가 결정합니다.
- WorkBudget, checkpoint, resume, retry 상한과 terminal disposition을 Artifact로 남깁니다.
- Completion Controller가 미종결 중요 Case와 필수 실패를 확인하기 전에는 Finalization을 허용하지 않습니다.

### Knowledge Foundry Dual-loop

실행 중인 분석은 승인된 불변 Knowledge Release만 사용합니다. 피드백은 즉시 학습되지 않고 별도 Knowledge Plane에서 처리됩니다.

```text
Analysis Plane
  승인된 Release로 분석 → 결과·한계·사용 Release 기록

Knowledge Plane
  Feedback Record
    → 실패 분류
    → Patch Proposal
    → 재현 사례·회귀테스트
    → 3단계 승인
    → 불변 Knowledge Release
    → 다음 Run부터 활성화 또는 rollback
```

이 구조는 한 번의 POC 보정이 아니라, 오답·누락·과잉 확신을 장기적으로 축적하고 기존 정답을 깨지 않으면서 지식을 개선하기 위한 운영 시스템입니다.

## 플러그인·웹·사람의 책임 경계

| 주체 | 책임 | 금지 |
|---|---|---|
| Plugin Control Plane | 상태, revision, 승인, Artifact, 권한, 최종 검증 | 모델 초안을 승인이나 Fact로 간주 |
| Analysis Engine | 계산, Pack 실행, 제한된 전문추론, Finding 생성 | 승인 범위 밖 결론 생성 |
| Orchestration Harness | 유한 DAG, 작업예산, 재시도·중단·재개, Join | 실패를 얕은 답변으로 대체 |
| Final Result Converter | 확정된 Finding을 웹 계약으로 결정적 매핑 | 새 Finding·Grade·관계 발명 |
| Web | 입력 안내, 진행 상태, 증거 탐색, 탭 2 표시 | 분석·승인·전문 판단 수행 |
| 사람·전문가 | 데이터 의미, 범위, 예외, 중요성, 최종 판단 | 해당 없음 |

분석에 영향을 주는 사용자 답변은 정확히 하나의 새 revision을 만들 수 있지만 승인 자체가 되지는 않습니다. 승인은 실제 TTY에서 nonce와 최신 revision을 확인하는 별도 흐름입니다.

## 현재 구현과 품질 상태

아래는 최신 성능을 영구 보증하는 표가 아니라, 저장소에 기록된 증거와 현재 권한 상한을 구분하기 위한 안내입니다.

| 영역 | 현재 상태 | 해석 |
|---|---|---|
| 전문 런타임 | Event→Route→Case→DAG→Finding→Completion 구현 | 실행 구조가 있다는 뜻이며 전문 정답률을 보장하지 않음 |
| 회계 Suite | AC/RV/CF/CA 64 Family Dispatcher와 절차 모듈 | 콘텐츠 권한은 `machine_draft`/`Boundary` |
| Trust·승인 | 불변 revision, CAS, nonce, TTY 승인, fail-closed | 테스트된 통제 구조 |
| 웹 | Finalized revision의 읽기 전용 탭 2 투영 | 웹은 새 결론을 만들지 않음 |
| Knowledge Foundry | Feedback·Patch·Regression·Release·rollback 런타임 | 실제 개선 효과는 POC와 Release 전후 평가 필요 |
| 법무·노무·세무 | 다중 라우팅과 안전한 Boundary | 전문가급 Pack은 아직 없음 |
| 전문가 품질 | 평가 프레임워크 존재 | 외부 모델·시니어 회계사 대조는 아직 `not_evaluated` |

기준일별 구현 증거는 [PLUGIN_IMPLEMENTATION_STATUS.md](docs/PLUGIN_IMPLEMENTATION_STATUS.md), 검증 방법과 마지막 기록은 [VALIDATION_WORKFLOW.md](docs/VALIDATION_WORKFLOW.md), 현재 품질 판단과 발전 Gate는 [QUALITY_ASSESSMENT_AND_EVOLUTION.md](docs/QUALITY_ASSESSMENT_AND_EVOLUTION.md)를 확인합니다.

## 안전한 시작

### 요구 환경

- Python `3.11.x`
- `uv`
- 웹 실행 시 Node.js `22.22.0`과 npm

### 플러그인

먼저 오프라인 사전 점검을 실행합니다.

```powershell
python plugin/trusted-ceo-agent/scripts/bootstrap.py preflight
```

엔진은 다음 고정 명령 경계를 통해 실행합니다.

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync `
  python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py <command>
```

전체 상태 전이와 승인 순서는 [플러그인 Skill](plugin/trusted-ceo-agent/skills/trusted-ceo-agent/SKILL.md)과 [Workflow Reference](plugin/trusted-ceo-agent/skills/trusted-ceo-agent/references/workflow.md)를 따릅니다. Artifact root는 작업공간 안의 별도 디렉터리를 사용하고 입력·플러그인·`logs` 디렉터리를 사용하지 않습니다.

### localhost AI 서비스와 웹

```powershell
npm --prefix web install
npm --prefix web run dev:ai
```

기본 주소는 `http://127.0.0.1:3000`입니다. 한 명령이 내부 토큰으로 보호된 Python AI 서비스와 Web UI를 IPv4 localhost에 함께 시작합니다. 브라우저에서 자료 업로드, 웹 HITL, 최종 보고서, 근거 기반 결과 질문과 실행 삭제를 수행하며 플러그인·Codex CLI·터미널 승인을 직접 조작하지 않습니다. API 접근이 준비되지 않으면 저장 보고서 열람은 유지되고 새 AI 분석은 비활성화됩니다.

로그인 없는 단일 사용자 데모이므로 외부에 공개하지 마세요. 입력 한도, 승인 의미, 실패 복구, 저장·삭제 범위와 분리된 live smoke는 [Local AI 서비스 데모](docs/local-ai-demo.md)를 확인합니다.

## 대회 당일 운영

긴 프롬프트를 새 대화마다 다시 붙이지 않습니다. 먼저
[대회 당일 Runbook](docs/operations/HACKATHON_DAY_RUNBOOK.md)을 읽고,
Runbook이 지정한 HD 프롬프트 파일에 변수와 직전 `HANDOFF`만 전달합니다.

최초 진단은 다음 입력으로 시작합니다.

```text
다음 파일을 순서대로 완전히 읽고 HD-01을 실행하세요.

1. docs/operations/HACKATHON_DAY_RUNBOOK.md
2. docs/operations/prompts/HD-01-diagnose-route.md

data_path: "<분석할 데이터의 절대경로>"
project_root: "<저장소 절대경로 또는 null>"
company: null
industry: null
analysis_goal: null
ceo_question: null
analysis_period: null
as_of_date: null
known_constraints: []
change_policy: "green_allowed_yellow_requires_approval_red_forbidden"
```

정본 실행 흐름은 다음과 같습니다.

```text
HD-01 진단
  → 필요할 때만 HD-02 Adapter / HD-03 Pack / HD-04 Component
  → HD-05 분석·HITL·저장·최종화
  → HD-06 WebReportBundle 생성·검증
  → MANUAL_UPLOAD 또는 HD-07 웹 게시·검증
```

HD-05는 분석 결과가 대화창에만 남는 것을 성공으로 처리하지 않습니다.
Finding, 반증, 충돌, 검증 계획, Completion과 최종 결과가 같은 불변 revision의
공식 Artifact에 저장·검증돼야 합니다. HD-06의 출력은 다음 위치에 생성됩니다.

```text
exports/<run_id>/revision-<revision>/web-report-bundle.json
```

수동 게시 시 `http://127.0.0.1:3000/report`에서 이 파일 하나를 선택해
`리포트 가져오기`를 누릅니다. 탭 2는 **저장되고 검증된 뒤 Converter가
WebReportBundle에 공개 매핑한 데이터만** 표시합니다. 대화에만 있는 내용과
비공개 중간 Artifact는 표시하지 않으며, 웹이 누락된 분석을 새로 추론하지
않습니다. HD-06의 `projection_coverage`에서 매핑·생략·차단 범위를 확인합니다.
현재 `/report`의 파일 가져오기는 bundle을 다시 검증해 표시하지만 웹 신뢰
모드는 항상 `unverified_import`(`출처 미확인 묶음`)입니다. HD-06의 source
viewer mode는 Handoff에 보존되지만 파일 업로드가 `trusted_final`을
보존한다고 주장하지 않습니다. trusted 등록 게시에는 artifact store root와
bundle path를 분리하는 별도 웹 계약·구현이 필요하며 현재 HD-07 범위가 아닙니다.


## 저장소 구조

```text
plugin/trusted-ceo-agent/   결정적 CLI, 분석 엔진, Pack, Schema, Trust Kernel
contracts/                  플러그인과 웹이 공유하는 결과 계약
web/                        Next.js 기반 입력·검토·탭 2 UI
tests/                      Python unit·contract·integration·E2E
docs/                       제품·아키텍처·상태·평가 문서
docs/operations/            대회 당일 Runbook과 HD-01~HD-07 실행 계약
docs/superpowers/specs/     승인된 설계와 통합 인덱스
docs/superpowers/plans/     구현계획
```

## 문서 읽기 순서

이 README는 입구 문서이며 설계 정본이나 구현계획을 대체하지 않습니다.

1. [PRD](docs/PRD.md) — 제품·사용자·입력·출력·비목표
2. [Architecture Decisions](docs/ARCHITECTURE_DECISIONS.md) — 확정된 기술·운영 결정
3. [Professional System Integration Index](docs/superpowers/specs/2026-07-17-professional-system-integration-index.md) — 필수 설계 읽기 순서와 충돌 규칙
4. [Plugin Design](docs/superpowers/specs/2026-07-17-trusted-ceo-agent-plugin-design.md) — 플러그인 Trust Kernel과 Artifact 계약
5. [Plugin Implementation Status](docs/PLUGIN_IMPLEMENTATION_STATUS.md) — 기준일별 구현·검증 증거
6. [Hackathon Day Runbook](docs/operations/HACKATHON_DAY_RUNBOOK.md) — 대회 당일 Prompt ID·순서·충돌·Handoff 정본
7. [HD Prompt Pack](docs/operations/prompts/HD-01-diagnose-route.md) — HD-01 진단부터 조건부 수정·분석·변환·게시 실행 계약
8. [Quality Assessment and Evolution](docs/QUALITY_ASSESSMENT_AND_EVOLUTION.md) — 현재 품질·한계·발전 Gate
9. [Synthetic Data POC SOP](docs/evaluation/SYNTHETIC_DATA_POC_SOP.md) — 합성 데이터와 검증 운영 절차
10. [Synthetic Data POC Master Prompt](docs/evaluation/prompts/SYNTHETIC_DATA_POC_MASTER_PROMPT.md) — 새 작업에서 실행할 프롬프트

구현자는 3번 통합 인덱스가 지정한 원문 설계와 구현계획을 생략해서는 안 됩니다.

## 현재 주장할 수 있는 것과 없는 것

현재 가장 강하게 주장할 수 있는 내용은 다음입니다.

> 증거·revision·승인·종료·결과 투영·지식 릴리스를 통제하는 전문 분석 플랫폼과 64개 회계 Issue Family의 실행 골격을 구현했다. 회계 콘텐츠는 아직 전문가 승격 전이며 전문 품질은 별도 POC와 블라인드 평가가 필요하다.

현재 주장하면 안 되는 내용은 다음입니다.

- 시니어 회계사와 동등한 품질이 입증됐다.
- 64개 Family가 모두 전문적으로 정확하다.
- 법무·노무·세무 전문가 수준 분석이 가능하다.
- 테스트 수가 회계적 정확성을 증명한다.
- Knowledge Foundry가 실제 품질을 개선했다는 것이 이미 입증됐다.
- 시스템이 최종 회계·세무·법률·노무·감사 판단을 내린다.

합성 데이터 POC, 반복 안정성, 오탐·누락 평가와 전문가 검토를 통해 이 주장 범위를 단계적으로 승격합니다.
