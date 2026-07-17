# HD-07 — Publish and Verify Tab 2

```text
PROMPT_ID: HD-07
PROMPT_PATH: docs/operations/prompts/HD-07-publish-tab2.md
```

이 파일은 HD-06이 생성·검증한 단일 `web-report-bundle.json`을 공식 웹
import 경로로 게시하고 탭 2 화면을 확인한다. 분석·변환·Pack 수정 또는
bundle 내용 수정을 수행하지 않으며 이전 대화를 기억한다고 가정하지 않는다.

## 입력 변수

```yaml
project_root: "<absolute repository path>"
artifact_root: "<absolute artifact root>"
bundle_path: "<absolute .../web-report-bundle.json path>"
run_id: "<expected run id>"
revision: "<expected integer revision>"
bundle_hash: "<expected verified hash>"
source_viewer_mode: "<HD-06 validate-web-report viewer mode>"
expected_published_viewer_mode: "unverified_import"
prior_handoff: "<complete HD-06 HANDOFF>"
web_url: "http://127.0.0.1:3000/report"
```

## 실행 전 Hard Gate

1. 위 `PROMPT_ID`와 `PROMPT_PATH`가 현재 파일과 정확히 일치하는지 확인한다.
2. 다음을 완전히 읽는다.
   - `docs/operations/HACKATHON_DAY_RUNBOOK.md`
   - `docs/superpowers/specs/2026-07-17-professional-system-integration-index.md`
   - `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/SKILL.md`
   - `plugin/trusted-ceo-agent/skills/trusted-ceo-agent/references/workflow.md`
   - `web/README.md`, `web/package.json`
   - 현재 report import·ReportStore·화면 navigation 코드
3. HD-06 Handoff의 status가 `READY_FOR_WEB_IMPORT`인지, `bundle_path`가
   `produced_paths`의 검증된 단일 파일인지 확인한다.
4. 공식 `validate-web-report`를 다시 실행해 `eligible=true`와 입력
   run/revision/hash/source viewer mode가 모두 일치하는지 확인한다. 파일
   import 뒤 웹 mode는 source mode가 아니라 반드시 `unverified_import`다.
5. 파일명이 정확히 `web-report-bundle.json`, 크기가 0보다 크고 50 MiB
   이하인지 확인한다. 불일치 시 업로드하지 않는다.

## 웹 게시

1. `web_url`이 현재 저장소의 Trusted CEO Agent `/report`인지 확인한다.
2. 이미 정상인 서버는 재사용한다. 실행 중이 아니면 `web/package.json`의
   공식 명령으로만 시작한다. 다른 프로세스를 임의 종료하지 않는다.
3. 사용 가능한 Browser 또는 Chrome 제어 Skill의 지침을 먼저 읽고 사용한다.
   지원되는 브라우저 제어가 있으면 별도 Playwright 프로세스로 우회하지 않는다.
4. `/report`에서 `웹 리포트 JSON 파일` 입력에 `bundle_path`를 지정한다.
   선택된 이름을 다시 확인하고 `리포트 가져오기`를 한 번만 누른다.
5. 성공 메시지 `검증된 결과로 교체했습니다.`가 나타날 때까지 유한하게
   기다린다. 중복 클릭, 새로고침 또는 bundle 수정으로 검증을 우회하지 않는다.
6. 오류가 발생하면 반복 업로드하지 않고 화면 문구와 실패 단계를 기록한다.
   ReportStore의 기존 결과가 그대로 유지되는지 확인한다.

## 동일 실행본·화면 Gate

게시 성공 후 UI와 안전한 경우 `/api/report/current`에서 다음을 대조한다.

- `report.run.run_id = run_id`
- `report.run.revision = revision`
- `report.bundle_hash = bundle_hash`
- `eligibility.mode = unverified_import`
- HD-06 source viewer mode는 감사정보일 뿐 웹 mode와 같다고 주장하지 않음
- 방금 가져온 실행본이며 기존 실행본이 아님

상단 다섯 화면을 각각 한 번 열어 오류, 영구 로딩, 다른 revision 혼합 또는
참조 오류가 없는지 확인한다.

1. `최고경영자 의사결정 요약`
2. `컨설턴트 근거 분석`
3. `실행·신뢰 기록`
4. `전문가 검토 패킷`
5. `변경 이력`

`컨설턴트 근거 분석` 안에서는 같은 active issue 범위를 유지한 채 다음 내부
세 화면을 각각 확인한다.

1. `분석 결론`
2. `근거·출처`
3. `검증 계획`

