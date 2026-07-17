/* eslint-disable */
/** Generated from Contract 0. Do not edit by hand. */

/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "idSet".
 */
export type IdSet = string[];
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "idSet".
 */
export type IdSet1 = string[];
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "textSet".
 */
export type TextSet = string[];
/**
 * This interface was referenced by `ResultAnswerDraftV1`'s JSON-Schema
 * via the `definition` "idSet".
 */
export type IdSet2 = string[];
/**
 * @minItems 1
 *
 * This interface was referenced by `ResultAnswerDraftV1`'s JSON-Schema
 * via the `definition` "nonEmptyIdSet".
 */
export type NonEmptyIdSet = [string, ...string[]];
/**
 * @maxItems 0
 *
 * This interface was referenced by `ResultAnswerDraftV1`'s JSON-Schema
 * via the `definition` "emptyIdSet".
 */
export type EmptyIdSet = never[];
/**
 * @minItems 1
 *
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "nonEmptyIdSet".
 */
export type NonEmptyIdSet1 = [string, ...string[]];
/**
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "idSet".
 */
export type IdSet3 = string[];
/**
 * @maxItems 0
 *
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "emptyIdSet".
 */
export type EmptyIdSet1 = never[];

export interface WebReportContractsV1 {
  web_report_bundle: WebReportBundleV1;
  viewer_eligibility_decision: ViewerEligibilityDecisionV1;
  presentation_manifest: PresentationManifestV1;
  result_question_job: ResultQuestionJobV1;
  result_answer_draft: ResultAnswerDraftV1;
  result_answer: ResultAnswerV1;
}
export interface WebReportBundleV1 {
  bundle_version: "1.0.0";
  canonicalization_version: "rfc8785-jcs-1";
  run: Run;
  viewer_eligibility_receipt: Receipt;
  final_result: FinalResult;
  presentation_manifest: PresentationManifestV1;
  evidence_view: EvidenceView;
  /**
   * @maxItems 5000
   */
  source_view: SourceViewItem[];
  /**
   * @maxItems 5000
   */
  source_previews: SourcePreviewV1[];
  official_url_policy: OfficialUrlPolicy;
  trust_view: TrustView;
  /**
   * @maxItems 500
   */
  expert_packet_view: ExpertPacketViewItemV1[];
  revision_view: RevisionViewV1;
  file_manifest: FileManifestItem[];
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  bundle_hash: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "run".
 */
export interface Run {
  run_id: string;
  revision: number;
  workflow_state: "finalized";
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  semantic_fingerprint: string;
  finalization_event_time: string | null;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "receipt".
 */
export interface Receipt {
  receipt_version: "1.0.0";
  claimed_viewer_mode: "trusted_final" | "poc_fixture" | "unverified_import";
  run_id: string;
  approved_revision: number | null;
  finalized_revision: number;
  workflow_state: "finalized";
  snapshot_manifest_hash: string | null;
  final_result_hash: string | null;
  result_artifact_ref: string | null;
  revision_ancestry_hash: string | null;
  validator_version: string;
  completed_checks: IdSet;
  final_approval_summary: FinalApprovalSummary;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "finalApprovalSummary".
 */
export interface FinalApprovalSummary {
  gate: string | null;
  status: string | null;
  input_method: "interactive_tty" | "test_fixture" | null;
  fixture_only: boolean | null;
  approval_id: string | null;
  actor_role: string | null;
  result_artifact_ref: string | null;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "finalResult".
 */
export interface FinalResult {
  run_summary: RunSummary;
  mission_summary: MissionSummary;
  capability_summary: CapabilitySummary;
  /**
   * @maxItems 500
   */
  issues: Issue[];
  cross_issue_relations: Relation[];
  conditional_responses: Response[];
  monitoring: Monitor[];
  blind_spots: BlindSpot[];
  expert_review_packets: PublicExpertPacket[];
  approvals: FinalApprovalSummary[];
  integrity: {
    /**
     * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
     * via the `definition` "hash".
     */
    semantic_fingerprint: string;
  };
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "runSummary".
 */
export interface RunSummary {
  run_id: string;
  revision: number;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "missionSummary".
 */
export interface MissionSummary {
  objective: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "capabilitySummary".
 */
export interface CapabilitySummary {
  status: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "issue".
 */
export interface Issue {
  issue_id: string;
  title_template: string;
  primary_grade:
    | "Decision Required"
    | "Immediate Verification"
    | "Expert Review Required"
    | "Monitor"
    | "Appendix Signal"
    | "Not Assessable";
  secondary_flags: IdSet;
  why_it_matters_template: string;
  value_refs: IdSet;
  /**
   * @minItems 1
   */
  evidence_link_ids: [string, ...string[]];
  cause_hypotheses: Claim[];
  counter_hypotheses: Claim[];
  unresolved_conflicts: IdSet;
  verification_next_steps: IdSet;
  conditional_response_refs: IdSet;
  expert_review_refs: IdSet;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "claim".
 */
export interface Claim {
  claim_code: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "relation".
 */
export interface Relation {
  relation_id: string;
  from_issue_ref: string;
  to_issue_ref: string;
  relation_type: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "response".
 */
export interface Response {
  response_id: string;
  condition_template: string;
  direction_template: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "monitor".
 */
export interface Monitor {
  monitor_id: string;
  metric_ref: string;
  condition_template: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "blindSpot".
 */
export interface BlindSpot {
  blind_spot_id: string;
  description_template: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "publicExpertPacket".
 */
export interface PublicExpertPacket {
  expert_packet_id: string;
  profession: string;
  question_template: string;
  forbidden_conclusions: IdSet;
}
export interface PresentationManifestV1 {
  /**
   * @maxItems 3
   */
  ceo_summary_issue_refs: [] | [string] | [string, string] | [string, string, string];
  selection_basis: "grade_order_then_issue_id";
  metric_cards: MetricCardV1[];
  /**
   * @maxItems 50
   */
  chart_specs: ChartSpecV1[];
  issue_graph: IssueGraph;
  /**
   * @minItems 1
   */
  korean_labels: [KoreanLabel, ...KoreanLabel[]];
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "metricCard".
 */
export interface MetricCardV1 {
  metric_card_id: string;
  issue_ref: string;
  label_ko: string;
  value_ref: string;
  display_value: string;
  unit_code: string | null;
  currency_code: string | null;
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "chartSpec".
 */
export interface ChartSpecV1 {
  chart_id: string;
  title_ko: string;
  description_ko: string;
  chart_kind: "line" | "bar" | "graph";
  /**
   * @minItems 1
   */
  issue_refs: [string, ...string[]];
  fact_refs: string[];
  signal_refs: string[];
  x_axis_label_ko: string | null;
  y_axis_label_ko: string | null;
  unit_code: string | null;
  currency_code: string | null;
  scale: string | null;
  display_format: string;
  float_safe: boolean;
  /**
   * @maxItems 5000
   */
  points: ChartPointV1[];
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "chartPoint".
 */
export interface ChartPointV1 {
  point_id: string;
  x_label: string;
  period_sort_key: string | null;
  value_ref: string;
  fact_id: string;
  display_value: string;
  /**
   * @minItems 1
   */
  evidence_link_ids: [string, ...string[]];
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "issueGraph".
 */
export interface IssueGraph {
  nodes: IssueNode[];
  edges: IssueEdge[];
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "issueNode".
 */
export interface IssueNode {
  issue_ref: string;
  label_ko: string;
  grade:
    | "Decision Required"
    | "Immediate Verification"
    | "Expert Review Required"
    | "Monitor"
    | "Appendix Signal"
    | "Not Assessable";
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "issueEdge".
 */
export interface IssueEdge {
  relation_id: string;
  from_issue_ref: string;
  to_issue_ref: string;
  relation_type: string;
}
/**
 * This interface was referenced by `PresentationManifestV1`'s JSON-Schema
 * via the `definition` "koreanLabel".
 */
export interface KoreanLabel {
  code: string;
  label_ko: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "evidenceView".
 */
export interface EvidenceView {
  facts: Fact[];
  signals: Signal[];
  evidence_links: EvidenceLink[];
  data_quality: DataQuality[];
  capability_map: CapabilityMap;
  issue_claim_closure: IssueClaimClosure[];
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "fact".
 */
export interface Fact {
  fact_id: string;
  fact_code: string;
  fact_type: "observed" | "aggregated" | "calculated";
  metric_code: string;
  semantic_role: string;
  observation_role: string;
  scope: ScopeMember[];
  time_context: PeriodContext | AsOfContext | WindowContext;
  value: FactValue;
  source_refs: SourceReference[];
  derivation: Derivation | null;
  quality: IdSet;
  producer: "runtime_intake" | "deterministic_component";
  integrity: {
    /**
     * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
     * via the `definition` "hash".
     */
    payload_hash: string;
  };
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "scopeMember".
 */
export interface ScopeMember {
  dimension_code: string;
  member_code: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "periodContext".
 */
export interface PeriodContext {
  period: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "asOfContext".
 */
export interface AsOfContext {
  as_of: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "windowContext".
 */
export interface WindowContext {
  window: TimeWindow;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "timeWindow".
 */
export interface TimeWindow {
  start: string;
  end: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "factValue".
 */
export interface FactValue {
  value_type: "decimal" | "integer" | "string" | "boolean" | "date" | "datetime" | "category";
  canonical_value: string | number | boolean;
  unit_code: string | null;
  currency_code: string | null;
  scale: string | null;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "sourceReference".
 */
export interface SourceReference {
  source_id: string;
  observation_role: string;
  locator_type: "csv_records" | "json_pointer" | "xlsx_cells";
  locator: CsvLocator | JsonLocator | XlsxLocator;
  selected_fields: IdSet;
  record_count: number;
  filters: Filter[];
  group_by: IdSet;
  operation: string;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  normalized_rows_hash: string;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  row_multiset_hash: string;
  lineage_set_ref: string;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  extraction_hash: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "csvLocator".
 */
export interface CsvLocator {
  /**
   * @minItems 1
   */
  record_indices: [number, ...number[]];
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "jsonLocator".
 */
export interface JsonLocator {
  pointer: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "xlsxLocator".
 */
export interface XlsxLocator {
  sheet: string;
  range: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "filter".
 */
export interface Filter {
  field: string;
  operator: string;
  value: string | number | boolean | null;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "derivation".
 */
export interface Derivation {
  component_id: string;
  component_version: string;
  operation_code: string;
  formula_ref: string;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  parameter_hash: string;
  input_fact_ids: IdSet;
  component_run_id: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "signal".
 */
export interface Signal {
  signal_id: string;
  signal_code: string;
  rule_ref: string;
  component_ref: ComponentRef;
  threshold_ref: string | null;
  input_fact_ids: IdSet;
  required_fact_codes: IdSet;
  missing_fact_codes: IdSet;
  scope: ScopeMember[];
  time_context: PeriodContext | AsOfContext | WindowContext;
  evaluation: EvaluationEntry[];
  outcome: "triggered" | "not_triggered" | "not_assessable";
  direction: string | null;
  impact_band_candidate: "critical" | "high" | "medium" | "low" | null;
  urgency_band_candidate: "immediate" | "near_term" | "routine" | null;
  reason_codes: IdSet;
  producer: "deterministic_component";
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "componentRef".
 */
export interface ComponentRef {
  component_id: string;
  component_version: string;
  component_run_id: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "evaluationEntry".
 */
export interface EvaluationEntry {
  key: string;
  value: string | number | boolean | null;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "evidenceLink".
 */
export interface EvidenceLink {
  evidence_link_id: string;
  target_ref: string;
  target_type:
    | "business_meaning"
    | "problem_candidate"
    | "cause_hypothesis"
    | "counter_hypothesis"
    | "integrated_issue"
    | "causal_relation_hypothesis"
    | "cross_issue_conflict"
    | "conditional_response"
    | "expert_review_need";
  evidence_ref: string;
  evidence_kind: "fact" | "signal";
  polarity: "supports" | "contradicts";
  role: "observation" | "corroboration" | "mechanism" | "counter_evidence" | "boundary";
  rationale_template: string;
  value_refs: ValueReference[];
  stage: string;
  materialized_by: "runtime_normalizer" | "runtime_integrator" | "runtime_grader" | "runtime_hitl";
  origin: Origin;
  independence_group_id: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "valueReference".
 */
export interface ValueReference {
  token: string;
  fact_or_signal_id: string;
  display_field: string;
  display_format_ref: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "origin".
 */
export interface Origin {
  origin_type: "model_proposal" | "deterministic_rule" | "human_overlay";
  origin_job_id: string | null;
  model_profile: string | null;
  prompt_hash: string | null;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  proposal_hash: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "dataQuality".
 */
export interface DataQuality {
  quality_issue_id: string;
  source_ref: string | null;
  issue_code:
    | "missing_required_field"
    | "invalid_decimal"
    | "invalid_date"
    | "ambiguous_unit"
    | "ambiguous_period"
    | "ambiguous_observation_role"
    | "duplicate_business_key"
    | "inconsistent_dimension"
    | "untrusted_formula_value"
    | "unsupported_type";
  severity: "blocking" | "warning" | "info";
  affected_field: string | null;
  raw_value_hash: string | null;
  normalized_role: string | null;
  reason_code: string;
  suggested_resolution: string;
  resolution_status: "open" | "resolved" | "accepted" | "not_applicable";
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "capabilityMap".
 */
export interface CapabilityMap {
  capability_map_id: string;
  capabilities: Capability[];
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "capability".
 */
export interface Capability {
  capability_id: string;
  capability_code: string;
  status: "available" | "partial" | "unsupported";
  available_source_roles: IdSet;
  missing_source_roles: IdSet;
  quality_issue_ids: IdSet;
  reason_codes: IdSet;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "issueClaimClosure".
 */
export interface IssueClaimClosure {
  issue_ref: string;
  claim_refs: IdSet;
  evidence_link_ids: IdSet;
  fact_refs: IdSet;
  signal_refs: IdSet;
  source_refs: IdSet;
  expert_packet_refs: IdSet;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "sourceViewItem".
 */
export interface SourceViewItem {
  source_ref: string;
  display_name_ko: string;
  snapshot_locator: string;
  /**
   * @minItems 1
   */
  extraction_hashes: [string, ...string[]];
  /**
   * @minItems 1
   */
  locator_summaries: [LocatorSummary, ...LocatorSummary[]];
  access_policy: "permitted" | "restricted" | "prohibited";
  official_url: string | null;
  preview_refs: IdSet;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "locatorSummary".
 */
export interface LocatorSummary {
  locator_type: "csv_records" | "json_pointer" | "xlsx_cells";
  display_locator: string;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  extraction_hash: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "sourcePreview".
 */
export interface SourcePreviewV1 {
  preview_ref: string;
  source_ref: string;
  locator: SourceLocator;
  column_labels: string[];
  rows: (string | number | boolean | null)[][];
  truncated: boolean;
  truncation_reason: "bundle_preview_budget" | null;
  masking_status: "none" | "restricted" | "prohibited" | "truncated";
  access_policy: "permitted" | "restricted" | "prohibited";
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  preview_hash: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "sourceLocator".
 */
export interface SourceLocator {
  locator_type: "csv_records" | "json_pointer" | "xlsx_cells";
  record_indices: number[];
  json_pointer: string | null;
  sheet: string | null;
  cell_range: string | null;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "officialUrlPolicy".
 */
export interface OfficialUrlPolicy {
  /**
   * @minItems 1
   */
  allowed_schemes: ["https" | "http", ...("https" | "http")[]];
  allowed_origins: string[];
  allow_redirects: boolean;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "trustView".
 */
export interface TrustView {
  plugin_version: string;
  pack_versions: VersionEntry[];
  schema_versions: VersionEntry[];
  validator_version: string;
  completed_checks: IdSet;
  approval_summary: FinalApprovalSummary[];
  trust_events: TrustEventV1[];
  file_hashes: FileHash[];
  limitations: IdSet;
  deidentification: Deidentification;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "versionEntry".
 */
export interface VersionEntry {
  name: string;
  version: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "trustEvent".
 */
export interface TrustEventV1 {
  event_id: string;
  revision: number;
  command: string;
  actor_kind: "human" | "runtime";
  gate: string | null;
  sequence: number;
  timestamp: string | null;
  invalidated_approval_refs: IdSet;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "fileHash".
 */
export interface FileHash {
  logical_path: string;
  length_bytes: number;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  sha256: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "deidentification".
 */
export interface Deidentification {
  poc_only: boolean;
  direct_identifiers_removed: boolean;
  notice_ko: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "expertPacketViewItem".
 */
export interface ExpertPacketViewItemV1 {
  expert_packet_id: string;
  profession: string;
  target_issue_ref: string;
  fact_refs: IdSet;
  evidence_link_ids: IdSet;
  source_refs: IdSet;
  cause_hypotheses: IdSet;
  counter_hypotheses: IdSet;
  unresolved_uncertainties: IdSet;
  required_document_refs: IdSet;
  review_question: string;
  forbidden_conclusions: IdSet;
  source_locators: SourceLocatorEntry[];
  run_id: string;
  revision: number;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  packet_hash: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "sourceLocatorEntry".
 */
export interface SourceLocatorEntry {
  source_ref: string;
  locator: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "revisionView".
 */
export interface RevisionViewV1 {
  available: boolean;
  unavailable_reason: "NO_PRIOR_FINAL_RESULT" | null;
  base_revision: number | null;
  compare_revision: number | null;
  change_categories: (
    | "data"
    | "mapping"
    | "mission"
    | "scope"
    | "pack"
    | "component"
    | "evidence"
    | "grade"
    | "approval"
    | "wording"
    | "expert_packet"
  )[];
  added_refs: IdSet;
  changed_refs: IdSet;
  removed_refs: IdSet;
  invalidated_approval_refs: IdSet;
  previous_semantic_fingerprint: string | null;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  current_semantic_fingerprint: string;
  display_message_ko: string;
}
/**
 * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
 * via the `definition` "fileManifestItem".
 */
export interface FileManifestItem {
  logical_path: string;
  length_bytes: number;
  /**
   * This interface was referenced by `WebReportBundleV1`'s JSON-Schema
   * via the `definition` "hash".
   */
  sha256: string;
}
export interface ViewerEligibilityDecisionV1 {
  decision_version: "1.0.0";
  eligible: boolean;
  viewer_mode: "trusted_final" | "poc_fixture" | "unverified_import" | "rejected";
  badge_label_ko: "승인·검증된 실행본" | "검증된 POC 시연 실행본" | "출처 미확인 묶음" | "열 수 없는 묶음";
  run_id: string | null;
  revision: number | null;
  bundle_hash: string | null;
  completed_checks: string[];
  failure_code:
    | "BUNDLE_SIZE_EXCEEDED"
    | "BUNDLE_JSON_INVALID"
    | "BUNDLE_SCHEMA_INVALID"
    | "BUNDLE_HASH_MISMATCH"
    | "REFERENCE_CLOSURE_BROKEN"
    | "RUN_ID_MISMATCH"
    | "REVISION_MISMATCH"
    | "WORKFLOW_NOT_FINALIZED"
    | "REQUIRED_CHECK_MISSING"
    | "FINAL_APPROVAL_INVALID"
    | "ANCESTRY_MISMATCH"
    | "FULL_RUN_MISMATCH"
    | "BYTE_MISMATCH"
    | "ABSOLUTE_PATH_LEAK"
    | null;
  failure_message: string | null;
}
export interface ResultQuestionJobV1 {
  job_version: "1.0.0";
  job_id: string;
  /**
   * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
   * via the `definition` "sha256".
   */
  job_hash: string;
  run_id: string;
  revision: number;
  question: string;
  response_locale: "ko-KR";
  privacy_classification: "poc_deidentified" | "company_restricted";
  scope: Scope;
  allowed_issue_refs: IdSet1;
  allowed_claim_refs: IdSet1;
  allowed_fact_refs: IdSet1;
  allowed_signal_refs: IdSet1;
  allowed_evidence_link_ids: IdSet1;
  allowed_source_refs: IdSet1;
  allowed_value_refs: IdSet1;
  allowed_expert_packet_refs: IdSet1;
  allowed_revision_diff_refs: IdSet1;
  /**
   * @maxItems 2000
   */
  context_blocks: ContextBlock[];
  value_table: ValueEntry[];
  forbidden_conclusions: TextSet;
  data_quality_conditions: TextSet;
  not_assessable_conditions: TextSet;
  deidentification: Deidentification1;
  privacy: Privacy;
  context_caps: ContextCaps;
  excluded_summary: ExcludedSummary;
  output_schema_version: "1.0.0";
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "scope".
 */
export interface Scope {
  scope_kind: "run" | "issue" | "section" | "claim" | "evidence" | "source" | "expert_packet" | "revision_diff";
  scope_instance_id: string;
  start_refs: IdSet1;
  issue_id: string | null;
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "contextBlock".
 */
export interface ContextBlock {
  block_ref: string;
  block_kind:
    "issue" | "claim" | "fact" | "signal" | "evidence" | "source" | "expert_packet" | "revision_diff" | "trust";
  subject_ref: string;
  text: string;
  claim_refs: IdSet1;
  evidence_link_ids: IdSet1;
  source_refs: IdSet1;
  value_refs: IdSet1;
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "valueEntry".
 */
export interface ValueEntry {
  value_ref: string;
  fact_or_signal_id: string;
  display_field: string;
  display_text: string;
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "deidentification".
 */
export interface Deidentification1 {
  poc_only: boolean;
  direct_identifiers_removed: boolean;
  notice_ko: string;
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "privacy".
 */
export interface Privacy {
  deidentified: boolean;
  excluded_fields: TextSet;
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "contextCaps".
 */
export interface ContextCaps {
  max_context_bytes: 131072;
  actual_context_bytes: number;
  excluded_block_count: number;
  max_answer_blocks: 12;
  max_block_characters: 800;
}
/**
 * This interface was referenced by `ResultQuestionJobV1`'s JSON-Schema
 * via the `definition` "excludedSummary".
 */
export interface ExcludedSummary {
  excluded: boolean;
  reason_codes: TextSet;
  available_scope_instance_ids: IdSet1;
}
export interface ResultAnswerDraftV1 {
  draft_version: "1.0.0";
  job_id: string;
  run_id: string;
  revision: number;
  /**
   * @maxItems 12
   */
  answer_blocks:
    | []
    | [SupportedAnswerBlock | NotSupportedAnswerBlock]
    | [SupportedAnswerBlock | NotSupportedAnswerBlock, SupportedAnswerBlock | NotSupportedAnswerBlock]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ]
    | [
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock,
        SupportedAnswerBlock | NotSupportedAnswerBlock
      ];
}
/**
 * This interface was referenced by `ResultAnswerDraftV1`'s JSON-Schema
 * via the `definition` "supportedAnswerBlock".
 */
export interface SupportedAnswerBlock {
  block_id: string;
  support_status: "supported";
  text_template: string;
  value_refs: IdSet2;
  claim_refs: NonEmptyIdSet;
  evidence_link_ids: NonEmptyIdSet;
  source_refs: IdSet2;
}
/**
 * This interface was referenced by `ResultAnswerDraftV1`'s JSON-Schema
 * via the `definition` "notSupportedAnswerBlock".
 */
export interface NotSupportedAnswerBlock {
  block_id: string;
  support_status: "not_supported";
  text_template: "현재 실행본의 근거로는 확인할 수 없습니다";
  value_refs: EmptyIdSet;
  claim_refs: EmptyIdSet;
  evidence_link_ids: EmptyIdSet;
  source_refs: EmptyIdSet;
}
export interface ResultAnswerV1 {
  answer_version: "1.0.0";
  job_id: string;
  run_id: string;
  revision: number;
  scope: Scope;
  validation: Validation;
  /**
   * @maxItems 12
   */
  answer_blocks:
    | []
    | [SupportedAnswerBlock1 | NotSupportedAnswerBlock1]
    | [SupportedAnswerBlock1 | NotSupportedAnswerBlock1, SupportedAnswerBlock1 | NotSupportedAnswerBlock1]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ]
    | [
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1,
        SupportedAnswerBlock1 | NotSupportedAnswerBlock1
      ];
}
/**
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "validation".
 */
export interface Validation {
  schema_valid: true;
  references_valid: true;
  values_valid: true;
  semantic_entailment_verified: false;
  label_ko: "스키마·참조 검증 통과";
}
/**
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "supportedAnswerBlock".
 */
export interface SupportedAnswerBlock1 {
  block_id: string;
  support_status: "supported";
  text: string;
  resolved_values: ResolvedValue[];
  claim_refs: NonEmptyIdSet1;
  evidence_link_ids: NonEmptyIdSet1;
  source_refs: IdSet3;
}
/**
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "resolvedValue".
 */
export interface ResolvedValue {
  value_ref: string;
  display_text: string;
}
/**
 * This interface was referenced by `ResultAnswerV1`'s JSON-Schema
 * via the `definition` "notSupportedAnswerBlock".
 */
export interface NotSupportedAnswerBlock1 {
  block_id: string;
  support_status: "not_supported";
  text: "현재 실행본의 근거로는 확인할 수 없습니다";
  /**
   * @maxItems 0
   */
  resolved_values: never[];
  claim_refs: EmptyIdSet1;
  evidence_link_ids: EmptyIdSet1;
  source_refs: EmptyIdSet1;
}
