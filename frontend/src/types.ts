// Shapes of the JSON produced by the Python API. The dashboard only displays
// these values; it never computes simulation behaviour itself.

export type WorldMode = "independent" | "collective" | "interrupted";
export const WORLD_MODES: WorldMode[] = ["independent", "collective", "interrupted"];

export interface Metrics {
  step: number;
  food_delivered: number;
  first_delivery_step: number | null;
  exploration_coverage: number;
  travel_efficiency: number | null;
  delivery_rate_per_100: number | null;
  recent_rate_per_100: number | null;
  food_relocations: number;
  deposit_events: number;
  communication_active: boolean;
  communication_disabled_step: number | null;
}

export interface SimEvent {
  type: "communication_disabled" | "obstacle_added";
  step: number;
  source: "scheduled" | "manual";
}

export interface WorldState {
  mode: WorldMode;
  agents: { x: number[]; y: number[]; heading: number[]; behaviour: number[] };
  food: { x: number; y: number; amount: number; r: number }[];
  obstacles: string;
  pheromone: string | null;
  metrics: Metrics;
  series: { steps: number[]; delivered: number[] };
  events: SimEvent[];
}

export interface SessionState {
  session_id: string;
  version: string;
  config: { seed: number; agent_count: number; deposit: number; food_capacity: number };
  interruption_step: number;
  width: number;
  height: number;
  nest: { x: number; y: number; r: number };
  step: number;
  mode: "controlled" | "exploratory";
  exploratory_reasons: string[];
  worlds: Record<WorldMode, WorldState>;
  applied?: boolean;
}

export interface Describe {
  n: number;
  n_undefined: number;
  mean: number | null;
  sd: number | null;
  median: number | null;
}

export interface Paired {
  n_pairs: number;
  mean_difference: number | null;
  ci95: [number, number] | null;
  effect_size_dz: number | null;
  relative_difference_pct: number | null;
  treatment_higher_in: string | null;
}

export interface QuickResult {
  seeds: number[];
  steps: number;
  interruption_step: number;
  food_delivered: Record<WorldMode, Describe>;
  per_seed: Record<WorldMode, number[]>;
  collective_vs_independent: Paired;
  interrupted_vs_collective: Paired;
}

export interface ModeComparison {
  independent: Describe;
  collective: Describe;
  communication_effect: Paired;
}

export interface StoredResults {
  manifest: {
    simulator_version: string;
    generated_utc: string;
    spec: { seeds: number[]; steps: number; interruption_step: number; obstacle_step: number; window: number };
  };
  results: {
    exp1_baseline_food_collection: Record<string, ModeComparison>;
    exp2_trail_emergence: { independent: Describe; collective: Describe; difference: Paired };
    exp3_communication_failure: {
      pre_interruption_trajectories_identical: boolean;
      post_deliveries: Record<WorldMode, Describe>;
      interrupted_vs_collective_post: Paired;
      interrupted_vs_independent_post: Paired;
    };
    exp4_dynamic_obstacle: Record<"independent" | "collective", {
      immediate_ratio: Describe;
      recovery_ratio: Describe;
      control_ratio: Describe;
    }>;
    exp6_sensitivity: Record<string, ModeComparison>;
  };
}
