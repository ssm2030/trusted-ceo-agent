"use client";

import { useEffect, useState } from "react";

import type { ReportClientPayload } from "@/features/report/report-model";
import { ReportImportControl } from "@/features/report/ReportImportControl";
import { ReportWorkspace } from "@/features/report/ReportWorkspace";
import styles from "@/features/report/ReportWorkspace.module.css";

const EMPTY_MESSAGE =
  "웹 리포트 묶음이 필요합니다. 결과 리포트에서 web-report-bundle.json을 가져오세요.";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; payload: ReportClientPayload; csrfToken: string }
  | { kind: "empty"; message: string; csrfToken: string | null };

type SessionResponse = { csrfToken: string };

async function readCurrentReport(): Promise<ReportClientPayload> {
  const response = await fetch("/api/report/current", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(EMPTY_MESSAGE);
  }
  return (await response.json()) as ReportClientPayload;
}

export function ReportLoader() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let csrfToken: string | null = null;
    void fetch("/api/report/session", {
      cache: "no-store",
      method: "POST",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(EMPTY_MESSAGE);
        }
        const session = (await response.json()) as SessionResponse;
        if (typeof session.csrfToken !== "string" || session.csrfToken.length === 0) {
          throw new Error(EMPTY_MESSAGE);
        }
        csrfToken = session.csrfToken;
        let current = await fetch("/api/report/current", {
          cache: "no-store",
          signal: controller.signal,
        });
        if (current.status === 401) {
          const retrySessionResponse = await fetch("/api/report/session", {
            cache: "no-store",
            method: "POST",
            signal: controller.signal,
          });
          if (!retrySessionResponse.ok) {
            throw new Error(EMPTY_MESSAGE);
          }
          const retrySession = (await retrySessionResponse.json()) as SessionResponse;
          if (
            typeof retrySession.csrfToken !== "string" ||
            retrySession.csrfToken.length === 0
          ) {
            throw new Error(EMPTY_MESSAGE);
          }
          csrfToken = retrySession.csrfToken;
          current = await fetch("/api/report/current", {
            cache: "no-store",
            signal: controller.signal,
          });
        }
        if (!current.ok) {
          setState({ kind: "empty", message: EMPTY_MESSAGE, csrfToken });
          return null;
        }
        return (await current.json()) as ReportClientPayload;
      })
      .then((payload) => {
        if (payload !== null && csrfToken !== null) {
          setState({ kind: "ready", payload, csrfToken });
        }
      })
      .catch(() => {
        if (controller.signal.aborted) {
          return;
        }
        setState({
          kind: "empty",
          message: EMPTY_MESSAGE,
          csrfToken,
        });
      });
    return () => controller.abort();
  }, []);

  if (state.kind === "loading") {
    return (
      <section className={styles.section} role="status">
        <h2>저장된 결과를 확인하고 있습니다.</h2>
        <p>로컬 리포트 저장소를 읽는 중입니다.</p>
      </section>
    );
  }

  if (state.kind === "empty") {
    return (
      <>
        <section className={styles.section}>
          <h2>표시할 결과가 없습니다.</h2>
          <p className={styles.notice}>{state.message}</p>
        </section>
        <ReportImportControl
          csrfToken={state.csrfToken}
          hasCurrentReport={false}
          onImported={async () => {
            const payload = await readCurrentReport();
            if (state.csrfToken !== null) {
              setState({ kind: "ready", payload, csrfToken: state.csrfToken });
            }
          }}
        />
      </>
    );
  }

  return (
    <>
      <ReportImportControl
        csrfToken={state.csrfToken}
        hasCurrentReport
        onImported={async () => {
          const payload = await readCurrentReport();
          setState({ kind: "ready", payload, csrfToken: state.csrfToken });
        }}
      />
      <ReportWorkspace payload={state.payload} />
    </>
  );
}
