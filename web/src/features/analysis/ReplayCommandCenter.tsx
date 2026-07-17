"use client";

import { useEffect, useState } from "react";

import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import type { ReplayFileMetadata } from "@/features/analysis/analysis-model";
import { getWorkflowStatusLabel } from "@/features/analysis/analysis-model";
import { CurrentWorkPanel } from "@/features/analysis/CurrentWorkPanel";
import { DataUploadCard } from "@/features/analysis/DataUploadCard";
import { ReplayAnalysisProvider } from "@/features/analysis/replay-provider";
import {
  loadReplaySession,
  saveReplaySession,
} from "@/features/analysis/replay-session-store";
import { RunDetailsPanel } from "@/features/analysis/RunDetailsPanel";
import { StageRail } from "@/features/analysis/StageRail";
import { RunHeader } from "@/features/shell/RunHeader";

const REPLAY_DISCLOSURE =
  "저장된 시연 흐름 — 이 화면은 준비된 작업 과정을 재현하며 선택한 파일 내용을 새로 분석하지 않습니다.";

export function ReplayCommandCenter() {
  const [provider] = useState(() => new ReplayAnalysisProvider());

  const [snapshot, setSnapshot] = useState<ProviderSnapshot>(() =>
    provider.peekSnapshot(),
  );
  const [selectedFiles, setSelectedFiles] = useState<ReplayFileMetadata[]>([]);
  const [humanDraft, setHumanDraft] = useState("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      const restored = loadReplaySession();
      if (restored) {
        provider.restoreSnapshot(restored.snapshot);
        setSnapshot(restored.snapshot);
        setSelectedFiles(restored.selectedFiles);
        setHumanDraft(restored.humanDraft);
      }
      setHydrated(true);
    });
  }, [provider]);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    saveReplaySession({ snapshot, selectedFiles, humanDraft });
  }, [humanDraft, hydrated, selectedFiles, snapshot]);

  async function handleFilesSelected(files: File[]) {
    const next = await provider.attachData(
      snapshot.run_id,
      snapshot.revision,
      files,
    );
    setSnapshot(next);
    if (!next.error) {
      setSelectedFiles(
        files.map(({ name, size, type }) => ({ name, size, type })),
      );
    }
  }

  async function handleStartOrContinue() {
    setSnapshot(
      await provider.startOrContinue(snapshot.run_id, snapshot.revision),
    );
  }

  async function handleSubmitHumanResponse() {
    const next = await provider.submitHumanResponse(
      snapshot.run_id,
      snapshot.revision,
      humanDraft,
    );
    setSnapshot(next);
    if (!next.error) {
      setHumanDraft("");
    }
  }

  async function handlePrepareTerminalRequest() {
    setSnapshot(
      await provider.prepareTerminalApprovalRequest(
        snapshot.run_id,
        snapshot.revision,
      ),
    );
  }

  return (
    <div className="analysis-workspace">
      <RunHeader
        badge={snapshot.display_badge}
        revision={snapshot.revision}
        runId={snapshot.run_id}
        status={getWorkflowStatusLabel(snapshot)}
      />
      <div className="replay-disclosure" role="note">
        <span aria-hidden="true">R</span>
        <p>{REPLAY_DISCLOSURE}</p>
      </div>
      <div className="command-center-grid">
        <StageRail activePhase={snapshot.ui_phase} />
        <CurrentWorkPanel
          draft={humanDraft}
          onDraftChange={setHumanDraft}
          onPrepareTerminalRequest={() => void handlePrepareTerminalRequest()}
          onStartOrContinue={() => void handleStartOrContinue()}
          onSubmitHumanResponse={() => void handleSubmitHumanResponse()}
          snapshot={snapshot}
        />
        <aside className="analysis-side-column">
          <DataUploadCard
            files={selectedFiles}
            onFilesSelected={handleFilesSelected}
          />
          <RunDetailsPanel snapshot={snapshot} />
        </aside>
      </div>
    </div>
  );
}
