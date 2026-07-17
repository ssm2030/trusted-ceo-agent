import path from "node:path";

import type {
  QuestionRunContext,
} from "@/lib/server/questions/types";

type Listener = (
  next: QuestionRunContext | null,
) => void;

let current: QuestionRunContext | null = null;
const listeners = new Set<Listener>();

function validated(
  value: QuestionRunContext,
): QuestionRunContext {
  if (
    typeof value.registrationId !== "string" ||
    value.registrationId.length === 0 ||
    !path.isAbsolute(value.artifactRoot) ||
    typeof value.runId !== "string" ||
    !Number.isInteger(value.revision) ||
    value.revision < 1 ||
    (value.viewerMode !== "trusted_final" &&
      value.viewerMode !== "poc_fixture") ||
    (value.privacyClassification !== "poc_deidentified" &&
      value.privacyClassification !== "company_restricted") ||
    !/^[0-9a-f]{64}$/.test(value.bundleHash)
  ) {
    throw new Error(
      "question context must come from a validated registered report",
    );
  }
  if (
    value.viewerMode === "poc_fixture" &&
    value.privacyClassification !== "poc_deidentified"
  ) {
    throw new Error(
      "POC fixture question context must be deidentified",
    );
  }
  return Object.freeze({ ...value });
}

function publish(next: QuestionRunContext | null): void {
  current = next;
  for (const listener of listeners) {
    listener(next);
  }
}

export function setCurrentQuestionRunContext(
  value: QuestionRunContext,
): void {
  publish(validated(value));
}

export function clearCurrentQuestionRunContext(): void {
  if (current !== null) {
    publish(null);
  }
}

export function getCurrentQuestionRunContext(): QuestionRunContext | null {
  return current;
}

export function onQuestionRunContextChanged(
  listener: Listener,
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
