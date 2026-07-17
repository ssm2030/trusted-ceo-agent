# B2B 서비스업 회계 전문 콘텐츠 Suite Manifest

- 상태: 회계 콘텐츠 설계 묶음의 최종 탐색 Manifest
- 기준일: 2026-07-17
- 최초 대상: 한국 B2B 서비스업, K-IFRS 우선

## 1. 문서 우선순위

이 Manifest는 Suite의 최종 파일 목록을 고정한다. `2026-07-17-accounting-content-suite-index.md`는 요약·탐색용이며, 파일 목록이 다르면 이 Manifest를 따른다.

## 2. 상위 설계

1. `2026-07-17-trusted-ceo-agent-plugin-design.md`
2. `2026-07-17-senior-accountant-review-expansion-design.md`
3. `2026-07-17-professional-reasoning-knowledge-foundry-design.md`

## 3. 필수 회계 콘텐츠 파일

1. `2026-07-17-accounting-review-coverage-matrix-design.md`
2. `2026-07-17-accounting-account-universe-gate-design.md`
3. `2026-07-17-accounting-norm-procedure-seed-catalog.md`
4. `2026-07-17-accounting-core-journal-integrity-pack-design.md`
5. `2026-07-17-contract-revenue-pack-design.md`
6. `2026-07-17-cash-flow-working-capital-pack-design.md`
7. `2026-07-17-project-cost-allocation-pack-design.md`

## 4. 역할

| 파일 | 역할 |
|---|---|
| Coverage Matrix | 공통 주장·데이터·Tier·Cross-cycle |
| Account Universe Gate | 초기 범위 밖 중요 계정 누락 차단 |
| Norm & Procedure Catalog | 실제 provisional 요건·예외·반증·절차 초안 |
| Accounting Core | 원장·시산표·보조원장·분개 |
| Contract & Revenue | 계약·수행의무·수익·계약잔액 |
| Cash & Working Capital | 현금흐름표·현금전환·유동성 |
| Project Cost & Allocation | 원가귀속·배부·WIP·손실계약 |

## 5. 상태

- 설계 콘텐츠: 작성 완료
- 공식 K-IFRS 문단별 grounding: 미수행
- Schema·Card·Component 구현: 미수행
- 합성 Oracle 구현: 미수행
- 전문가 검토·승격: 미수행
- 현재 Authority: `machine_draft`

“설계 콘텐츠 작성 완료”를 “회계사급 런타임 구현 완료”로 표현하지 않는다.

## 6. 구현 완료 Gate

1. 64개 Issue Family가 D1~D12를 충족한다.
2. Norm Seed가 시행 중 K-IFRS 문단 ref와 연결된다.
3. 결정적 Procedure와 계산이 테스트된다.
4. 정상·오류·경계·반증·복합사례가 존재한다.
5. 중요 Account Family 상태 빈칸이 없다.
6. 회계오류와 경영진단이 분리된다.
7. 전문가 검토 전 `Full`이 차단된다.
8. Knowledge Foundry Release로만 Analysis Plane에 배포된다.

## 7. HANDOFF

```text
이 Manifest의 일곱 파일을 하나의 필수 설계 묶음으로 취급한다.
Norm Catalog를 생략하면 Pack ID와 절차만 남아 지식이 다시 얕아진다.
Account Universe Gate를 생략하면 초기 범위 밖 중요 계정이 숨겨진다.
```
