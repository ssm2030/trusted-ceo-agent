"use client";

import { useRef } from "react";

import type { Issue } from "../../../../contracts/web-report/v1/generated/types";

import { AnalysisConclusionPanel } from "@/features/report/AnalysisConclusionPanel";
import {
  EvidenceWorkbench,
  type PreviewRequest,
} from "@/features/report/EvidenceWorkbench";
import type { ClientReportBundle } from "@/features/report/report-model";
import { VerificationPlanPanel } from "@/features/report/VerificationPlanPanel";
import styles from "@/features/report/ReportWorkspace.module.css";

export type ConsultantAnalysisSection =
  | "analysis"
  | "evidence"
  | "verification";

type ConsultantAnalysisViewProps = {
  activeEvidenceRef: string | null;
  activeIssue: Issue;
  activeView: ConsultantAnalysisSection;
  onPreviewRequest: (request: PreviewRequest) => void;
  onViewSelect: (view: ConsultantAnalysisSection) => void;
  report: ClientReportBundle;
};

const CONSULTANT_SECTIONS = [
  { id: "analysis", label: "분석 결론" },
  { id: "evidence", label: "근거·출처" },
  { id: "verification", label: "검증 계획" },
] as const satisfies ReadonlyArray<{
  id: ConsultantAnalysisSection;
  label: string;
}>;

export function ConsultantAnalysisView({
  activeEvidenceRef,
  activeIssue,
  activeView,
  onPreviewRequest,
  onViewSelect,
  report,
}: ConsultantAnalysisViewProps) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeIndex = CONSULTANT_SECTIONS.findIndex(
    (section) => section.id === activeView,
  );

  const selectByIndex = (index: number) => {
    const section = CONSULTANT_SECTIONS[index];
    if (section === undefined) {
      return;
    }
    onViewSelect(section.id);
    tabRefs.current[index]?.focus();
  };

  const handleTabKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % CONSULTANT_SECTIONS.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex =
        (index - 1 + CONSULTANT_SECTIONS.length) %
        CONSULTANT_SECTIONS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = CONSULTANT_SECTIONS.length - 1;
    }

    if (nextIndex === null) {
      return;
    }
    event.preventDefault();
    selectByIndex(nextIndex);
  };

  return (
    <section
      aria-labelledby="consultant-analysis-title"
      className={styles.section}
    >
      <header className={styles.sectionHeader}>
        <div>
          <p className={styles.sectionKicker}>컨설턴트 분석 작업대</p>
          <h2 className={styles.sectionTitle} id="consultant-analysis-title">
            {activeIssue.title_template} 분석 검토
          </h2>
          <p className={styles.sectionDescription}>
            플러그인이 저장한 결론, 근거와 검증 계획을 같은 문제 범위에서
            살펴봅니다.
          </p>
        </div>
        <span className={styles.scopeBand}>
          현재 범위: {activeIssue.title_template}
        </span>
      </header>

      <div
        aria-label="컨설턴트 분석 보기"
        className={styles.analysisTabs}
        role="tablist"
      >
        {CONSULTANT_SECTIONS.map((section, index) => {
          const selected = index === activeIndex;
          return (
            <button
              aria-controls={`consultant-panel-${section.id}`}
              aria-selected={selected}
              className={`${styles.analysisTab} ${
                selected ? styles.analysisTabActive : ""
              }`}
              id={`consultant-tab-${section.id}`}
              key={section.id}
              onClick={() => onViewSelect(section.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              role="tab"
              tabIndex={selected ? 0 : -1}
              type="button"
            >
              {section.label}
            </button>
          );
        })}
      </div>

      <div
        aria-labelledby={`consultant-tab-${activeView}`}
        className={styles.analysisTabPanel}
        id={`consultant-panel-${activeView}`}
        role="tabpanel"
        tabIndex={0}
      >
        {activeView === "analysis" ? (
          <AnalysisConclusionPanel activeIssue={activeIssue} report={report} />
        ) : activeView === "evidence" ? (
          <EvidenceWorkbench
            activeEvidenceRef={activeEvidenceRef}
            activeIssue={activeIssue}
            onPreviewRequest={onPreviewRequest}
            report={report}
          />
        ) : (
          <VerificationPlanPanel activeIssue={activeIssue} report={report} />
        )}
      </div>
    </section>
  );
}
