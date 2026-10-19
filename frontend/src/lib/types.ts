import type { components } from "./api-types";

type S = components["schemas"];

export type Role = S["RoleOut"];
export type Category = S["CategoryOut"];
export type Project = S["ProjectOut"];
export type ProjectListItem = S["ProjectListItem"];
export type DocumentOut = S["DocumentOut"];
export type Chunk = S["ChunkOut"];
export type Job = S["JobOut"];
export type Estimate = S["EstimateOut"];
export type EstimateTree = S["EstimateTree"];
export type ModuleOut = S["ModuleOut"];
export type TaskOut = S["TaskOut"];
export type TaskPatch = S["TaskPatch"];
export type Baseline = S["BaselineOut"];
export type EditEvent = S["EditEventOut"];
export type Proposal = S["ProposalOut"];
export type Question = S["QuestionOut"];
export type Assumption = S["AssumptionOut"];
export type ActualRow = S["ActualRow"];
export type Unplanned = S["UnplannedOut"];
export type Rule = S["RuleOut"];
export type BacktestRun = S["BacktestRunOut"];
export type BacktestDetail = S["BacktestDetail"];
export type CompareOut = S["CompareOut"];
export type ReasonTag = NonNullable<S["TaskPatch"]["reason_tag"]>;

export const REASON_TAGS: { value: ReasonTag; label: string }[] = [
  { value: "underestimated_complexity", label: "Underestimated complexity" },
  { value: "overestimated", label: "Overestimated" },
  { value: "reuse_existing_code", label: "Reuse existing code" },
  { value: "client_specific", label: "Client-specific" },
  { value: "scope_added", label: "Scope added" },
  { value: "scope_removed", label: "Scope removed" },
  { value: "risk_buffer", label: "Risk buffer" },
  { value: "other", label: "Other" },
];

// Shapes of endpoints that return free-form JSON (dict) on the backend.
export interface HistogramBin {
  x0: number;
  x1: number;
  count: number;
}

export interface Simulation {
  p10: number;
  p50: number;
  p80: number;
  p90: number;
  mean: number;
  draws: number;
  histogram: HistogramBin[];
  empirical_categories: string[];
  shared: string;
}

export interface Bucket {
  name: string;
  min: number;
  max: number;
  mid: number;
  cost: number;
}

export interface EstimateSummary {
  total_min: number;
  total_max: number;
  total_mid: number;
  task_count: number;
  total_cost_mid: number;
  currency: string;
  by_module: Bucket[];
  by_role: Bucket[];
  simulation: Simulation;
}

export interface Calibration {
  mu: number;
  sigma2: number;
  sigma: number;
  factor: number;
  scope_used: string;
  n_edit: number;
  n_actual: number;
  mu_edit: number;
  mu_actual: number | null;
}

export interface AnalogInfo {
  task_id: string;
  project_id: string;
  project_name: string;
  title: string;
  similarity: number;
  raw_mid: number | null;
  final_mid: number | null;
  actual_mid: number | null;
}

export interface Provenance {
  raw: { min: number; max: number; samples: [number, number][] };
  analogs: AnalogInfo[];
  analog_candidates?: AnalogInfo[];
  analog_mid?: number | null;
  blend_weight?: number;
  calibration: Calibration | null;
  source_chunk_ids: string[];
  rules_applied: string[];
  learning: boolean;
  reference_projects?: ReferenceProject[];
}

export interface ReferenceProject {
  project_id: string;
  name: string;
  similarity: number;
  score: number;
  status: string;
  data_source: string;
  why?: string[];
  total_min?: number;
  total_max?: number;
  actual_total?: number | null;
  notes?: string[];
}

export type ApplyMode = "auto" | "review";

export interface AgentSessionOut {
  id: string;
  estimate_id: string;
  title: string;
  summary: string;
  state: Record<string, unknown>;
  status: string;
  pinned: boolean;
  apply_mode: ApplyMode;
  use_memory: boolean;
  run_state: string;
  cost_usd: number;
  tokens: number;
  model_key: string | null;
  created_at: string;
  last_activity_at: string | null;
}

export interface ToolLogEntry {
  id: string;
  name: string;
  ok: boolean;
  status?: string | null;
  summary?: string | null;
  operation_id?: string | null;
}

