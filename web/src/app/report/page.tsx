import { ReportLoader } from "@/features/report/ReportLoader";
import { ProductShell } from "@/features/shell/ProductShell";

export default function ReportPage() {
  return (
    <ProductShell activePath="/report">
      <div className="page-intro">
        <div>
          <p className="eyebrow">의사결정 근거 리포트</p>
          <h1>결과 리포트</h1>
        </div>
        <p>로컬 검증 엔진이 게시한 문제, 근거, 신뢰 기록만 표시합니다.</p>
      </div>
      <ReportLoader />
    </ProductShell>
  );
}
