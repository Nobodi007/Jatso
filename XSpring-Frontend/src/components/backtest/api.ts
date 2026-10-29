import type { Meta, Run, Spec } from "./types"

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

const PREFIX = "/api/backtest-lab"

async function call<T>(apiBase: string, token: string | null, method: string, path: string, body?: unknown): Promise<T> {
  if (!token) throw new ApiError(401, "login_required", "กรุณาเข้าสู่ระบบ")
  let res: Response
  try {
    res = await fetch(`${apiBase}${PREFIX}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, "network", "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้")
  }
  let data: { code?: string; message?: string; detail?: string } | null = null
  try {
    data = await res.json()
  } catch {
    data = null
  }
  if (!res.ok) {
    const code = data?.code ?? data?.detail ?? "error"
    throw new ApiError(res.status, code, data?.message ?? `ผิดพลาด (${res.status})`)
  }
  return data as T
}

export const fetchMeta = (b: string, t: string | null) => call<Meta>(b, t, "GET", "/meta")
export const createRun = (b: string, t: string | null, spec: Spec) =>
  call<{ id: string; status: string; duplicate?: boolean }>(b, t, "POST", "/runs", { spec })
export const getRun = (b: string, t: string | null, id: string) => call<Run>(b, t, "GET", `/runs/${encodeURIComponent(id)}`)
export const listRuns = (b: string, t: string | null) => call<{ runs: Run[] }>(b, t, "GET", "/runs")
export const deleteRun = (b: string, t: string | null, id: string) =>
  call<{ deleted: boolean }>(b, t, "DELETE", `/runs/${encodeURIComponent(id)}`)
