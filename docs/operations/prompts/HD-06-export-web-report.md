# HD-06 — Export Web Report

```text
PROMPT_ID: HD-06
PROMPT_PATH: docs/operations/prompts/HD-06-export-web-report.md
```

이 파일은 하나의 finalized revision을 검증된 WebReportBundle로 무추론
변환한다. 분석, HITL, Finding 또는 snapshot mutation을 수행하지 않으며
이전 대화를 기억한다고 가정하지 않는다.

## 입력 변수

```yaml
project_root: "<absolute repository path>"
artifact_root: "<absolute artifact root>"
run_id: "<finalized run id>"
revision: "<finalized integer revision>"
prior_handoff: "<complete HD-05 HANDOFF>"
```

출력 경로는 변수로 받지 않고 다음 계약으로 결정한다.

```text
<project_root>/exports/<run_id>/revision-<revision>/web-report-bundle.json
```

## 실행 전 Hard Gate

1. 위 `PROMPT_ID`와 `PROMPT_PATH`가 현재 파일과 정확히 일치하는지 확인한다.
2. 다음을 완전히 읽는다.
   - `docs/operations/HACKATHON_DAY_RUNBOOK.md`
   - `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   - `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/SKILL.md`
   - `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/references/workflow.md`
   - 현재 CLI의 `validate`, `render`, `export-web-report`,
     `validate-web-report` 구현
   - `plugin/trusted-ceo-agent/schemas/web-report-input-manifest.schema.json`
   - `contracts/web-report/v1/web-report-bundle.schema.json`
3. HD-05 Handoff의 `artifact_root`, `run_id`, `revision`과
   `analysis_artifact_refs`를 실제 snapshot·manifest와 대조한다.
4. workflow가 `finalized`가 아니거나 Analysis Persistence Gate 증거가
   불완전하면 `BLOCKED`로 끝내고 HD-05로 돌려보낸다.
5. 후보가 여러 개면 최신이라는 이유로 선택하지 않는다.

## 공식 실행

공식 CLI prefix만 사용한다.

```powershell
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py <command>
```

다음 순서를 지킨다.

1. CLI의 현재 작업 디렉터리를 정확히 `project_root`로 고정한다.
2. `status`로 current identity를 확인하되 입력 revision을 임의 변경하지 않는다.
3. 명시된 revision에 `validate`를 실행한다.
4. `render`로 `render_package`가 정의한 전체 결정적 최종 패키지의
   byte-equivalence를 확인한다.
5. snapshot manifest에서 `final/result.json`의 SHA-256을 읽어
   `web-report-input-manifest.schema.json`에 맞는 단일 입력 manifest를 만든다.
   이 임시 manifest는 안전한 임시 위치에 두고 snapshot을 수정하지 않는다.
   export 성공·실패 후 해당 임시 파일만 제거하여 영구 산출물이 bundle
   하나뿐이게 한다.
6. 고정 출력 경로의 부모가 없으면 `project_root` 안이며 플러그인·run·`logs`·
   `web/var` 밖인 정확한 부모 디렉터리만 만든다.
7. 고정 출력 파일이 이미 있으면 덮어쓰거나 삭제하지 않는다. 같은
   run/revision으로 `validate-web-report`를 실행해 현재 계약에도 유효하면
   그대로 재사용하고, 불일치하거나 유효하지 않으면 `BLOCKED`로 끝낸다.
8. 고정 출력 파일이 없을 때만 정확한 `--input-manifest`와 고정 출력 경로로
   `export-web-report`를 한 번 실행한다.
9. 생성 또는 재사용한 파일에 같은 run/revision을 지정해
   `validate-web-report`를 실행한다.
10. validator 결과의 `eligible=true`, `bundle_hash`, source `viewer_mode`와
    bundle의 `workflow_state=finalized`, 파일명이 정확히
    `web-report-bundle.json`인지 확인한다.

Converter 또는 운영자가 새 Finding, Grade, 관계, Evidence, 전문 판단,
문장 의미를 만들거나 약화해서는 안 된다.

## Projection Coverage Gate

실제 converter 코드, Final Result와 WebReportBundle Schema를 대조해
`projection_coverage`를 작성한다. 다음 네 범주를 섞지 않는다.

- `mapped`: 검증된 source Artifact 필드와 실제 public bundle 목적지
- `omitted`: 저장됐지만 public 계약에 매핑되지 않은 필드와 이유. 각 항목은
  `classification=private|public_contract_omission`으로 private 비공개와
  공개 계약 누락을 구별한다.
- `chat_only_forbidden`: 대화에만 존재해 내보낼 수 없는 실질 분석
- `blocked`: 매핑·privacy·참조 불일치 때문에 export를 차단한 항목

`mapped`는 source path/field와 destination path/field를 함께 기록한다.
`omitted`는 누락을 숨기지 않고 분류, 이유, 사용자 영향과 제한을 기록한다.
모든 심층 Artifact가 public bundle에 포함된다고 주장하지 않는다.
Inventory는 converter가 실제 읽는 `final/result.json`,
`final/structured-output.json`, `evidence/core.json`, 승인 ancestry와 revision
Artifact의 source JSON Pointer를 포함한다. 각 pointer는 `mapped`, `omitted`,
`blocked` 중 정확히 하나에만 있어야 하며 누락·중복은 `blocked`다.
`complete`는 모든 pointer가 분류되고 public contract omission, blocked,
chat-only가 없는 상태다. `partial`은 모든 pointer가 분류됐지만
`public_contract_omission`이 있는 유효한 bundle이다. `blocked`는 미분류,
중복, 참조·privacy 불일치 또는 chat-only가 있는 상태다.

`chat_only_forbidden`이 한 건이라도 있으면 `READY_FOR_WEB_IMPORT`가 아니며
`BLOCKED`로 종료하고 HD-05 Persistence Gate로 되돌린다.

bundle 자체와 `validate-web-report`가 검증 증거다. 변환기는 저장되지 않은
대화 내용을 합성하거나 private 중간 Artifact를 노출해서는 안 된다.

## 종료 상태와 의사결정

- `READY_FOR_WEB_IMPORT`: 고정 경로의 단일 bundle과 모든 Gate 통과
- `BLOCKED`: finalization, persistence, export, validation 또는 coverage 실패
- `BLOCKED_CONTRACT_CONFLICT`: 상위 정본과 실제 코드 계약 충돌

성공 시 유효한 선택지는 사용자의 수동 업로드 또는 다음 게시 프롬프트다.

```text
HD-07
docs/operations/prompts/HD-07-publish-tab2.md
```

수동 업로드는 `/report`의 `웹 리포트 JSON 파일`에서 산출물을 선택하고
`리포트 가져오기`를 누르는 절차다. 자동 게시가 필요하거나 수동 업로드에
실패한 경우에만 HD-07을 권장한다.

## 필수 출력

`produced_paths`에는 검증에 성공한 bundle만 넣고 경로를 추측하지 않는다.
실패 파일의 존재를 성공으로 보고하지 않는다.

```yaml
NEXT_DECISION:
  decision_status: "<READY|BLOCKED>"
  decision_required: <true|false>
  summary: "<export result and why a decision is or is not required>"
  options:
    - option_id: "<manual_upload|publish_with_hd07|repair_with_hd05|stop>"
      action: "<legal next action>"
      reason: "<why>"
      tradeoff: "<cost or limitation>"
      approval_required: <true|false>
      next_prompt_id: "<MANUAL_UPLOAD|HD-05|HD-07|STOP>"
      next_prompt_path: "<repo-relative path or null>"
      user_action: "<one literal next action, including bundle path when applicable>"
  recommended_option_id: "<one option id or null>"
  recommendation_reason: "<evidence-based reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and what remains unchanged>"

HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable operation id>"
  completed_prompt_id: "HD-06"
  status: "<READY_FOR_WEB_IMPORT|BLOCKED|BLOCKED_CONTRACT_CONFLICT>"
  project_root: "<absolute path>"
  data_path: "<absolute source path or null>"
  artifact_root: "<absolute artifact root>"
  run_id: "<run id>"
  revision: "<integer>"
  input_handoff_hash: "<exact prior HD-05 HANDOFF.handoff_hash>"
  handoff_hash: "<JCS SHA-256 of this HANDOFF with handoff_hash omitted>"
  proposed_gap_ids: []
  approved_gap_ids: []
  approval_refs: []
  approved_write_paths:
    - "<absolute export bundle path>"
  produced_paths:
    - "<absolute .../web-report-bundle.json path>"
  validation_evidence:
    - "<validate, render, export-web-report and validate-web-report evidence>"
  analysis_artifact_refs:
    - path: "<unchanged verified HD-05 snapshot-relative path>"
      sha256: "<verified hash>"
  projection_coverage:
    source_inventory_hash: "<JCS SHA-256 of sorted source JSON Pointer inventory>"
    source_pointer_count: "<integer>"
    unclassified_source_pointers: []
    status: "<complete|partial|blocked>"
    mapped:
      - source: "<artifact path and field>"
        destination: "<bundle path and field>"
    omitted:
      - source: "<artifact path and field>"
        classification: "<private|public_contract_omission>"
        reason: "<why omitted>"
        user_impact: "<visible limitation>"
    chat_only_forbidden: []
    blocked: []
  blocking_questions: []
  limitations: []
  next_prompt_id: "<MANUAL_UPLOAD|HD-05|HD-07|STOP>"
  next_prompt_path: "<repo-relative path or null>"
  prompts_after_success: []
  bundle_path: "<absolute path or null>"
  bundle_hash: "<verified hash or null>"
  source_viewer_mode: "<verified validate-web-report mode or null>"
```
