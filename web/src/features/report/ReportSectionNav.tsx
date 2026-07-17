import type { ReportSection } from "@/features/report/report-model";
import styles from "@/features/report/ReportWorkspace.module.css";

type ReportSectionNavProps = {
  activeSection: ReportSection;
  expertPacketCount: number;
  onSectionSelect: (section: ReportSection) => void;
};

type NavigationItem = {
  id: ReportSection;
  label: string;
};

export function ReportSectionNav({
  activeSection,
  expertPacketCount,
  onSectionSelect,
}: ReportSectionNavProps) {
  const packetLabel =
    expertPacketCount === 1
      ? "전문가 검토 패킷 1"
      : `전문가 검토 패킷 ${expertPacketCount}`;
  const items: NavigationItem[] = [
    { id: "decision", label: "최고경영자 의사결정 요약" },
    { id: "evidence", label: "컨설턴트 근거 분석" },
    { id: "trust", label: "실행·신뢰 기록" },
    { id: "expert_packets", label: packetLabel },
    { id: "revision_changes", label: "변경 이력" },
  ];

  return (
    <nav aria-label="결과 리포트 화면" className={styles.sectionNav}>
      {items.map((item) => (
        <button
          aria-current={activeSection === item.id ? "page" : undefined}
          className={`${styles.navButton} ${
            activeSection === item.id ? styles.navButtonActive : ""
          }`}
          key={item.id}
          onClick={() => onSectionSelect(item.id)}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
