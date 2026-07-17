import validTrusted from "../../../../../contracts/web-report/v1/fixtures/valid-trusted.json";
import type {
  ChartSpecV1,
  ExpertPacketViewItemV1,
  Issue,
  WebReportBundleV1,
} from "../../../../../contracts/web-report/v1/generated/types";

import {
  sanitizeReportBundle,
  type ReportClientPayload,
} from "@/features/report/report-model";

const SECONDARY_ISSUE: Issue = {
  issue_id: "issue_secondary",
  title_template: "현금 회수 지연",
  primary_grade: "Monitor",
  secondary_flags: ["collection_watch"],
  why_it_matters_template:
    "승인된 회수 관찰값을 계속 확인해야 운전자금 대응 시점을 놓치지 않습니다.",
  value_refs: ["fact_main"],
  evidence_link_ids: ["evidence_secondary"],
  cause_hypotheses: [{ claim_code: "cause_collection_timing" }],
  counter_hypotheses: [{ claim_code: "counter_seasonality" }],
  unresolved_conflicts: ["conflict_payment_timing"],
  verification_next_steps: ["거래처별 회수 예정일 확인"],
  conditional_response_refs: ["response_collection"],
  expert_review_refs: [],
};

const SUMMARY_CHART: ChartSpecV1 = {
  chart_id: "chart_margin_path",
  title_ko: "승인된 관찰값 흐름",
  description_ko: "플러그인이 제공한 두 시점의 원장 관찰값입니다.",
  chart_kind: "line",
  issue_refs: ["issue_main"],
  fact_refs: ["fact_main"],
  signal_refs: [],
  x_axis_label_ko: "기간",
  y_axis_label_ko: "관찰값",
  unit_code: "count",
  currency_code: null,
  scale: "1",
  display_format: "decimal",
  float_safe: true,
  points: [
    {
      point_id: "point_2026_05",
      x_label: "2026년 5월",
      period_sort_key: "2026-05",
      value_ref: "fact_main",
      fact_id: "fact_main",
      display_value: "92",
      evidence_link_ids: ["evidence_main"],
    },
    {
      point_id: "point_2026_06",
      x_label: "2026년 6월",
      period_sort_key: "2026-06",
      value_ref: "fact_main",
      fact_id: "fact_main",
      display_value: "100",
      evidence_link_ids: ["evidence_main"],
    },
  ],
};

const EXPERT_PACKET: ExpertPacketViewItemV1 = {
  expert_packet_id: "packet_legal_main",
  profession: "법률",
  target_issue_ref: "issue_main",
  fact_refs: ["fact_main"],
  evidence_link_ids: ["evidence_main"],
  source_refs: ["source_main"],
  cause_hypotheses: ["cause_main"],
  counter_hypotheses: [],
  unresolved_uncertainties: ["계약 조항의 적용 범위"],
  required_document_refs: ["document_contract_main"],
  review_question: "현재 계약 조항이 승인된 관찰 사실에 어떤 제한을 두는지 검토해 주세요.",
  forbidden_conclusions: ["법률 위반 여부를 단정하지 않음"],
  source_locators: [
    {
      source_ref: "source_main",
      locator: "원장 자료 1행",
    },
  ],
  run_id: "run_20260717T000000Z_aaaaaaaaaaaaaaaa",
  revision: 3,
  packet_hash: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
};

export function makeClientReportPayload(): ReportClientPayload {
  const bundle = structuredClone(validTrusted) as unknown as WebReportBundleV1;
  const primaryIssue = bundle.final_result.issues[0];
  primaryIssue.title_template = "수익성 점검 필요";
  primaryIssue.why_it_matters_template =
    "승인된 원장 관찰값을 바탕으로 다음 의사결정을 확인해야 합니다.";
  primaryIssue.verification_next_steps = ["비용 구조의 승인 범위를 확인"];
  primaryIssue.expert_review_refs = ["packet_legal_main"];

  bundle.final_result.issues = [primaryIssue, SECONDARY_ISSUE];
  bundle.final_result.cross_issue_relations = [
    {
      relation_id: "relation_margin_collection",
      from_issue_ref: "issue_main",
      to_issue_ref: "issue_secondary",
      relation_type: "observed_together",
    },
  ];
  bundle.final_result.conditional_responses = [
    {
      response_id: "response_collection",
      condition_template: "회수 예정일이 승인 범위를 벗어나면",
      direction_template: "현금 보전 대응안을 다시 확인합니다.",
    },
  ];
  bundle.final_result.expert_review_packets = [
    {
      expert_packet_id: "packet_legal_main",
      profession: "법률",
      question_template: EXPERT_PACKET.review_question,
      forbidden_conclusions: EXPERT_PACKET.forbidden_conclusions,
    },
  ];

  const secondaryEvidence = structuredClone(bundle.evidence_view.evidence_links[0]);
  secondaryEvidence.evidence_link_id = "evidence_secondary";
  secondaryEvidence.target_ref = "issue_secondary";
  secondaryEvidence.rationale_template =
    "승인된 관찰값이 회수 지연 문제를 뒷받침합니다.";
  bundle.evidence_view.evidence_links.push(secondaryEvidence);
  bundle.evidence_view.issue_claim_closure.push({
    issue_ref: "issue_secondary",
    claim_refs: ["cause_collection_timing", "counter_seasonality"],
    evidence_link_ids: ["evidence_secondary"],
    fact_refs: ["fact_main"],
    signal_refs: [],
    source_refs: ["source_main"],
    expert_packet_refs: [],
  });

  bundle.presentation_manifest.ceo_summary_issue_refs = [
    "issue_main",
    "issue_secondary",
  ];
  bundle.presentation_manifest.metric_cards = [
    bundle.presentation_manifest.metric_cards[0],
    {
      metric_card_id: "metric_collection",
      issue_ref: "issue_secondary",
      label_ko: "회수 관찰값",
      value_ref: "fact_main",
      display_value: "100",
      unit_code: "count",
      currency_code: null,
    },
  ];
  bundle.presentation_manifest.chart_specs = [SUMMARY_CHART];
  bundle.presentation_manifest.issue_graph = {
    nodes: [
      {
        issue_ref: "issue_main",
        label_ko: "수익성 점검 필요",
        grade: "Decision Required",
      },
      {
        issue_ref: "issue_secondary",
        label_ko: "현금 회수 지연",
        grade: "Monitor",
      },
    ],
    edges: [
      {
        relation_id: "relation_margin_collection",
        from_issue_ref: "issue_main",
        to_issue_ref: "issue_secondary",
        relation_type: "observed_together",
      },
    ],
  };

  bundle.source_view[0].official_url = "https://official.example/source";
  bundle.expert_packet_view = [EXPERT_PACKET];
  bundle.revision_view = {
    available: true,
    unavailable_reason: null,
    base_revision: 2,
    compare_revision: 3,
    change_categories: ["evidence", "grade"],
    added_refs: ["issue_secondary"],
    changed_refs: ["issue_main"],
    removed_refs: [],
    invalidated_approval_refs: [],
    previous_semantic_fingerprint:
      "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    current_semantic_fingerprint:
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    display_message_ko: "플러그인이 제공한 리비전 변경 기록입니다.",
  };

  return sanitizeReportBundle(bundle, {
    mode: "trusted_final",
    label: "승인·검증된 실행본",
    trusted: true,
    questionsAllowed: true,
  });
}
