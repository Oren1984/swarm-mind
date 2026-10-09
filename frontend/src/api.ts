import type { QuickResult, SessionState, StoredResults } from "./types";

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed with HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export interface SessionParams {
  seed: number;
  agent_count: number;
  deposit: number;
  interruption_step: number;
}

export const api = {
  createSession: (p: SessionParams) => request<SessionState>("/session", p),
  step: (id: string, n: number) => request<SessionState>(`/session/${id}/step`, { n }),
  interrupt: (id: string) => request<SessionState>(`/session/${id}/interrupt`, {}),
  obstacle: (id: string, point?: { x: number; y: number }) =>
    request<SessionState>(`/session/${id}/obstacle`, point ?? {}),
  quickExperiment: (seeds: number, steps: number) =>
    request<QuickResult>("/experiments/quick", { seeds, steps, first_seed: 1 }),
  /** Resolves to null when no stored experiment exists yet. */
  storedResults: async (): Promise<StoredResults | null> => {
    const res = await request<StoredResults & { available: boolean }>("/experiments/results");
    return res.available ? res : null;
  },
};
