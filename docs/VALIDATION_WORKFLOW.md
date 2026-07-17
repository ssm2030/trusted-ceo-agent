# Trusted CEO Agent validation workflow

## 목적

필수 품질 게이트는 유지하면서 동일 저장소 상태의 중복 검증, 장문 로그 출력,
편집마다 수행하는 전체 회귀를 피한다. CI의 Blocking 검증과 최종 완료 게이트는
축소하지 않는다.

## 2026-07-17 기준 측정

| 검증 범위 | 관측 시간 | 판정 |
|---|---:|---|
| 편집 1회 후 자동 검증 | 0초 | `.codex/hooks.json`과 `.claude/settings.json`은 종료 로그만 저장하며 테스트를 실행하지 않는다. |
| B Human Response focused | 7.775초 | 19/19 통과 |
| L Completion focused | 0.593초 | 6/6 통과 |
| WebReport preview focused | 0.155초 | 4/4 통과 |
| AC-06~16 focused | 0.516초 | 5/5 통과 |
| E Schema cache 적용 subset | 9.499초 | 7/7 통과; 기존 E 전체 9개 45.311초와 범위가 달라 직접 성능비교에는 사용하지 않음 |
| Python Full 기준선 | 101.729초 | 구현 전 기준선 233/233 통과 |
| 동일 상태 중복 검증 | 0회 | 현재 실행 기록에서는 코드·가설 변화 없는 재실행이 없었다. |

Full 회귀가 focused 검증보다 약 13배 이상 오래 걸리는 것이 현재 확인된 주
병목이다. 종료 로그 훅은 검증 병목이 아니므로 유지한다.

동시에 여러 편집 흐름이 patch engine을 호출하면 한 호출이 524.9초 대기한
사례가 확인됐다. 이후에는 편집 흐름을 한 개만 유지하고, 독립 read-only 조사만
병렬화한다. 이 규칙은 구현계획의 Task 분해를 바꾸지 않는다.

## 최종 완료 게이트

| 게이트 | 결과 | 시간 |
|---|---:|---:|
| Python 전체 | 418/418 통과 | 246.852초 |
| Python hidden web-report | 41/41 통과 | 9.161초 |
| Web-report contract 생성·fixture parity | 통과 | 7.740초 |
| Web unit | 135/135 통과 | 34.264초 |
| Web typecheck / lint / build | 모두 통과 | 9.939 / 13.016 / 30.001초 |
| Playwright | 3/3 통과 | 18.092초 |

독립 게이트를 병렬 실행한 성공 경로의 임계 시간은 Python 묶음 256.236초였다.
첫 Web 실행은 테스트 수집 전 Vite 하위 프로세스가 sandbox `spawn EPERM`으로
차단되어, 환경 권한만 바꿔 Web 묶음만 재개했다. 동일 상태·동일 환경의 중복
검증은 0회다. Next build는 통과했지만 dynamic filesystem trace로 프로젝트 전체가
NFT 목록에 포함될 수 있다는 Turbopack 경고 1건이 남았다.

## 로컬 구현 중 검증

1. `rg`로 변경 계약과 직접 관련된 테스트 모듈을 찾고 필요한 구간만 읽는다.
2. 최초 실행은 quiet focused 테스트로 한다.

```powershell
$env:PYTHONPATH=(Resolve-Path 'plugin/trusted-ceo-agent').Path
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest <modules> -q
```

3. 실패했을 때만 실패한 정확한 모듈을 `-v`로 다시 실행한다.
4. 코드나 검증 가설이 바뀌지 않았다면 같은 명령을 다시 실행하지 않는다.
5. 같은 실패가 두 번이면 증거·배제 원인·다음 판별 실험을 짧게 기록하고
   접근을 바꾼다.
6. 문구·주석·예제만 바꾼 경우에는 동작 계약 테스트를 추가 실행하지 않는다.
7. 작업 상태 문서는 의미 있는 수직 단위가 끝나거나 실제 인계가 필요할 때만
   갱신한다.

## 최종 완료 게이트

코드와 동작 설정을 동결한 뒤 다음 검증을 한 번 실행한다. 이후 코드나 동작
설정이 바뀐 경우에만 영향 범위 검증과 필요한 Full 검증을 다시 실행한다.

```powershell
$env:PYTHONPATH=(Resolve-Path 'plugin/trusted-ceo-agent').Path
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests -q
uv run --project plugin/trusted-ceo-agent --frozen --offline --no-sync python -m unittest discover -s tests/unit/web_report -p 'test_*.py' -q
```

웹은 `web` 디렉터리에서 `npm test`, `npm run typecheck`, `npm run build`를 최종
게이트에서 실행한다. 보안·권한·stale revision·idempotency·required-task
finalization 차단·결정성·byte-equivalence 검증은 변경 비용과 무관하게
Blocking으로 유지한다.

## 검증 캐시 경계

현재 핵심 플러그인·테스트·웹 파일 다수가 Git 미추적 상태이므로 Git diff만
사용한 fingerprint 캐시는 변경을 누락할 수 있다. 이 상태에서는 캐시를
사용하지 않는다. 해당 파일들이 추적된 뒤 명령, lockfile, 환경, 전체 입력 파일
content hash를 포함하는 manifest 방식으로만 도입한다.