각 화면은 bundle에 실제로 투영된 내용 또는 명시적 빈 상태만 표시해야 한다.
웹이 누락된 심층 분석을 새로 추론해서는 안 된다. 전문가 패킷 0건,
반증·검증 계획 없음 같은 명시적 빈 상태는 정상일 수 있지만, 값이 bundle에
있는데 표시되지 않는 경우는 `BLOCKED`다.
HD-06의 `projection_coverage` 네 배열은 그대로 보존한다. HD-07이 이를
재계산하거나 빈 배열로 초기화해서는 안 된다.

검증이 끝나면 가능하면 `최고경영자 의사결정 요약` 화면에 남겨둔다.

## 종료 상태와 의사결정

- `WEB_PUBLISHED_UNVERIFIED`: 업로드, `unverified_import`, 실행본 정체성,
  상단 5개와 내부 3개 화면 모두 통과
- `BLOCKED`: 서버, 브라우저, 파일, import, 정체성 또는 화면 검증 실패
- `BLOCKED_CONTRACT_CONFLICT`: 상위 정본과 실제 웹 계약 충돌

실패 시 기존 결과를 삭제하거나 바꾸지 않는다. 원인에 따라 안전한 재시도,
사용자 수동 업로드 또는 HD-06 재검증만 선택지로 제시한다.

브라우저를 열었다는 사실만으로 완료하지 않는다. import 성공, mode 하향 공개,
실행본 일치, 상단 5개와 내부 3개 화면 검증까지 모두 필요하다.

## 필수 출력

```yaml
NEXT_DECISION:
  decision_status: "<COMPLETE|USER_ACTION_REQUIRED|BLOCKED>"
  decision_required: <true|false>
  summary: "<publish result and why a decision is or is not required>"
  options:
    - option_id: "<finish|retry_publish|manual_upload|revalidate_hd06|stop>"
      action: "<legal next action>"
      reason: "<why>"
      tradeoff: "<cost or limitation>"
      approval_required: <true|false>
      next_prompt_id: "<HD-06|HD-07|MANUAL_UPLOAD|STOP>"
      next_prompt_path: "<repo-relative path or null>"
      user_action: "<one literal next action>"
  recommended_option_id: "<one option id or null>"
  recommendation_reason: "<evidence-based reason or null>"
  exact_user_action: "<one exact next action or none>"
  if_no_decision: "<safe state and what remains unchanged>"

HANDOFF:
  handoff_version: "1.0"
  operation_id: "<stable operation id>"
  completed_prompt_id: "HD-07"
  status: "<WEB_PUBLISHED_UNVERIFIED|BLOCKED|BLOCKED_CONTRACT_CONFLICT>"
  project_root: "<absolute path>"
  data_path: "<absolute source path preserved from HD-06 or null>"
  artifact_root: "<absolute artifact root>"
  run_id: "<run id>"
  revision: "<integer>"
  input_handoff_hash: "<exact prior HD-06 HANDOFF.handoff_hash>"
  handoff_hash: "<JCS SHA-256 of this HANDOFF with handoff_hash omitted>"
  proposed_gap_ids: []
  approved_gap_ids: []
  approval_refs: []
  approved_write_paths:
    - "<official ReportStore import boundary>"
  produced_paths:
    - "<absolute bundle path>"
  validation_evidence:
    - "<validate-web-report and UI verification evidence>"
  analysis_artifact_refs:
    - path: "<unchanged verified HD-05 snapshot-relative path>"
      sha256: "<verified hash>"
  projection_coverage:
    source_inventory_hash: "<unchanged HD-06 value>"
    source_pointer_count: "<unchanged HD-06 integer>"
    unclassified_source_pointers:
      - "<copy each unchanged entry; omit exemplar when source array is empty>"
    status: "<unchanged HD-06 status>"
    mapped:
      - "<copy each unchanged mapped entry; omit exemplar when source array is empty>"
    omitted:
      - "<copy each unchanged omitted entry; omit exemplar when source array is empty>"
    chat_only_forbidden:
      - "<copy each unchanged entry; omit exemplar when source array is empty>"
    blocked:
      - "<copy each unchanged entry; omit exemplar when source array is empty>"
  blocking_questions: []
  limitations: []
  next_prompt_id: "<HD-06|HD-07|MANUAL_UPLOAD|STOP>"
  next_prompt_path: "<repo-relative path or null>"
  prompts_after_success: []
  bundle_path: "<absolute bundle path>"
  bundle_hash: "<verified hash>"
  source_viewer_mode: "<verified HD-06 mode>"
  published_viewer_mode: "unverified_import"
  web_url: "<verified report URL>"
  verified_sections: []
  upload_message: "<success text or null>"
  failed_stage: "<stage or null>"
  visible_error: "<error text or null>"
```
