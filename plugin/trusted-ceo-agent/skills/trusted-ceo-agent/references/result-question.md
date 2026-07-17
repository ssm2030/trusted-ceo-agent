# 결과 질문

결과 질문은 finalized revision을 바꾸지 않는 읽기 전용 흐름입니다. 모델 초안은 사용자에게 직접 표시하지 않고 플러그인이 검증해 만든 canonical answer만 표시합니다.

## 순서

1. 고정 launcher로 질문 Job을 만듭니다.

   ```text
   uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py prepare-result-question --artifact-root <root> --run-id <run_id> --revision <revision> --question-file <utf8-file> --scope-kind <kind> --scope-instance-id <id> --privacy-classification <classification>
   ```

2. 반환된 Job을 바꾸지 않고 격리된 one-shot 모델에 전달합니다. 모델은 `templates/result-question/SKILL.md`만 따르고 `result-answer-draft.schema.json` 형식의 JSON 초안 하나만 반환해야 합니다.
3. Job과 초안을 고정 launcher로 검증합니다.

   ```text
   uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python plugin/trusted-ceo-agent/scripts/trusted_ceo_agent.py validate-result-answer --artifact-root <root> --run-id <run_id> --revision <revision> --job <job-json> --draft <draft-json>
   ```

4. `data.answer`의 canonical answer만 사용자에게 표시합니다. 검증 실패, revision 불일치, 범위 밖 참조는 표시하거나 저장하지 않습니다.

`SCOPE_REQUIRED`가 반환되면 제안된 더 좁은 범위를 사용자에게 제시하고 Codex를 호출하지 않습니다. 두 명령 모두 snapshot, current pointer, 승인 기록을 수정하지 않습니다.
