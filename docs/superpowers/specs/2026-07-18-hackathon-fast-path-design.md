# Trusted CEO Agent 대회 Fast Path 설계

- 상태: 사용자 승인
- 기준일: 2026-07-18
- 목표: 기존 HD-01~HD-07을 변경하지 않고 신규 구현을 최소화한 빠른 진단 경로 제공
- 비목표: Trust Kernel, 승인, 불변 revision, Validator, HD-05~HD-07 완료 Gate 완화

## 1. 결정

Fast Path는 새 읽기 전용 진단 Prompt `HDF-01`과 전용 Runbook으로 격리한다.
실제 Adapter·Component 변경과 분석·게시 작업은 기존 `HD-02`, `HD-04`,
`HD-05`, `HD-06`, `HD-07`을 재사용한다.

기본 정책은 코드 변경 금지다. 다음 두 변경만 분석 중단을 피하기 위한 예외로
허용한다.

1. CEO 질문의 핵심 열을 기존 Adapter와 Green 매핑으로 읽을 수 없을 때
   `HD-02` Adapter Gap 최대 1건
2. CEO 결론에 직접 필요한 결정적 계산이 없을 때 `HD-04` Component Gap
   최대 1건

`HD-03`은 실행하지 않는다. Pack 부족은 Generic 또는 Boundary 결과와 명시적
한계로 보존한다. 비핵심 Gap은 관련 분석·수치·Finding을 범위에서 제외한다.
두 예외로도 의미 있는 핵심 결과가 성립하지 않으면 `STOP`한다.

## 2. 파일 구조

```text
docs/operations/
├─ HACKATHON_FAST_PATH_RUNBOOK.md
└─ prompts/
   └─ HDF-01-fast-diagnose-route.md
```

Fast Path Runbook은 정책, 예외 예산, 라우팅, Handoff 확장, 최초·후속 입력
템플릿을 정의한다. `HDF-01`은 최소 읽기 전용 진단과 정확한 다음 Prompt
선택만 담당한다.

## 3. 정본 우선순위

1. 코드가 검증하는 Schema·Trust Kernel·승인·authority·hash·Validator 계약
2. 전문 시스템 통합 인덱스와 D01~D18 정본
3. `docs/operations/HACKATHON_DAY_RUNBOOK.md`
4. `docs/operations/HACKATHON_FAST_PATH_RUNBOOK.md`
5. 실행 대상 Prompt 파일
6. 대화의 임시 지시

Fast Path는 상위 계약을 좁힐 수만 있고 완화하지 못한다. 충돌은
`BLOCKED_CONTRACT_CONFLICT`다.

## 4. HDF-01 책임과 입력

`HDF-01`은 다음만 수행한다.

- 데이터의 파일·표·열·형식·단위·기간을 구조적으로 조사
- CEO 질문과 핵심 결과에 필요한 핵심 열을 식별
- 기존 Adapter 또는 Green 매핑으로 핵심 열을 읽을 수 있는지 확인
- 기존 결정적 Component가 필수 계산을 제공하는지 확인
- Pack 부족을 Generic·Boundary로 제한할 수 있는지 확인
- 비핵심 Gap과 이에 의존하는 분석을 제외 목록으로 확정
- 다음 Prompt ID와 경로를 하나로 결정

필수 입력은 절대 `data_path`다. `project_root`, 회사·업종·기간·CEO 질문은
선택 입력이며 불명확한 경제적 의미를 추측하지 않는다. HDF-01은 코드, 설정,
원본 데이터, snapshot, run, Artifact를 수정하거나 만들지 않는다.

## 5. 라우팅

```text
HDF-01
  ├─ 기존 기능·Green 매핑으로 충분
  │    └─ HD-05
  ├─ 비핵심 Gap만 존재
  │    └─ 의존 분석 제외 + Generic/Boundary → HD-05
  ├─ 핵심 열을 읽을 수 없음
  │    └─ HD-02 최대 1건 → HD-05
  ├─ 필수 계산이 없음
  │    └─ HD-04 최대 1건 → HD-05
  ├─ 핵심 열과 필수 계산이 모두 없음
  │    └─ HD-02 최대 1건 → HD-04 최대 1건 → HD-05
  ├─ 핵심 경제적 의미 확인 필요
  │    └─ USER_RESPONSE → HDF-01 재진단
  └─ 예외 예산으로도 핵심 결과 불성립
       └─ STOP
```

HD-02가 필요하면 구조적 입력을 먼저 고친 뒤 HD-04를 실행한다. 각 Yellow
Gap은 기존 Runbook대로 실제 Gap ID와 쓰기 경로를 사용자가 명시 승인해야
한다. Fast Path 선택은 아직 발견되지 않은 Gap의 포괄 승인이 아니다.

## 6. 예외 조건

### HD-02 최대 1건

다음을 모두 만족해야 한다.

- CEO 질문에 직접 필요한 핵심 열이다.
- 기존 Adapter와 Green 매핑으로 의미 손실 없이 읽을 수 없다.
- 해당 열을 제외하면 핵심 결과가 성립하지 않는다.
- 최소 필드·lineage·단위·기간 지원으로 닫힌 변경을 정의할 수 있다.
- 특정 Gap ID, 쓰기 경로, focused 검증과 롤백 대상을 명시할 수 있다.

