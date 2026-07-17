import type { EvidenceTableRow } from "@/features/report/model/chart-option";

import styles from "@/features/report/ReportWorkspace.module.css";

type EvidenceFallbackTableProps = {
  onEvidenceSelect: (evidenceLinkId: string) => void;
  reason: string;
  rows: EvidenceTableRow[];
};

export function EvidenceFallbackTable({
  onEvidenceSelect,
  reason,
  rows,
}: EvidenceFallbackTableProps) {
  return (
    <div>
      <p className={styles.tableFallback}>{reason}</p>
      <table className={styles.evidenceTable}>
        <thead>
          <tr>
            <th scope="col">항목</th>
            <th scope="col">플러그인 표시값</th>
            <th scope="col">근거</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.factId}:${row.label}`}>
              <th scope="row">{row.label}</th>
              <td>{row.formattedValue}</td>
              <td>
                <button
                  className={styles.pointButton}
                  onClick={() => onEvidenceSelect(row.evidenceLinkId)}
                  type="button"
                >
                  근거 보기
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
