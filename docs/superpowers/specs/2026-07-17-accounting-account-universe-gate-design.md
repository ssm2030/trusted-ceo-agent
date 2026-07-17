# Accounting Account Universe Gate 설계

- 상태: 회계 Coverage Matrix의 필수 보완 설계
- 상위 문서: `2026-07-17-accounting-review-coverage-matrix-design.md`
- 적용대상: 모든 회계 분석 Run

## 0. 목적

Accounting Core가 모든 계정의 무결성을 검사해도 모든 계정의 전문 회계처리를 검토하는 것은 아니다. 이 Gate는 초기 네 Pack 밖의 중요 계정과 공시영역을 숨기지 못하게 한다.

## 1. 상태

모든 중요 계정·공시영역은 다음 중 정확히 하나의 상태를 가진다.

- `deep_reviewed`: 검증된 전문 Pack으로 심화검토 완료
- `core_screened`: 원장·대사·일반 이상검사만 완료
- `pack_required`: 별도 전문 Pack 필요
- `not_assessable`: 데이터·규범·전문역량 부족
- `not_applicable`: 거래·잔액이 존재하지 않음
- `excluded_by_approved_scope`: 사람이 명시적으로 제외

빈 상태는 허용하지 않는다.

## 2. 최초 네 Pack의 직접 범위 밖 후보

- 리스
- 유형자산
- 프로젝트 외 무형자산
- 법인세·이연법인세
- 종업원급여·퇴직급여
- 주식기준보상
- 외화·파생상품
- 지분·복잡한 금융부채
- 연결·관계기업
- 사업결합
- 프로젝트 밖의 일반 충당부채·우발사항
- 정부보조금
- 공정가치 측정

거래와 잔액이 중요하면 Router는 `pack_required` 또는 `expert_review_required`를 만든다.

## 3. 입력

- 계정과목표
- 시산표
- 주석 mapping
- 전기 재무제표
- 회사 회계정책
- 거래 유형
- 법인·연결구조
- 중요성 입력
- 질적 중요성 Trigger

## 4. 절차

1. 모든 계정을 계정 Family로 mapping한다.
2. 금액·거래량·변동·질적 위험을 계산한다.
3. 현재 Knowledge Release의 전문 Pack Coverage와 비교한다.
4. `deep_reviewed`와 `core_screened`를 구분한다.
5. 데이터가 있지만 Pack이 없으면 `pack_required`로 둔다.
6. 데이터 자체가 없으면 `not_assessable`로 둔다.
7. `excluded_by_approved_scope`에는 승인자·사유·기간을 요구한다.
8. 최종 보고 전 빈 상태와 중요 `core_screened` 영역을 차단한다.

## 5. 금지 표현

- Core screening만 수행한 영역을 “회계적으로 이상 없음”으로 표시
- 전문 Pack이 없는 영역을 자동으로 중요하지 않다고 판단
- 금액이 작다는 이유만으로 법적·세무·부정 위험을 제거
- 데이터 부재를 거래 부재로 해석

## 6. 출력

| Account family | Amount | Risk | State | Pack | Missing capability | Next action |
|---|---:|---|---|---|---|---|
| revenue | value ref | high | deep_reviewed | revenue | none | review issues |
| leases | value ref | medium | pack_required | none | lease contract | expert pack |
| tax | value ref | high | not_assessable | none | tax return | tax review |

숫자는 Fact ref로 렌더링하고 자유 텍스트에 하드코딩하지 않는다.

## 7. Finalization Gate

- 중요 계정·공시영역 중 빈 상태 0건
- `core_screened`를 전문검토 완료로 표시한 항목 0건
- 중요 `pack_required`가 최종 보고서 사각지대에 모두 표시
- `excluded_by_approved_scope`에 승인기록 없는 항목 0건
- 세 Cycle Full 표시는 각 Cycle Depth Gate와 별도 판정
- 회사 전체 회계 Full 표시는 전체 중요 Account Family의 전문 Pack 승격 후에만 허용

## 8. HANDOFF

```text
Accounting Core는 전체 계정을 screen하지만 전체 회계주제를 깊게 검토하지 않는다.
모든 중요 계정 Family에 Coverage 상태를 부여하고,
Pack이 없는 영역을 명시적인 전문검토 필요사항으로 남긴다.
```
