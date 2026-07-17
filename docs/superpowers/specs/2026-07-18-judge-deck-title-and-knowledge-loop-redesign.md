# Judge Deck Title and Knowledge Loop Redesign

## Scope

심사위원용 10장 PPTX의 모든 제목을 문장형 종결이 없는 제목형 명사구로 통일하고, 10페이지 Knowledge Foundry의 화살표를 교차 없는 순환 구조로 재설계한다.

기존 본문, 색상 체계, 슬라이드 순서와 전체 스토리는 유지한다.

## Title Mapping

1. `TRUSTED CEO Agent`
2. `수많은 기업 데이터를 여러 전문 관점으로 검토`
3. `긴 기업 점검 절차를 검토 가능한 초안으로 압축`
4. `몇 번의 질문으로 분석 범위와 우선순위 설정`
5. `제안·근거·출처·반증이 연결된 Finding`
6. `결과에서 근거까지 이어지는 대화형 탐색`
7. `회사·업종별 Adapter와 Domain Pack 교체`
8. `전문 사고법·규범지식·검증 절차·반증의 교차검증`
9. `감사 가능한 분석을 만드는 Trust Kernel`
10. `피드백·회귀테스트·승격의 Knowledge Foundry`

## Slide 10 Knowledge Loop

주 흐름은 다음 순서의 2행 시계방향 루프로 표현한다.

`Feedback Record → Patch Proposal → Regression Test → 3단계 승인 → Versioned Release → 다음 Run 적용 → Feedback Record`

- 커넥터는 노드보다 먼저 만들거나 외곽 경로를 사용해 노드와 텍스트를 관통하지 않는다.
- 주 흐름은 파란색, 승인 이후 흐름은 초록색으로 구분한다.
- rollback은 `다음 Run 적용`에서 `Versioned Release`로 돌아가는 별도의 빨간 점선 경로로 표현한다.
- rollback 문구는 경로 가까이에 두되 다른 연결선이나 노드와 겹치지 않는다.

## Acceptance Criteria

- 10개 슬라이드 제목에 `합니다`, `됩니다`, `있습니다` 형태의 문장형 종결이 없다.
- 문제 정의 슬라이드 제목은 정확히 `수많은 기업 데이터를 여러 전문 관점으로 검토`이다.
- 10페이지의 모든 화살표가 한눈에 따라갈 수 있는 방향성을 가진다.
- 커넥터가 노드, 제목, 설명 텍스트를 관통하거나 서로 불필요하게 교차하지 않는다.
- 최종 PPTX는 10장을 유지하며 실제 렌더링과 오버플로 검사를 통과한다.
