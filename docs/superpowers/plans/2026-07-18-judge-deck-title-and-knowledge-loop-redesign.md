# Judge Deck Title and Knowledge Loop Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 심사위원용 10장 PPTX의 제목을 제목형 명사구로 통일하고, 10페이지 Knowledge Foundry 화살표를 교차 없는 2행 순환 구조로 재배치한다.

**Architecture:** 기존 artifact-tool 생성 스크립트와 시각 체계는 유지한다. 9개 본문 슬라이드의 `addHeader` 제목 인수만 교체하고, 10페이지의 노드 좌표와 연결 규칙만 국소 수정한 뒤 별도 PPTX로 내보낸다.

**Tech Stack:** JavaScript ES modules, `@oai/artifact-tool`, bundled Node.js, presentation render and overflow QA tools

---

### Task 1: 제목형 명사구로 통일

**Files:**
- Modify: `C:/Users/home/AppData/Local/Temp/codex-presentations/019f6db1-9361-7082-bfc5-97c6dab2a981/trusted-ceo-agent-judge-friendly/tmp/build-deck.mjs`
- Reference: `docs/superpowers/specs/2026-07-18-judge-deck-title-and-knowledge-loop-redesign.md`

- [ ] **Step 1: 현재 문장형 제목이 존재하는지 확인**

Run:

```powershell
rg -n "숨어 있습니다|압축합니다|만듭니다|보여줍니다|따라갑니다|바꿉니다|높아집니다|바꿉니다|승격됩니다" "C:\Users\home\AppData\Local\Temp\codex-presentations\019f6db1-9361-7082-bfc5-97c6dab2a981\trusted-ceo-agent-judge-friendly\tmp\build-deck.mjs"
```

Expected: 슬라이드 2~10의 기존 제목 9개가 검색된다.

- [ ] **Step 2: `addHeader` 제목 인수 9개 교체**

Apply these exact replacements:

```diff
- "데이터는 많지만, 먼저 봐야 할 문제는 숨어 있습니다"
+ "수많은 기업 데이터를 여러 전문 관점으로 검토"

- "사람의 긴 점검 절차를, 검토 가능한 초안으로 압축합니다"
+ "긴 기업 점검 절차를 검토 가능한 초안으로 압축"

- "필요한 질문만 묻고, 답변마다 분석을 더 정확하게 만듭니다"
+ "몇 번의 질문으로 분석 범위와 우선순위 설정"

- "결론보다 먼저, 왜 그렇게 봤는지를 보여줍니다"
+ "제안·근거·출처·반증이 연결된 Finding"

- "결과를 보며 묻고, 답변은 다시 근거를 따라갑니다"
+ "결과에서 근거까지 이어지는 대화형 탐색"

- "회사가 달라도, Adapter와 Pack만 바꿉니다"
+ "회사·업종별 Adapter와 Domain Pack 교체"

- "추론력은 ‘더 길게 답하기’가 아니라, 네 가지를 교차검증할 때 높아집니다"
+ "전문 사고법·규범지식·검증 절차·반증의 교차검증"

- "Trust Kernel이 자유로운 AI를 감사 가능한 분석으로 바꿉니다"
+ "감사 가능한 분석을 만드는 Trust Kernel"

- "피드백은 즉시 학습되지 않고, 검증된 다음 버전으로 승격됩니다"
+ "피드백·회귀테스트·승격의 Knowledge Foundry"
```

- [ ] **Step 3: 제목 교체 정적 검증**

Run:

```powershell
rg -n "숨어 있습니다|압축합니다|만듭니다|보여줍니다|따라갑니다|바꿉니다|높아집니다|승격됩니다" "C:\Users\home\AppData\Local\Temp\codex-presentations\019f6db1-9361-7082-bfc5-97c6dab2a981\trusted-ceo-agent-judge-friendly\tmp\build-deck.mjs"
rg -n "수많은 기업 데이터를 여러 전문 관점으로 검토|피드백·회귀테스트·승격의 Knowledge Foundry" "C:\Users\home\AppData\Local\Temp\codex-presentations\019f6db1-9361-7082-bfc5-97c6dab2a981\trusted-ceo-agent-judge-friendly\tmp\build-deck.mjs"
```

Expected: 첫 번째 명령은 결과가 없고, 두 번째 명령은 슬라이드 2와 10의 새 제목을 출력한다.

### Task 2: Knowledge Foundry 연결 구조 재배치

**Files:**
- Modify: `C:/Users/home/AppData/Local/Temp/codex-presentations/019f6db1-9361-7082-bfc5-97c6dab2a981/trusted-ceo-agent-judge-friendly/tmp/build-deck.mjs:970-1003`

- [ ] **Step 1: 기존 자동 순환 연결 확인**

Run:

```powershell
rg -n -C 8 "const foundryNodes|nodeShapes\\[\\(i \\+ 1\\) % nodeShapes.length\\]|이전 Release로 rollback" "C:\Users\home\AppData\Local\Temp\codex-presentations\019f6db1-9361-7082-bfc5-97c6dab2a981\trusted-ceo-agent-judge-friendly\tmp\build-deck.mjs"
```

Expected: 엇갈린 노드 좌표, modulo 기반 연결 루프와 중앙 rollback 문구가 출력된다.

- [ ] **Step 2: 정렬된 2행 노드와 명시적 순환 경로 구현**

Replace the six-node staggered coordinates, modulo connector loop, and centered rollback text with:

