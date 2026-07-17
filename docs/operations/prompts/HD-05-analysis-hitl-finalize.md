# HD-05 — Analysis, HITL and Finalize

```text
PROMPT_ID: HD-05
PROMPT_PATH: docs/operations/prompts/HD-05-analysis-hitl-finalize.md
```

이 파일은 실제 데이터 분석, 사람의 답변 반영, 사건 종결과 최종화를 담당한다.
이전 대화의 선행 결과를 기억한다고 가정하지 않는다.

## 입력 변수

```yaml
project_root: "<absolute repository path>"
data_path: "<absolute source path>"
artifact_root: "<absolute artifact root inside project_root>"
run_id: "<existing run id or null when a new run is required>"
expected_revision: "<current integer revision or null>"
mission_contract_path: "<absolute path or null>"
approved_release_refs: []
approved_scope_ref: "<approved deep-dive scope ref or null>"
accounting_input_path: "<absolute closed request JSON path or null>"
professional_input_path: "<absolute closed request JSON path or null>"
prior_handoff: "<complete HANDOFF block or null>"
```

누락값은 저장소와 Artifact에서 하나로 결정될 때만 발견해서 채운다. 후보가
여러 개거나 의미가 불분명하면 임의 선택하지 않고 `NEEDS_INPUT`으로 끝낸다.

## 실행 전 Hard Gate

