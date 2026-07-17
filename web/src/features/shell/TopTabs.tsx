import Link from "next/link";

import { KOREAN_LABELS } from "@/features/shell/labels.ko";

type TopTabsProps = {
  activePath: "/analysis" | "/report";
};

const tabs = [
  { href: "/analysis", label: KOREAN_LABELS.analysisTab },
  { href: "/report", label: KOREAN_LABELS.reportTab },
] as const;

export function TopTabs({ activePath }: TopTabsProps) {
  return (
    <nav aria-label="주요 화면" className="top-tabs">
      {tabs.map((tab) => {
        const isActive = tab.href === activePath;

        return (
          <Link
            aria-current={isActive ? "page" : undefined}
            className="top-tab"
            data-active={isActive}
            href={tab.href}
            key={tab.href}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