### HD-04 최대 1건

다음을 모두 만족해야 한다.

- CEO 결론에 직접 필요한 계산이다.
- 기존 Component와 검증된 조합으로 계산할 수 없다.
- 계산을 제외하면 핵심 결과가 성립하지 않는다.
- 입력 Canonical Fact가 존재하거나 선행 HD-02 결과로 제공된다.
- 하나의 결정적 계약과 focused 검증으로 닫을 수 있다.

### HD-03 금지

Pack 부족을 일반 LLM 지식으로 보충하지 않는다. Generic 또는 Boundary로
제한하고 전문 판단, Norm 적용, 강한 인과·규제 결론을 만들지 않는다.

## 7. 상태와 Handoff

HDF-01 종료 상태는 다음과 같다.

- `FAST_GO`: 변경 없이 HD-05 진행
- `FAST_LIMITED_GO`: 제외 범위와 Generic·Boundary 한계로 HD-05 진행
- `FAST_EXCEPTION_REQUIRED`: HD-02 또는 HD-04의 특정 Gap 승인 필요
- `NEEDS_USER_CLARIFICATION`: 핵심 의미를 확인해야 함
- `NO_GO`: 예외 예산으로도 핵심 결과 불가능
- `BLOCKED_CONTRACT_CONFLICT`: 상위 계약과 충돌

기존 Handoff 필드를 유지하고 다음 확장을 추가한다.

```yaml
fast_path:
  policy_version: "1.0"
  hd02_budget: 1
  hd02_used: 0
  hd04_budget: 1
  hd04_used: 0
  hd03_allowed: false
  generic_boundary_required: false
  excluded_gap_ids: []
  excluded_analysis_scopes: []
  exception_sequence: []
```

Fast Path 후속 입력은 Fast Path Runbook, 기존 Runbook, 대상 Prompt를 함께
읽고 이 블록을 다음 Handoff에 보존한다. 예산을 모두 사용한 뒤 추가 변경이
필요하면 관련 분석을 제외해도 핵심 결과가 성립하는지 확인하고, 불가능하면
`STOP`한다.

## 8. 성능 규칙

- HDF-01은 테스트를 실행하지 않고 마지막 확인 가능한 기준선만 기록한다.
- `rg`와 `rg --files`로 관련 Adapter·Component·Registry·Schema만 찾는다.
- 전체 구현 디렉터리, 전체 테스트, 전체 로그를 반복해서 읽지 않는다.
- 데이터는 구조와 핵심 열 판단에 필요한 최소 범위만 읽고 원본 값을 장문
  출력하지 않는다.
- 독립 읽기만 병렬화하고 쓰기·patch·검증 흐름은 하나만 유지한다.
- 같은 권한·sandbox·spawn 실패를 상태 변화 없이 재실행하지 않는다.
- HD-02·HD-04 구현 중에는 관련 focused RED/GREEN만 실행하고, 기존
  Prompt가 요구하는 완료 Gate는 유지한다.
- 전체 finalization·Validator·내보내기·웹 import 검증은 생략하지 않는다.

## 9. 오류 처리

- 핵심 열의 경제적 의미가 불명확하면 Adapter를 추측하지 않고
  `NEEDS_USER_CLARIFICATION`으로 종료한다.
- HD-02·HD-04의 특정 Gap 승인이 없으면 수정하지 않는다.
- HD-02 또는 HD-04가 실패하면 약한 성공으로 바꾸지 않고 기존 Prompt의
  차단 상태를 보존한다.
- required 실패, 무결성 오류, Persistence Gate 실패는 limited 결과로
  우회하지 않는다.
- Windows 절대경로와 가상환경은 macOS Handoff에서 재사용하지 않고 현재
  절대경로를 다시 검증한다.

## 10. 정적 검증

구현 후 다음을 확인한다.

1. 새 파일 두 개가 존재하고 기존 HD-01~HD-07 내용은 바뀌지 않았다.
2. Fast Runbook과 HDF-01에 예외 예산, HD-03 금지, Generic·Boundary,
   `NEXT_DECISION`, `HANDOFF`, `fast_path`가 존재한다.
3. 모든 Prompt ID와 상대경로가 실제 파일과 일치한다.
4. 다음 경로가 Handoff만으로 복원된다.
   - `HDF-01 → HD-05`
   - `HDF-01 → HD-02 → HD-05`
   - `HDF-01 → HD-04 → HD-05`
   - `HDF-01 → HD-02 → HD-04 → HD-05`
   - `HDF-01 → USER_RESPONSE → HDF-01`
   - `HDF-01 → STOP`
5. 입력 placeholder 밖에 `TBD`, `TODO` 또는 단순 숫자 Prompt 참조가 없다.

## 11. 완료 기준

- 사용자가 복사할 최초 입력 템플릿만으로 HDF-01을 시작할 수 있다.
- HDF-01 출력만으로 다음 Prompt와 정확한 파일을 선택할 수 있다.
- Fast Path가 기존 HD 파일을 수정하거나 검증·승인 계약을 완화하지 않는다.
- 신규 구현은 HD-02 최대 1건과 HD-04 최대 1건을 넘지 않는다.
- Pack 부족은 HD-03 대신 Generic·Boundary와 limitations로 남는다.