export interface AgentMsg {
  id: string;
  role: "user" | "assistant" | "system_event";
  content: string;
  tool_calls: ToolLogEntry[];
  payload: Record<string, unknown>;
  batch_id: string | null;
  created_at: string;
}

export interface AgentOperationOut {
  id: string;
  session_id: string | null;
  batch_id: string;
  op_type: string;
  status: "pending" | "awaiting_confirmation" | "applied" | "rejected" | "failed" | "reverted";
  summary: string;
  result: {
    before?: [number, number];
    after?: [number, number];
    touched_task_ids?: string[];
    created_ids?: string[];
    undo?: { applied: number; skipped: { task_id: string; title: string; reason: string }[] };
  };
  tool_call_id: string | null;
  message_id: string | null;
}

export interface ProjectMemoryOut {
  id: string;
  kind: "fact" | "decision" | "constraint" | "preference";
  text: string;
  origin: "user" | "agent" | "document";
  enabled: boolean;
}

export interface ProposalOp {
  id: string;
  type: "add_task" | "update_task" | "remove_task" | "split_task" | "bulk_adjust" | "add_module";
  status: "pending" | "accepted" | "rejected";
  summary: string;
  rationale?: string;
  actor?: string;
  payload: {
    task_id?: string;
    title?: string;
    changes?: Record<string, unknown> | BulkChange[];
    min_hours?: number;
    max_hours?: number;
    before?: { min_hours?: number; max_hours?: number; title?: string };
    [k: string]: unknown;
  };
}

export interface BulkChange {
  task_id: string;
  title: string;
  old_min: number;
  old_max: number;
  new_min: number;
  new_max: number;
}

export interface CalibrationRow {
  layer: "edit" | "actual";
  scope_type: string;
  scope_key: string;
  label: string;
  n: number;
  factor: number;
  factor_lo: number;
  factor_hi: number;
  shrunk_mean: number;
  shrunk_var: number;
}

export type TimelinePoint = { id: string; created_at: string; trigger: string; layer: string } & Record<
  string,
  number | string | null
>;

export interface AccuracyPoint {
  project_id: string;
  name: string;
  data_source: string;
  delivered_at: string;
  ape: number | null;
  task_mdape: number | null;
  within_p80: boolean | null;
  unplanned_share: number | null;
}

export interface StructuralSignals {
  categories: {
    category: string;
    ai_tasks: number;
    added: number;
    removed: number;
    missing_task_rate: number;
    false_positive_rate: number;
  }[];
  frequently_added: { category: string; title: string; count: number }[];
  unplanned_share_mean: number | null;
  unplanned_share_n: number;
}

export interface Metrics {
  n: number;
  MAPE?: number;
  MdAPE?: number;
  MMRE?: number;
  PRED25?: number;
  bias?: number;
  coverage_p80?: number;
  interval_width?: number;
}

export interface EstimatorResult {
  task: Metrics;
  project: Metrics;
  task_ci: Record<string, [number, number]>;
  project_ci: Record<string, [number, number]>;
}

export interface BacktestSummary {
  protocol: string;
  n_projects: number;
  estimators: Record<string, EstimatorResult>;
  learning_curve?: ({ n_train: number } & Record<string, number>)[];
  small_sample: boolean;
  data_sources: string[];
}

export interface BacktestProject {
  project_id: string;
  name: string;
  data_source: string;
  actual: number;
  n_train: number;
  estimators: Record<string, { p50: number; p80: number; ape: number; covered_p80: boolean }>;
}

export interface Accuracy {
  estimate_id: string;
  tasks_total: number;
  tasks_with_actuals: number;
  estimate_mid_for_tasks_with_actuals: number;
  planned_actual_hours: number;
  unplanned_hours: number;
  total_actual_hours: number;
  unplanned_share: number | null;
  p50: number | null;
  p80: number | null;
  within_p80: boolean | null;
  project_ape: number | null;
  task_mdape: number | null;
  task_in_range_share: number | null;
}

export interface LearningSettings {
  values: Record<string, number>;
  defaults: Record<string, number>;
  descriptions: Record<string, string>;
}