1. 위 `PROMPT_ID`와 `PROMPT_PATH`가 현재 파일과 정확히 일치하는지 확인한다.
2. 다음 파일을 완전히 읽고 이 순서의 권한을 적용한다.
   - `docs/operations/HACKATHON_DAY_RUNBOOK.md`
   - `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   - `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/SKILL.md`
   - `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/references/workflow.md`
3. 현재 CLI, Schema, Adapter·Pack·Component Registry와 선행 Handoff를
   확인한다. 문서와 코드가 충돌하면 `BLOCKED_CONTRACT_CONFLICT`로 끝낸다.
4. `approved_release_refs`와 입력 snapshot을 고정한다. 승인되지 않은 Pack,
   Component 또는 전문 권한을 일반 LLM 지식으로 보충하지 않는다.
5. 원본, 기존 snapshot, 승인 기록, authority 또는 hash를 직접 수정하지 않는다.

## 공식 실행 경계

플러그인의 정식 Skill과 다음 CLI만 사용한다.

```powershell
python plugin/trusted-ceo-agent/scripts/bootstrap.py preflight
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py <command>
```

`preflight` 실패 시 설치·업데이트를 시도하지 말고 중단한다. `start`는
`--expected-revision`을 받지 않으며, 기존 run을 바꾸는 모든 mutation에는
현재 `--expected-revision`을 사용한다. 종료 코드 2는 사용자 행동, 3은 계약
입력 수정, 4는 무결성·승인 검토, 6은 `status` 후 stale 제안 폐기를 뜻한다.

## 분석 절차

1. 신규 실행이면 `start`, 기존 실행이면 `status`로 run identity를 확정한다.
2. Skill의 정식 순서로 Intake, `scan`, Canonical Mapping, Data HITL,
   Fact·Lineage·Quality, 승인 Gate, 결정적 Component와 Reasoning Job을
   실행한다.
3. `run-components`의 `--accounting-input`과 `--professional-input`은 승인된
   closed request가 있을 때만 사용한다. `scope_ref`는 승인 범위와 같아야 한다.
4. Signal Case Queue의 우선순위를 따르고 한 번에 deep active case를 하나만
   처리한다. 현재 사건의 필수 도메인, 반증, 구별검사와 required Work Item을
   종결·checkpoint한 뒤 다음 사건으로 이동한다.
5. 모델 초안은 각 frozen Job allowlist 안에서만 작성하고
   `ingest-result`와 해당 `reduce-stage`로 검증한다. Fact, Signal, Grade,
   Finding 관계 또는 승인을 직접 만들지 않는다.
6. 모든 required Case는 `status=terminal`이며 다음 중 하나의 disposition과
   `terminal_reason`을 가져야 한다.
   `substantiated`, `not_substantiated`, `inconclusive`, `merged`,
   `out_of_scope`, `expert_review_required`, `deferred`, `failed`,
   `cancelled`.
7. required 실패, 미충족 domain barrier, 미해결 무결성 오류는 제한 완료로
   우회하지 않는다. 지원되지 않는 법무·노무·세무는 Boundary,
   `not_assessable`, `unsupported_pack` 또는 전문가 검토로 보존한다.

## HITL 답변 → 새 revision

1. `pending-action`으로 현재 immutable Action Card를 읽는다.
2. 현재 결론을 바꿀 수 있는 질문만 한 카드에 묶어 사용자에게 제시한다.
   질문마다 선택지, 이유·대가, 권장안·권장 이유와 사용자의 정확한 응답
   형식을 제공한다.
3. 분석에 영향을 주는 답변은 먼저 읽기 전용 `preview-human-response`로
   검증한 뒤 같은 card ID·content hash·expected revision과 안정적인
   idempotency key로 `submit-human-response`한다.
4. `request_explanation` 이외의 수락된 답변은 정확히 새 revision 하나를
   만들며, 영향받는 downstream만 새 snapshot에서 재실행한다. snapshot을
   수동 병합하지 않는다.
5. Human Response는 Approval Record가 아니다. 응답 결과가
   `terminal_approval_required`이면 사용자가 실제 Terminal TTY에서
   `approve-interactive` 또는 `decide-interactive`를 실행할 때까지 기다린다.
   nonce, 승인 파일 또는 파이프로 승인을 위조하지 않는다.

## Completion·Finalization Gate

1. CompletionAssessment가 `finalization_ready` 또는 사용자가 한계를 명시적으로
   확인한 `limited_completion_ready`인지 검사한다.
2. blocking case, required work, required domain route, invalid Finding와 hard
   failure가 허용되지 않은 채 남아 있으면 `BLOCKED_REQUIRED_FAILURE`다.
3. Cross-Finding Join, Cross-domain Integration, 충돌 공개, Coverage,
   Final Validator와 TTY final approval 조건을 모두 확인한다.
4. `prepare-finalization` 후 writer Job을 정식 경로로 처리하고
   `approval-request --gate final`을 생성한다. 실제 TTY 승인 후에만
   `finalize`한다.
5. 최종 revision에 읽기 전용 `validate`와 `render`를 실행한다.

## Analysis Persistence Gate

최종화 성공을 보고하기 전에 같은 `run_id`와 최종 `revision`의 검증된
snapshot에 아래 경로가 모두 존재해야 한다.

```text
analysis/professional/runtime-result.json
analysis/professional/signal-cases.json
analysis/professional/findings.json
analysis/professional/relations.json
analysis/professional/issue-clusters.json
analysis/professional/completion-assessment.json
analysis/professional/grading-inputs.json
analysis/professional/grade-records.json
analysis/professional/execution-authority.json
final/structured-output.json
final/result.json
final/ceo-brief.md
final/issue-tree.json
final/evidence-cards.json
final/monitoring-and-blind-spots.json
final/expert-packets.json
final/validation-summary.json
final/audit-manifest.json
final/professional-publication.json  # professional flow only
```

다음을 모두 검증한다.

- snapshot manifest의 각 경로와 SHA-256이 실제 파일과 일치한다.
- runtime result, Completion, Final Result와 workflow state의 run/revision
  정체성이 서로 닫혀 있다.
- Signal Case→Finding→Relation·Cluster→Grade→Final Result 참조가 닫혀 있다.
- `validate`가 full snapshot 계약을, `render`가 byte-equivalence를 통과한다.
- 실질적인 결론, 반증, Finding, 관계, 검증 계획 또는 한계가 대화에만 남지
  않고 위 Artifact에 저장되어 있다.

필수 경로·hash·참조가 하나라도 불일치하거나 실질적 분석이 chat-only이면
`BLOCKED_ANALYSIS_PERSISTENCE`로 종료한다. 대화 내용을 임의로 `.md`에
복사하거나 약한 성공으로 바꾸지 않는다.

## 종료 상태

- `FINALIZED`: 정상 Completion, TTY 승인, Validator와 Persistence Gate 통과
- `LIMITED_FINALIZED`: 사용자가 확인한 제한 완료, TTY 승인과 모든 Gate 통과
- `NEEDS_INPUT`: 현재 Action Card 또는 입력 의미 확인이 필요
- `BLOCKED_REQUIRED_FAILURE`: required 절차·도메인·무결성 실패
- `BLOCKED_ANALYSIS_PERSISTENCE`: 저장·동일 revision·참조 폐쇄성 실패
- `BLOCKED_CONTRACT_CONFLICT`: 상위 정본과 실행 계약 충돌

`FINALIZED` 또는 `LIMITED_FINALIZED`일 때만 다음 경로를 권장할 수 있다.

```text
HD-06
docs/operations/prompts/HD-06-export-web-report.md
```

## 필수 출력

설명 뒤 아래 두 블록을 문자 그대로 출력한다. 현재 상태에서 합법적인
선택지만 최대 3개 제시하며, 각 선택지에는 이유, 대가와 사용자의 정확한
다음 행동을 넣는다. 권장안은 선택지 ID로 한 번만 지정한다.

```yaml
NEXT_DECISION:
  decision_status: "<READY|USER_ACTION_REQUIRED|BLOCKED|COMPLETE>"
  decision_required: <true|false>
  summary: "<current result and why a decision is or is not required>"
  options:
    - option_id: "<stable option id>"
      action: "<legal next action>"
      reason: "<why>"
      tradeoff: "<cost or limitation>"
      approval_required: <true|false>
      next_prompt_id: "<HD-05|HD-06|STOP>"
      next_prompt_path: "<repo-relative path or null>"
      user_action: "<one literal next action>"
  recommended_option_id: "<one option id or null>"
  recommendation_reason: "<evidence-based reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and what remains unchanged>"

HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable operation id>"
  completed_prompt_id: "HD-05"
  status: "<FINALIZED|LIMITED_FINALIZED|NEEDS_INPUT|BLOCKED_REQUIRED_FAILURE|BLOCKED_ANALYSIS_PERSISTENCE|BLOCKED_CONTRACT_CONFLICT>"
  project_root: "<absolute path>"
  data_path: "<absolute path>"
  artifact_root: "<absolute path>"
  run_id: "<run id>"
  revision: "<integer>"
  input_handoff_hash: "<exact prior HANDOFF.handoff_hash or null>"
  handoff_hash: "<JCS SHA-256 of this HANDOFF with handoff_hash omitted>"
  proposed_gap_ids: []
  approved_gap_ids: []
  approval_refs: []
  approved_write_paths:
    - "<official artifact root mutation boundary>"
  produced_paths: []
  validation_evidence: []
  analysis_artifact_refs:
    - path: "<snapshot-relative required path>"
      sha256: "<verified hash>"
  projection_coverage:
    status: "not_started"
    mapped: []
    omitted: []
    chat_only_forbidden: []
    blocked: []
  blocking_questions: []
  limitations: []
  next_prompt_id: "<HD-05|HD-06|STOP>"
  next_prompt_path: "<repo-relative path or null>"
  prompts_after_success: []
```
