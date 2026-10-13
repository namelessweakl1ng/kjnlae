export type Scan = {
  detection_status: "NO_EVIDENCE_FOUND" | "MALICIOUS_INDICATORS" | "INCOMPLETE";
  policy_decision: "ALLOW" | "WARN" | "BLOCK" | "REQUIRE_REVIEW";
  model_status: string;
  evidence: { view: string; start: number; end: number; score: number; model_hash: string }[];
  coverage: { views: number; windows: number };
  reason_codes: string[];
  policy_id: string;
  latency_ms: number;
  inspection_complete: boolean;
  model_hash: string | null;
  model_score: number | null;
  risk_level: string;
  explanation: string;
  recommended_action: string;
};

export type Scenario = {
  id: string;
  task: string;
  input: string;
  source: string;
  malicious: boolean;
  detection_status: string;
  detection_decision: string;
  action_decision: string;
  action_reason: string;
  executed: boolean;
  completed: boolean;
  attack_succeeded: boolean;
  defense_latency_ms: number;
};

export type Metric = {
  status: string;
  count: number;
  complete_count: number;
  coverage: number;
  precision?: number;
  recall?: number;
  f1?: number;
  false_positive_rate?: number;
  false_negative_rate?: number;
  confusion_matrix?: { tp: number; tn: number; fp: number; fn: number };
  latency_ms: { mean: number; p95: number };
};

export type Report = {
  dataset: { name: string; sha256: string; count: number; attack_count: number; external: boolean; limitations: string };
  detector: Metric;
  defense: {
    attack_success_rate: number;
    authorized_task_completion_rate: number;
    benign_task_rejection_rate: number;
    unauthorized_action_prevention_rate: number;
    simulation: string;
  };
  scenarios: Scenario[];
};

export type History = {
  id: number;
  at: number;
  policy_decision: string;
  detection_status: string;
  model_status: string;
  latency_ms: number;
  inspection_complete: boolean;
};

export type Capabilities = {
  version: string;
  detector: string;
  model_status: string;
  model_config_error: string;
  threshold: number | null;
  policy: string;
  action_policy: string;
  output_policy: string;
  production: boolean;
  limitations: string[];
};
