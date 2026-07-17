import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import type { ResultAnswerV1 } from "../../../contracts/web-report/v1/generated/types";
import { makeClientReportPayload } from "../../src/features/report/__tests__/report-fixture";

type ConversationKey = {
  revision: number;
  runId: string;
  scopeInstanceId: string;
  scopeKind: string;
};

type SubmittedQuestion = {
  clientRequestId: string;
  consentVersion: string;
  issueId: string | null;
  question: string;
  revision: number;
  runId: string;
  scopeInstanceId: string;
  scopeKind: string;
};

function keyOf(key: ConversationKey): string {
  return [
    key.runId,
    String(key.revision),
    key.scopeKind,
    key.scopeInstanceId,
  ].join("\u001f");
}

async function installQuestionRoutes(page: Page) {
  const payload = makeClientReportPayload();
  const runId = payload.report.run.run_id;
  const revision = payload.report.run.revision;
  const submitted: SubmittedQuestion[] = [];
  const conversationReads: ConversationKey[] = [];
  const conversations = new Map<string, unknown[]>();
  const answer: ResultAnswerV1 = {
    answer_version: "1.0.0",
    job_id: "job_e2e_evidence",
    run_id: runId,
    revision,
    scope: {
      scope_kind: "evidence",
      scope_instance_id: "evidence_main",
      start_refs: ["evidence_main"],
      issue_id: "issue_main",
    },
    validation: {
      schema_valid: true,
      references_valid: true,
      values_valid: true,
      semantic_entailment_verified: false,
      label_ko: "스키마·참조 검증 통과",
    },
    answer_blocks: [
      {
        block_id: "answer_e2e_1",
        support_status: "supported",
        text: "검증된 근거에서 승인된 관찰값을 확인할 수 있습니다.",
        resolved_values: [
          {
            value_ref: "fact_main",
            display_text: "100",
          },
        ],
        claim_refs: ["cause_main"],
        evidence_link_ids: ["evidence_main"],
        source_refs: ["source_main"],
      },
    ],
  };

  await page.addInitScript(() => {
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: undefined,
    });
  });

  await page.route("**/api/report/session", async (route) => {
    await route.fulfill({
      json: { csrfToken: "csrf_e2e" },
      status: 200,
    });
  });
  await page.route("**/api/report/current", async (route) => {
    await route.fulfill({ json: payload, status: 200 });
  });
  await page.route(
    "**/api/report/source-previews/preview_main",
    async (route) => {
      await route.fulfill({
        json: {
          preview_ref: "preview_main",
          source_ref: "source_main",
          access_policy: "permitted",
          truncated: false,
          masking_status: "none",
          column_labels: ["항목", "값"],
          rows: [["관찰값", "100"]],
          locator_summary: "원장 자료 1행",
        },
        status: 200,
      });
    },
  );
  await page.route("**/api/questions/capability", async (route) => {
    await route.fulfill({
      json: {
        capability: {
          companyDataEnabled: false,
          disclosureVersion: "qa-remote-processing-v1",
          modeLabelKo: "POC 제한 모드",
          pocOnly: true,
          reasonCode: "POC_ONLY",
          textQuestionEnabled: true,
        },
        disclosuresKo: [
          "질문용 근거 묶음이 로그인된 Codex를 통해 OpenAI 서비스로 전송됩니다.",
          "답변은 플러그인 검증을 통과한 뒤에만 표시됩니다.",
        ],
      },
      status: 200,
    });
  });
  await page.route("**/api/conversations?*", async (route) => {
    const url = new URL(route.request().url());
    const key: ConversationKey = {
      revision: Number(url.searchParams.get("revision")),
      runId: url.searchParams.get("runId") ?? "",
      scopeInstanceId: url.searchParams.get("scopeInstanceId") ?? "",
      scopeKind: url.searchParams.get("scopeKind") ?? "",
    };
    conversationReads.push(key);
    await route.fulfill({
      json: {
        key,
        records: conversations.get(keyOf(key)) ?? [],
      },
      status: 200,
    });
  });
  await page.route("**/api/questions/request_evidence", async (route) => {
    await route.fulfill({
      json: {
        request: {
          answer,
          clientRequestId: "client_e2e",
          errorCode: null,
          modelDraft: "검증 전 모델 초안 노출 금지",
          queuePosition: null,
          requestId: "request_evidence",
          scopeSuggestions: [],
          state: "completed",
        },
      },
      status: 200,
    });
  });
  await page.route("**/api/questions", async (route) => {
    const body = route.request().postDataJSON() as SubmittedQuestion;
    submitted.push(body);
    const key: ConversationKey = {
      revision: body.revision,
      runId: body.runId,
      scopeInstanceId: body.scopeInstanceId,
      scopeKind: body.scopeKind,
    };
    conversations.set(keyOf(key), [
      {
        createdAt: "2026-07-17T00:00:00.000Z",
        key,
        question: body.question,
        recordId: "record_question_e2e",
        recordVersion: "1.0.0",
        type: "question_submitted",
      },
      {
        answer,
        createdAt: "2026-07-17T00:00:01.000Z",
        key,
        recordId: "record_answer_e2e",
        recordVersion: "1.0.0",
        requestId: "request_evidence",
        type: "answer_verified",
      },
    ]);
    await route.fulfill({
      json: {
        request: {
          answer: null,
          clientRequestId: body.clientRequestId,
          errorCode: null,
          queuePosition: null,
          requestId: "request_evidence",
          scopeSuggestions: [],
          state: "queued",
        },
      },
      status: 202,
    });
  });

  return { conversationReads, revision, runId, submitted };
}