```js
  const foundryNodes = [
    { text: "Feedback\nRecord", x: 614, y: 278, fill: C.white, color: C.body, border: C.line },
    { text: "Patch\nProposal", x: 808, y: 278, fill: C.blueSoft, color: C.blue, border: C.blue },
    { text: "Regression\nTest", x: 1002, y: 278, fill: C.amberSoft, color: "#9A6500", border: C.amber },
    { text: "3단계\n승인", x: 1002, y: 452, fill: C.greenSoft, color: "#087B58", border: C.green },
    { text: "Versioned\nRelease", x: 808, y: 452, fill: C.navy, color: C.white, border: C.navy },
    { text: "다음 Run\n적용", x: 614, y: 452, fill: C.cyanSoft, color: "#087C91", border: C.cyan },
  ];
  const nodeShapes = [];
  for (const n of foundryNodes) {
    const s = addRect(slide, n.x, n.y, 154, 86, n.fill, {
      radius: 18,
      line: { style: "solid", fill: n.border, width: 2 },
      shadow: n.fill === C.navy ? "shadow-md" : undefined,
    });
    labelShape(s, n.text, { fontSize: 18, color: n.color });
    nodeShapes.push(s);
  }

  const mainRoutes = [
    { from: 0, to: 1, fromSide: "right", toSide: "left", color: C.blue },
    { from: 1, to: 2, fromSide: "right", toSide: "left", color: C.blue },
    { from: 2, to: 3, fromSide: "bottom", toSide: "top", color: C.green },
    { from: 3, to: 4, fromSide: "left", toSide: "right", color: C.green },
    { from: 4, to: 5, fromSide: "left", toSide: "right", color: C.green },
    { from: 5, to: 0, fromSide: "top", toSide: "bottom", color: C.blue },
  ];
  for (const route of mainRoutes) {
    connect(slide, nodeShapes[route.from], nodeShapes[route.to], {
      kind: "straight",
      fromSide: route.fromSide,
      toSide: route.toSide,
      color: route.color,
      width: 3,
    });
  }

  connect(slide, nodeShapes[5], nodeShapes[4], {
    kind: "elbow",
    fromSide: "top",
    toSide: "top",
    color: C.red,
    style: "dashed",
    width: 2,
  });
  addText(slide, "성능 악화 시 이전 Release로 rollback", 740, 390, 286, 34, {
    fontSize: 16,
    bold: true,
    color: C.red,
    align: "center",
    valign: "middle",
    fill: C.bg,
    radius: 10,
  });
```

Expected: 주 흐름은 상단 왼쪽에서 오른쪽으로 이동한 뒤 하단 오른쪽에서 왼쪽으로 돌아오며, rollback만 별도의 빨간 점선으로 표시된다.

- [ ] **Step 3: 출력 파일을 별도 개정본으로 변경**

Replace:

```js
const outputPath = "C:/Users/home/Desktop/개인 작업/해커톤/trusted-ceo-agent/outputs/trusted-ceo-agent-judge-friendly-10slides.pptx";
```

with:

```js
const outputPath = "C:/Users/home/Desktop/개인 작업/해커톤/trusted-ceo-agent/outputs/trusted-ceo-agent-judge-friendly-10slides-revised.pptx";
```

### Task 3: 생성 및 시각 검증

**Files:**
- Create: `outputs/trusted-ceo-agent-judge-friendly-10slides-revised.pptx`
- Test: rendered slide PNGs under the retained external presentation workspace

- [ ] **Step 1: PPTX 재생성**

Run from the presentation workspace:

```powershell
& "C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" "build-deck.mjs"
```

Expected: JSON output contains `"slideCount":10` and the revised PPTX path.

- [ ] **Step 2: 실제 PPTX 10장 렌더링**

Run from `C:\Users\home`:

```powershell
& "C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -X utf8 "C:\Users\home\.codex\plugins\cache\openai-primary-runtime\presentations\26.715.12143\skills\presentations\container_tools\render_slides.py" "C:\Users\home\Desktop\개인 작업\해커톤\trusted-ceo-agent\outputs\trusted-ceo-agent-judge-friendly-10slides-revised.pptx" --output_dir "C:\Users\home\AppData\Local\Temp\codex-presentations\019f6db1-9361-7082-bfc5-97c6dab2a981\trusted-ceo-agent-judge-friendly\tmp\qa\revised-render"
```

Expected: `slide-1.png`부터 `slide-10.png`까지 10개 파일이 생성된다.

- [ ] **Step 3: 개별 슬라이드 시각 검사**

Inspect all ten rendered slides at full size. Verify:

```text
Slides 2-10: titles remain on one line and use the approved title phrases.
Slide 10: no connector crosses a node or label.
Slide 10: main loop direction is immediately readable.
Slide 10: rollback path is visually separate from the main loop.
```

- [ ] **Step 4: 오버플로 검사**

Run from `C:\Users\home`:

```powershell
& "C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -X utf8 "C:\Users\home\.codex\plugins\cache\openai-primary-runtime\presentations\26.715.12143\skills\presentations\container_tools\slides_test.py" "C:\Users\home\Desktop\개인 작업\해커톤\trusted-ceo-agent\outputs\trusted-ceo-agent-judge-friendly-10slides-revised.pptx"
```

Expected: `Test passed. No overflow detected.`

- [ ] **Step 5: 최종 파일 메타데이터 확인**

Run:

```powershell
Get-Item "C:\Users\home\Desktop\개인 작업\해커톤\trusted-ceo-agent\outputs\trusted-ceo-agent-judge-friendly-10slides-revised.pptx"
Get-FileHash -Algorithm SHA256 "C:\Users\home\Desktop\개인 작업\해커톤\trusted-ceo-agent\outputs\trusted-ceo-agent-judge-friendly-10slides-revised.pptx"
```

Expected: 파일이 존재하고 크기가 0보다 크며 SHA-256이 출력된다.
