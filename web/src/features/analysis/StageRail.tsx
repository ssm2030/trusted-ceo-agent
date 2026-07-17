import { ANALYSIS_PHASES } from "@/features/analysis/analysis-model";

type StageRailProps = {
  activePhase: 1 | 2 | 3 | 4 | 5 | 6 | 7;
};

export function StageRail({ activePhase }: StageRailProps) {
  return (
    <aside className="stage-rail" aria-label="분석 단계">
      <div className="panel-heading">
        <p className="eyebrow">작업 흐름</p>
        <h2>전체 단계</h2>
      </div>
      <ol>
        {ANALYSIS_PHASES.map((phase, index) => {
          const phaseNumber = (index + 1) as StageRailProps["activePhase"];
          const state =
            phaseNumber < activePhase
              ? "complete"
              : phaseNumber === activePhase
                ? "current"
                : "upcoming";

          return (
            <li
              aria-current={state === "current" ? "step" : undefined}
              data-state={state}
              key={phase}
            >
              <span className="stage-number">{String(phaseNumber).padStart(2, "0")}</span>
              <span>{phase}</span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
