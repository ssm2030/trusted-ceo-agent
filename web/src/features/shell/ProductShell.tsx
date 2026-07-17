import type { ReactNode } from "react";

import { TopTabs } from "@/features/shell/TopTabs";

type ProductShellProps = {
  activePath: "/analysis" | "/report";
  children: ReactNode;
  runHeader?: ReactNode;
};

export function ProductShell({
  activePath,
  children,
  runHeader,
}: ProductShellProps) {
  return (
    <div className="product-shell">
      <header className="product-masthead">
        <div className="brand-lockup">
          <span aria-hidden="true" className="brand-mark">
            T
          </span>
          <div>
            <p className="brand-kicker">신뢰 기반 의사결정 운영</p>
            <p className="brand-title">Trusted CEO Agent</p>
          </div>
        </div>
        <p className="product-boundary">
          플러그인이 분석과 신뢰의 정본입니다
        </p>
      </header>
      <div className="shell-control-band">
        <TopTabs activePath={activePath} />
        {runHeader}
      </div>
      <main id="main-content">{children}</main>
    </div>
  );
}