test("질문 drawer가 검증 답변과 범위별 대화를 안전하게 유지한다", async ({
  page,
}) => {
  const harness = await installQuestionRoutes(page);
  await page.goto("/report");
  await expect(
    page.getByRole("heading", { name: "결과 리포트" }),
  ).toBeVisible();

  const launcher = page.getByRole("button", {
    name: "결과에 질문하기",
  });
  const launcherBox = await launcher.boundingBox();
  expect(launcherBox?.width).toBe(52);
  expect(launcherBox?.height).toBe(52);

  await page.getByRole("button", {
    name: "2026년 5월 근거 보기",
  }).click();
  await launcher.focus();
  await expect(launcher).toBeFocused();
  await page.keyboard.press("Enter");

  const drawer = page.getByRole("dialog", { name: "결과 질문 창" });
  await expect(drawer).toBeVisible();
  await expect(
    page.getByRole("button", { name: "질문 창 닫기" }),
  ).toBeFocused();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(
    accessibility.violations.filter((violation) => violation.impact === "critical"),
  ).toEqual([]);
  const drawerBox = await drawer.boundingBox();
  const viewport = page.viewportSize();
  expect(drawerBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(drawerBox!.width).toBeLessThanOrEqual(440);
  expect(drawerBox!.width).toBeLessThanOrEqual(viewport!.width * 0.4);
  expect(drawerBox!.height).toBeLessThanOrEqual(viewport!.height * 0.72);

  const composer = page.getByLabel("결과 질문", { exact: true });
  await expect(composer).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "누르고 말하기" }),
  ).toHaveCount(0);
  await composer.fill("이 근거가 무엇을 뜻하나요?");
  await page.getByRole("button", { name: "질문 보내기" }).click();

  await expect(
    page.getByRole("dialog", { name: "원격 처리 동의" }),
  ).toBeVisible();
  expect(harness.submitted).toHaveLength(0);
  await page.getByRole("checkbox", {
    name: "원격 처리 안내를 확인하고 동의합니다",
  }).check();
  await page.getByRole("button", {
    name: "동의하고 질문 보내기",
  }).click();

  await expect(
    page.getByText(
      "검증된 근거에서 승인된 관찰값을 확인할 수 있습니다.",
    ),
  ).toBeVisible();
  await expect(page.getByText("스키마·참조 검증 통과")).toBeVisible();
  await expect(
    page.getByText("검증 전 모델 초안 노출 금지"),
  ).toHaveCount(0);
  expect(harness.submitted).toEqual([
    expect.objectContaining({
      consentVersion: "qa-remote-processing-v1",
      question: "이 근거가 무엇을 뜻하나요?",
      revision: harness.revision,
      runId: harness.runId,
      scopeInstanceId: "evidence_main",
      scopeKind: "evidence",
    }),
  ]);

  await composer.fill("근거 범위 후속 초안");
  await page.getByRole("button", {
    name: "질문 창 닫기",
  }).click();
  await launcher.click();
  await expect(page.getByLabel("결과 질문", { exact: true })).toHaveValue(
    "근거 범위 후속 초안",
  );
  await expect(
    page.getByText(
      "검증된 근거에서 승인된 관찰값을 확인할 수 있습니다.",
    ),
  ).toBeVisible();

  await page.getByRole("button", { name: "질문 창 닫기" }).click();
  await page.getByRole("button", { name: "출처 미리보기" }).click();
  await page.getByRole("button", { name: "출처 미리보기 닫기" }).click();
  await launcher.click();
  await expect(page.getByText("현재 범위: 출처 · source_main")).toBeVisible();
  await expect(page.getByLabel("결과 질문", { exact: true })).toHaveValue("");

  expect(harness.conversationReads).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        revision: harness.revision,
        runId: harness.runId,
        scopeInstanceId: "evidence_main",
        scopeKind: "evidence",
      }),
      expect.objectContaining({
        revision: harness.revision,
        runId: harness.runId,
        scopeInstanceId: "source_main",
        scopeKind: "source",
      }),
    ]),
  );

  await drawer.evaluate(async (element) => {
    await Promise.all(
      element.getAnimations().map(async (animation) => {
        try {
          await animation.finished;
        } catch {
          // A cancelled entrance animation is already settled for layout checks.
        }
      }),
    );
  });

  for (const viewportCase of [
    { height: 900, maxHeightRatio: 0.7, maxWidth: 380, width: 820 },
    { height: 844, maxHeightRatio: 0.85, maxWidth: 390, width: 390 },
  ]) {
    await page.setViewportSize({
      height: viewportCase.height,
      width: viewportCase.width,
    });
    const responsiveBox = await drawer.boundingBox();
    expect(responsiveBox).not.toBeNull();
    expect(responsiveBox!.x).toBeGreaterThanOrEqual(0);
    expect(responsiveBox!.y).toBeGreaterThanOrEqual(0);
    expect(responsiveBox!.x + responsiveBox!.width).toBeLessThanOrEqual(
      viewportCase.width,
    );
    expect(responsiveBox!.y + responsiveBox!.height).toBeLessThanOrEqual(
      viewportCase.height,
    );
    expect(responsiveBox!.width).toBeLessThanOrEqual(viewportCase.maxWidth);
    expect(responsiveBox!.height).toBeLessThanOrEqual(
      viewportCase.height * viewportCase.maxHeightRatio,
    );
  }
});
