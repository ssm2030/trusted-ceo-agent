"use client";

import { useEffect, useState } from "react";

import type {
  AnalysisProvider,
  HitlDecision,
  ProviderSnapshot,
} from "@/features/analysis/analysis-provider";
import {
  getWorkflowStatusLabel,
  type AnalysisUpload,
} from "@/features/analysis/analysis-model";
import { DataUploadCard } from "@/features/analysis/DataUploadCard";
import { HitlDecisionPanel } from "@/features/analysis/HitlDecisionPanel";
import { RemoteAnalysisProvider } from "@/features/analysis/remote-provider";
import { RunDetailsPanel } from "@/features/analysis/RunDetailsPanel";
import { StageRail } from "@/features/analysis/StageRail";
import { RunHeader } from "@/features/shell/RunHeader";

const RUN_STORAGE_KEY = "trusted-ceo-live-run-id";
const RUN_ID_PATTERN = /^run_[A-Za-z0-9_-]{8,200}$/u;

type LiveHealth = Readonly<{
  status: "ok";
  aiReady: boolean;
  model: "gpt-5.6";
}>;

type LiveAnalysisProvider = AnalysisProvider & Readonly<{
  getHealth(): Promise<LiveHealth>;
}>;

type LiveAnalysisCommandCenterProps = Readonly<{
  provider?: LiveAnalysisProvider;
  onNavigate?: (url: string) => void;
}>;

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function LiveAnalysisCommandCenter({
  provider: suppliedProvider,
  onNavigate,
}: LiveAnalysisCommandCenterProps) {
  const [provider] = useState<LiveAnalysisProvider>(
    () => suppliedProvider ?? new RemoteAnalysisProvider(),
  );
  const [health, setHealth] = useState<LiveHealth | null>(null);
  const [snapshot, setSnapshot] = useState<ProviderSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const nextHealth = await provider.getHealth();
        if (!active) return;
        setHealth(nextHealth);
        if (!nextHealth.aiReady) return;
        const stored = window.sessionStorage.getItem(RUN_STORAGE_KEY);
        const next = stored !== null && RUN_ID_PATTERN.test(stored)
          ? await provider.getStatus(stored)
          : await provider.createRun();
        if (!active) return;
        window.sessionStorage.setItem(RUN_STORAGE_KEY, next.run_id);
        setSnapshot(next);
      } catch {
        if (active) {
          setLocalError("로컬 AI 서비스에 연결할 수 없습니다. 실행 상태를 확인해 주세요.");
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [provider]);

  useEffect(() => {
    if (snapshot?.pending_action !== "provider_work") return;
    let active = true;
    void (async () => {
      let delay = 500;
      let current = snapshot;
      while (active && current.pending_action === "provider_work") {
        await wait(delay);
        if (!active) return;
        try {
          current = await provider.getStatus(current.run_id);
          if (!active) return;
          setSnapshot(current);
          delay = Math.min(delay * 2, 2_000);
        } catch {
          if (active) {
            setLocalError("진행 상태를 새로 불러오지 못했습니다. 잠시 후 다시 시도합니다.");
          }
          delay = Math.min(delay * 2, 2_000);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [provider, snapshot]);

  async function perform(
    operation: () => Promise<ProviderSnapshot>,
  ): Promise<ProviderSnapshot | null> {
    if (busy) return null;
    setBusy(true);
    setLocalError(null);
    try {
      const next = await operation();
      setSnapshot(next);
      return next;
    } catch {
      if (snapshot !== null) {
        try {
          setSnapshot(await provider.getStatus(snapshot.run_id));
        } catch {
          // Keep the last verified browser snapshot if canonical refresh also fails.
        }
      }
      setLocalError("요청을 처리하지 못했습니다. 현재 revision을 새로 확인해 주세요.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function handleUploadsSelected(uploads: AnalysisUpload[]) {
    if (snapshot === null) return;
    await perform(() => provider.attachData(
      snapshot.run_id,
      snapshot.revision,
      uploads,
    ));
  }

  async function handleDecision(
    decision: HitlDecision,
    edits: Readonly<Record<string, unknown>>,
    rationale: string | null,
  ) {
    if (snapshot === null) return;
    await perform(() => provider.submitDecision(
      snapshot.run_id,
      snapshot.revision,
      decision,
      edits,
      rationale,
    ));
  }

  async function handleAction(
    action: "continue" | "retry" | "resume" | "stop" | "cancel",
  ) {
    if (snapshot === null) return;
    const operation = {
      continue: provider.startOrContinue.bind(provider),
      retry: provider.retry.bind(provider),
      resume: provider.resume.bind(provider),
      stop: provider.stop.bind(provider),
      cancel: provider.cancel.bind(provider),
    }[action];
    await perform(() => operation(snapshot.run_id, snapshot.revision));
  }

  async function handleOpenReport() {
    if (snapshot === null || busy) return;
    setBusy(true);
    setLocalError(null);
    try {
      const url = await provider.openFinalizedReport(snapshot.run_id);
      if (url === null) throw new Error("report unavailable");
      (onNavigate ?? ((next) => window.location.assign(next)))(url);
    } catch {
      setLocalError("최종 보고서를 검증해 게시하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (
      snapshot === null ||
      busy ||
      !window.confirm("이 실행의 업로드 자료와 중간 산출물을 모두 삭제할까요?")
    ) {
      return;
    }
    setBusy(true);
    setLocalError(null);
    try {
      await provider.deleteRun(snapshot.run_id, snapshot.revision);
      window.sessionStorage.removeItem(RUN_STORAGE_KEY);
      setSnapshot(null);
      setDeleted(true);
    } catch {
      setLocalError("실행 데이터를 삭제하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (localError !== null && health === null) {
    return <p className="service-blocked-state" role="alert">{localError}</p>;
  }
  if (health === null) {
    return <p className="loading-state">로컬 AI 서비스 상태를 확인하고 있습니다.</p>;
  }
  if (!health.aiReady) {
    return (
      <section className="service-blocked-state" role="status">
        <span aria-hidden="true">KEY</span>
        <div>
          <p className="eyebrow">AI 서비스 대기</p>
          <h2>OpenAI API 키가 필요합니다.</h2>
          <p>
            현재 localhost UI와 검증 엔진은 준비됐지만 AI 분석 호출은 비활성화되어
            있습니다. 키 설정은 사용자가 명시적으로 요청할 때만 진행합니다.
          </p>
        </div>
      </section>
    );
  }
  if (deleted) {
    return (
      <section className="service-blocked-state" role="status">
        <span aria-hidden="true">✓</span>
        <div>
          <p className="eyebrow">로컬 정리 완료</p>
          <h2>실행 데이터가 삭제되었습니다.</h2>
          <p>브라우저에 저장된 run ID도 함께 제거했습니다.</p>
        </div>
      </section>
    );
  }
  if (snapshot === null) {
    return <p className="loading-state">새 AI 분석 실행을 준비하고 있습니다.</p>;
  }

  return (
    <div className="analysis-workspace live-analysis-workspace">
      <RunHeader
        badge={snapshot.display_badge}
        revision={snapshot.revision}
        runId={snapshot.run_id}
        status={getWorkflowStatusLabel(snapshot)}
      />
      <div className="live-service-disclosure" role="note">
        <span aria-hidden="true">AI</span>
        <p>
          업로드 자료는 localhost 검증 엔진에서 정규화되고, 검증된 최소 Job만
          OpenAI API로 전송됩니다. AI 초안은 로컬 검증을 통과하기 전에는 공식
          결과가 아닙니다.
        </p>
      </div>
      <div className="command-center-grid">
        <StageRail activePhase={snapshot.ui_phase} />
        <section className="current-work-panel live-work-panel">
          <div className="work-heading">
            <div>
              <p className="eyebrow">현재 작업</p>
              <h2>사람이 결정권을 갖는 분석</h2>
            </div>
            <span className="phase-chip">단계 {snapshot.ui_phase} / 7</span>
          </div>
          <div className="status-overview">
            <div>
              <span className="pulse-dot" aria-hidden="true" />
              <p>{getWorkflowStatusLabel(snapshot)}</p>
            </div>
            <strong>{snapshot.progress}%</strong>
          </div>
          <div
            aria-label={`진행률 ${snapshot.progress}%`}
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={snapshot.progress}
            className="progress-track"
            role="progressbar"
          >
            <span style={{ width: `${snapshot.progress}%` }} />
          </div>
          <div className="work-body">
            {snapshot.hitl_card ? (
              <HitlDecisionPanel
                key={snapshot.hitl_card.request_id}
                busy={busy}
                card={snapshot.hitl_card}
                onDecision={handleDecision}
              />
            ) : null}
            {snapshot.pending_action === "provider_work" ? (
              <div className="provider-work live-provider-work">
                <p>{snapshot.latest_event}</p>
                <button
                  className="primary-action"
                  disabled={busy}
                  onClick={() => void handleAction("continue")}
                  type="button"
                >
                  분석 계속
                </button>
              </div>
            ) : null}
            {snapshot.pending_action === "retry" ? (
              <button className="primary-action" disabled={busy} onClick={() => void handleAction("retry")} type="button">
                실패 단계 다시 시도
              </button>
            ) : null}
            {snapshot.pending_action === "resume" ? (
              <button className="primary-action" disabled={busy} onClick={() => void handleAction("resume")} type="button">
                체크포인트에서 재개
              </button>
            ) : null}
            {snapshot.pending_action === "terminal" && snapshot.workflow_status === "finalized" ? (
              <div className="terminal-actions">
                <button className="primary-action" disabled={busy} onClick={() => void handleOpenReport()} type="button">
                  최종 보고서 열기
                </button>
                <button className="danger-action" disabled={busy} onClick={() => void handleDelete()} type="button">
                  실행 데이터 삭제
                </button>
              </div>
            ) : null}
            {snapshot.error ? (
              <p className="inline-error" role="alert">{snapshot.error.message}</p>
            ) : null}
            {localError ? (
              <p className="inline-error" role="alert">{localError}</p>
            ) : null}
          </div>
        </section>
        <aside className="analysis-side-column">
          <DataUploadCard
            disabled={busy || !snapshot.allowed_actions.includes('attach_data')}
            files={snapshot.uploaded_files}
            mode="service"
            onUploadsSelected={handleUploadsSelected}
          />
          <RunDetailsPanel snapshot={snapshot} />
        </aside>
      </div>
    </div>
  );
}
