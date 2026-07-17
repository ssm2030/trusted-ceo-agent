import { ReplayCommandCenter } from "@/features/analysis/ReplayCommandCenter";
import { ProductShell } from "@/features/shell/ProductShell";

export default function AnalysisPage() {
  return (
    <ProductShell activePath="/analysis">
      <div className="page-intro">
        <div>
          <p className="eyebrow">ANALYSIS COMMAND CENTER</p>
          <h1>분석 작업</h1>
        </div>
        <p>
          준비된 흐름에서 자료, 사람 확인, 터미널 승인 경계를 한눈에
          확인합니다.
        </p>
      </div>
      <ReplayCommandCenter />
    </ProductShell>
  );
}
