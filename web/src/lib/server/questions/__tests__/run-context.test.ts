// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import {
  clearCurrentQuestionRunContext,
  getCurrentQuestionRunContext,
  onQuestionRunContextChanged,
  setCurrentQuestionRunContext,
} from "@/lib/server/questions/run-context";
import type { QuestionRunContext } from "@/lib/server/questions/types";

const context: QuestionRunContext = {
  registrationId: "representative",
  artifactRoot: "C:\\runs\\representative",
  runId: "run_20260717T010203Z_0123456789abcdef",
  revision: 3,
  viewerMode: "trusted_final",
  privacyClassification: "company_restricted",
  bundleHash: "a".repeat(64),
};

describe("question run context", () => {
  it("publishes only a validated registered context and can clear it", () => {
    clearCurrentQuestionRunContext();
    const listener = vi.fn();
    const unsubscribe = onQuestionRunContextChanged(listener);
    setCurrentQuestionRunContext(context);

    expect(getCurrentQuestionRunContext()).toEqual(context);
    expect(Object.isFrozen(getCurrentQuestionRunContext())).toBe(true);
    expect(listener).toHaveBeenCalledWith(context);

    clearCurrentQuestionRunContext();
    expect(getCurrentQuestionRunContext()).toBeNull();
    unsubscribe();
  });

  it("rejects an unverified viewer mode at the server boundary", () => {
    expect(() =>
      setCurrentQuestionRunContext({
        ...context,
        viewerMode: "unverified_import" as "trusted_final",
      }),
    ).toThrow("registered");
  });
});
