export type Scan = {
  detection_status: "NO_EVIDENCE_FOUND" | "MALICIOUS_INDICATORS" | "INCOMPLETE";
  policy_decision: "ALLOW" | "WARN" | "BLOCK" | "REQUIRE_REVIEW";
  model_status: string;
  evidence: { view: string; start: number; end: number; score: number; model_hash: string }[];
  windows: { view: string; start: number; end: number; score: number; model_hash: string }[];
  threshold: number | null;
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
