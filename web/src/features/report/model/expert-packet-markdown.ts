import type { ExpertPacketViewItemV1 } from "../../../../../contracts/web-report/v1/generated/types";

function list(items: string[]): string {
  return items.length === 0
    ? "- 제공되지 않음"
    : items.map((item) => `- ${item}`).join("\n");
}

export function renderExpertPacketMarkdown(
  packet: ExpertPacketViewItemV1,
): string {
  return [
    `# ${packet.profession} 전문가 검토 패킷`,
    "",
    `- 실행 ID: ${packet.run_id}`,
    `- 리비전: ${packet.revision}`,
    `- 대상 문제: ${packet.target_issue_ref}`,
    `- 패킷 해시: ${packet.packet_hash}`,
    "",
    "## 검토 질문",
    "",
    packet.review_question,
    "",
    "## 사실 참조",
    "",
    list(packet.fact_refs),
    "",
    "## 근거 참조",
    "",
    list(packet.evidence_link_ids),
    "",
    "## 미해결 불확실성",
    "",
    list(packet.unresolved_uncertainties),
    "",
    "## 필요한 문서",
    "",
    list(packet.required_document_refs),
    "",
    "## 결론 금지 범위",
    "",
    list(packet.forbidden_conclusions),
    "",
  ].join("\n");
}
