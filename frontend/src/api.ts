export type Frame = { id: string; name: string; width: number; height: number }
export type Mapping = { node_id: string; label: string; breakpoint: number; selector: string; confidence?: string; signals?: string[] }
export type State = 'queued' | 'running' | 'awaiting_frames' | 'awaiting_mapping' | 'completed' | 'failed' | 'interrupted'
export type Job = {
  job_id: string; state: State; stage?: string; events?: { stage: string; message?: string }[];
  error?: { message: string }; frames?: Frame[]; selected_frames?: Record<string, string>; breakpoints?: number[]; mappings?: Mapping[];
  completed_checks?: number; total_checks?: number; elapsed_seconds?: number;
}
export type Finding = {
  label: string; category: string; property: string; expected: string; actual: string;
  difference?: string; recommendation?: string; severity: 'High' | 'Medium' | 'Low';
}
export type Check = {
  page: string; breakpoint: number; status: 'PASS' | 'FAIL' | 'ERROR'; ssim?: number;
  findings: Finding[]; images?: { design: string; live: string; diff: string }; error?: string;
  coverage?: string[];
}
export type Result = { job_id: string; live_url?: string; figma_url?: string; created_at?: string; verdict?: string; similarity?: number; issues?: number; checks: Check[] }
export type History = {
  items: { job_id: string; name: string; created_at: string; state: State; verdict?: string; similarity?: number; issues?: number }[];
  totals?: { websites: number; issues: number; similarity?: number };
}
export const stages = [
  ['validate', 'Validating URLs'], ['figma', 'Retrieving design'],
  ['mapping', 'Identifying design elements'], ['capture', 'Capturing live website'],
  ['visual', 'Comparing screenshots'], ['styles', 'Comparing styles'], ['report', 'Generating report'],
] as const

export async function api<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch('/api' + path, {
      signal,
      ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    })
  } catch {
    throw new Error('Could not reach the DesignQA API. Check that the backend is running.')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const detail = data?.error?.message ?? data?.detail
    if (response.status >= 500) throw new Error('The DesignQA API is unavailable. Try again in a moment.')
    throw new Error(typeof detail === 'string' ? detail : `Request failed (HTTP ${response.status}). Check your input and retry.`)
  }
  try {
    return await response.json()
  } catch {
    throw new Error('The DesignQA API did not return a valid response.')
  }
}

