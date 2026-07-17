import type { ProviderSnapshot } from "@/features/analysis/analysis-provider";
import type { ReplayFileMetadata } from "@/features/analysis/analysis-model";

export const REPLAY_SESSION_KEY = "trusted-ceo-replay:v1";

export type ReplaySession = {
  snapshot: ProviderSnapshot;
  selectedFiles: ReplayFileMetadata[];
  humanDraft: string;
};

function copySafeSnapshot(snapshot: ProviderSnapshot): ProviderSnapshot {
  return {
    provider_kind: snapshot.provider_kind,
    display_badge: snapshot.display_badge,
    run_id: snapshot.run_id,
    revision: snapshot.revision,
    workflow_status: snapshot.workflow_status,
    ui_phase: snapshot.ui_phase,
    pending_action: snapshot.pending_action,
    pending_approval_request_id: snapshot.pending_approval_request_id,
    allowed_actions: [...snapshot.allowed_actions],
    latest_event: snapshot.latest_event,
    progress: snapshot.progress,
    result_ref: snapshot.result_ref,
    error: snapshot.error ? { ...snapshot.error } : null,
  };
}

export function saveReplaySession(session: ReplaySession): void {
  const safeSession: ReplaySession = {
    snapshot: copySafeSnapshot(session.snapshot),
    selectedFiles: session.selectedFiles.map(({ name, size, type }) => ({
      name,
      size,
      type,
    })),
    humanDraft: session.humanDraft,
  };
  try {
    sessionStorage.setItem(REPLAY_SESSION_KEY, JSON.stringify(safeSession));
  } catch {
    // Replay remains usable when storage is blocked or full.
  }
}

export function loadReplaySession(): ReplaySession | null {
  try {
    const serialized = sessionStorage.getItem(REPLAY_SESSION_KEY);
    if (!serialized) {
      return null;
    }
    const candidate = JSON.parse(serialized) as ReplaySession;
    if (
      candidate.snapshot?.provider_kind !== "replay" ||
      !Array.isArray(candidate.selectedFiles) ||
      typeof candidate.humanDraft !== "string"
    ) {
      return null;
    }
    return {
      snapshot: copySafeSnapshot(candidate.snapshot),
      selectedFiles: candidate.selectedFiles.map(({ name, size, type }) => ({
        name,
        size,
        type,
      })),
      humanDraft: candidate.humanDraft,
    };
  } catch {
    return null;
  }
}
