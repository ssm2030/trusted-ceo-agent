"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import { DecisionBrief } from "@/features/report/DecisionBrief";
import { EvidenceWorkbench } from "@/features/report/EvidenceWorkbench";
import { ExpertPackets } from "@/features/report/ExpertPackets";
import type {
  ReportClientPayload,
  ReportScope,
  ReportScopeKind,
  ReportSection,
} from "@/features/report/report-model";
import { ReportSectionNav } from "@/features/report/ReportSectionNav";
import { RevisionChanges } from "@/features/report/RevisionChanges";
import { SourcePreviewDialog } from "@/features/report/SourcePreviewDialog";
import { TrustManifest } from "@/features/report/TrustManifest";
import styles from "@/features/report/ReportWorkspace.module.css";

type ReportWorkspaceProps = {
  onScopeChange?: (scope: ReportScope) => void;
  payload: ReportClientPayload;
};

type PreviewState = {
  previewRef: string;
  sourceName: string;
};

export function ReportWorkspace({
  onScopeChange,
  payload,
}: ReportWorkspaceProps) {
  const { eligibility, report } = payload;
  const issueMap = useMemo(
    () =>
      new Map(
        report.final_result.issues.map((issue) => [issue.issue_id, issue]),
      ),
    [report.final_result.issues],
  );
  const summaryIssues = report.presentation_manifest.ceo_summary_issue_refs
    .slice(0, 3)
    .map((reference) => issueMap.get(reference))
    .filter((issue): issue is Issue => issue !== undefined);
  const fallbackIssue =
    summaryIssues[0] ?? report.final_result.issues[0] ?? null;
  const [activeIssueRef, setActiveIssueRef] = useState(
    fallbackIssue?.issue_id ?? "",
  );
  const [activeSection, setActiveSection] =
    useState<ReportSection>("decision");
  const [activeRef, setActiveRef] = useState<string | null>(
    fallbackIssue?.issue_id ?? null,
  );
  const [activeScopeKind, setActiveScopeKind] =
    useState<ReportScopeKind>("issue");
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);
  const previewTriggerRef = useRef<HTMLElement | null>(null);
  const activeIssue = issueMap.get(activeIssueRef) ?? fallbackIssue;
  const activePackets =
    activeIssue === null
      ? []
      : report.expert_packet_view.filter(
          (packet) => packet.target_issue_ref === activeIssue.issue_id,
        );

  useEffect(() => {
    if (onScopeChange === undefined || activeIssue === null) {
      return;
    }
    onScopeChange({
      activeRef,
      issueId: activeIssue.issue_id,
      scopeInstanceId: activeRef ?? activeIssue.issue_id,
      scopeKind: activeScopeKind,
    });
  }, [activeIssue, activeRef, activeScopeKind, onScopeChange]);

  if (activeIssue === null) {
    return (
      <section className={styles.section}>
        <h2>표시할 결과 문제가 없습니다.</h2>
        <p className={styles.notice}>
          이 묶음에는 플러그인이 제공한 문제 항목이 없습니다.
        </p>
      </section>
    );
  }

  const selectIssue = (issueRef: string) => {
    if (!issueMap.has(issueRef)) {
      return;
    }
    setActiveIssueRef(issueRef);
    setActiveRef(issueRef);
    setActiveScopeKind("issue");
  };
  const selectSection = (section: ReportSection) => {
    setActiveSection(section);
    setActiveRef(
      section === "expert_packets"
        ? (activePackets[0]?.expert_packet_id ?? activeIssue.issue_id)
        : activeIssue.issue_id,
    );
    setActiveScopeKind(
      section === "expert_packets"
        ? "expert_packet"
        : section === "revision_changes"
          ? "revision_diff"
          : section === "trust"
            ? "section"
            : "issue",
    );
  };
  const selectEvidence = (evidenceLinkId: string, issueRef: string) => {
    selectIssue(issueRef);
    setActiveRef(evidenceLinkId);
    setActiveScopeKind("evidence");
    setActiveSection("evidence");
  };
  const badgeClass =
    eligibility.mode === "trusted_final"
      ? styles.statusTrusted
      : eligibility.mode === "poc_fixture"
        ? styles.statusPoc
        : styles.statusUnverified;

  return (
    <div className={styles.workspace}>
      <header className={styles.reportHeader}>
        <div>
          <p className={styles.eyebrow}>검증된 의사결정 기록</p>
          <h1 className={styles.reportTitle}>결정은 짧게, 근거는 깊게.</h1>
          <p className={styles.reportLead}>
            이 화면은 분석 정본이 아닙니다. 플러그인이 제공하고 검증기가
            판정한 결과 표현만 탐색할 수 있습니다.
          </p>
        </div>
        <div className={styles.statusStrip}>
          <span className={`${styles.statusBadge} ${badgeClass}`}>
            {eligibility.label}
          </span>
          <dl className={styles.reportMeta}>
            <dt>실행 ID</dt>
            <dd>{report.run.run_id}</dd>
            <dt>리비전</dt>
            <dd>{report.run.revision}</dd>
            <dt>묶음 버전</dt>
            <dd>{report.bundle_version}</dd>
          </dl>
        </div>
      </header>

      <ReportSectionNav
        activeSection={activeSection}
        expertPacketCount={activePackets.length}
        onSectionSelect={selectSection}
      />

      {activeSection === "decision" ? (
        <DecisionBrief
          activeIssueRef={activeIssue.issue_id}
          charts={report.presentation_manifest.chart_specs}
          graph={report.presentation_manifest.issue_graph}
          issues={summaryIssues}
          metricCards={report.presentation_manifest.metric_cards}
          onEvidenceSelect={selectEvidence}
          onIssueSelect={selectIssue}
        />
      ) : activeSection === "evidence" ? (
        <EvidenceWorkbench
          activeEvidenceRef={activeRef}
          activeIssue={activeIssue}
          onPreviewRequest={({ previewRef, sourceRef, sourceName, trigger }) => {
            previewTriggerRef.current = trigger;
            setPreviewState({ previewRef, sourceName });
            setActiveRef(sourceRef);
            setActiveScopeKind("source");
          }}
          report={report}
        />
      ) : activeSection === "trust" ? (
        <TrustManifest
          activeIssue={activeIssue}
          eligibility={eligibility}
          report={report}
        />
      ) : activeSection === "expert_packets" ? (
        <ExpertPackets activeIssue={activeIssue} packets={activePackets} />
      ) : (
        <RevisionChanges
          activeIssueTitle={activeIssue.title_template}
          revisionView={report.revision_view}
        />
      )}

      <SourcePreviewDialog
        onClose={() => setPreviewState(null)}
        open={previewState !== null}
        previewRef={previewState?.previewRef ?? null}
        returnFocusRef={previewTriggerRef}
        sourceName={previewState?.sourceName ?? "출처"}
      />
    </div>
  );
}
