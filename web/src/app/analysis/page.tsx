import { LiveAnalysisCommandCenter } from "@/features/analysis/LiveAnalysisCommandCenter";
import { ProductShell } from "@/features/shell/ProductShell";

export default function AnalysisPage() {
  return (
    <ProductShell activePath="/analysis">
      <div className="page-intro">
        <div>
          <p className="eyebrow">분석 지휘 화면</p>
          <h1>실시간 AI 분석</h1>
        </div>
        <p>
          자료 업로드, AI 분석, 사람의 승인, 검증된 최종 보고서까지 하나의
          localhost 작업 흐름에서 관리합니다.
        </p>
      </div>
      <LiveAnalysisCommandCenter />
    </ProductShell>
  );
}