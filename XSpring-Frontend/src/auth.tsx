import { createContext, useCallback, useContext, useEffect, useState } from "react"
import type { ReactNode } from "react"
import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google"

const API_BASE_URL = "https://xspring-api.onrender.com"
const GOOGLE_CLIENT_ID = String(import.meta.env.VITE_GOOGLE_CLIENT_ID || "").trim()
const DEALER_API_KEY = String(import.meta.env.VITE_DEALER_API_KEY || "").trim()

const TOKEN_KEY = "xspring_token"
const USER_KEY = "xspring_user"

export type AuthUser = {
  email: string
  name?: string
  picture?: string
  role?: string
}

/* ---------- storage helpers ---------- */

function readToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || ""
  } catch {
    return ""
  }
}

function tokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))
    return !payload.exp || payload.exp * 1000 <= Date.now()
  } catch {
    return true
  }
}

function readUser(): AuthUser | null {
  try {
    const token = readToken()
    if (!token || tokenExpired(token)) return null
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}

function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    // ignore
  }
}

/** ใช้แทน header เดิมทุกที่: { Accept: "...", ...authHeaders() } */
export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  if (DEALER_API_KEY) headers["X-API-Key"] = DEALER_API_KEY
  const token = readToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

/** session หมดอายุ/ไม่ถูกต้อง -> ให้ AuthGate เด้งกลับหน้า login */
const UNAUTHORIZED_EVENT = "xspring:unauthorized"

/** fetch ที่แนบ X-API-Key + Bearer ให้เอง และ logout อัตโนมัติเมื่อได้ 401 */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    headers: { ...(init.headers as Record<string, string> | undefined), ...authHeaders() },
  })

  if (response.status === 401) {
    clearSession()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }

  return response
}

/* ---------- context ---------- */

type AuthContextValue = {
  user: AuthUser
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth ต้องอยู่ใน <AuthGate>")
  return ctx
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{children}</GoogleOAuthProvider>
}

/** แสดงหน้า login ถ้ายังไม่ล็อกอิน ถ้าล็อกอินแล้วค่อย render children */
export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => readUser())

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, logout)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, logout)
  }, [logout])

  if (!user) return <LoginScreen onLoggedIn={setUser} />

  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>
}

/* ---------- login screen ---------- */

function LoginScreen({ onLoggedIn }: { onLoggedIn: (user: AuthUser) => void }) {
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  // ให้ธีมตรงกับที่ผู้ใช้เลือกไว้ แม้ยังไม่ได้เข้า App หลัก
  useEffect(() => {
    let dark = window.matchMedia("(prefers-color-scheme: dark)").matches
    try {
      const saved = localStorage.getItem("theme")
      if (saved === "light" || saved === "dark") dark = saved === "dark"
    } catch {
      // ignore
    }
    document.documentElement.classList.toggle("dark", dark)
  }, [])

  const handleCredential = async (credential?: string) => {
    if (!credential) {
      setError("ไม่ได้รับข้อมูลจาก Google")
      return
    }

    setLoading(true)
    setError("")

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ credential }),
      })
      const body = await response.json().catch(() => ({}))

      if (!response.ok || !body?.token || !body?.user) {
        if (response.status === 403) throw new Error("อีเมลนี้ยังไม่ได้รับอนุญาตให้ใช้งาน")
        throw new Error(typeof body?.detail === "string" ? body.detail : "ล็อกอินไม่สำเร็จ")
      }

      try {
        localStorage.setItem(TOKEN_KEY, body.token)
        localStorage.setItem(USER_KEY, JSON.stringify(body.user))
      } catch {
        throw new Error("เบราว์เซอร์บล็อกการบันทึก session")
      }

      onLoggedIn(body.user as AuthUser)
    } catch (e) {
      setError(e instanceof Error ? e.message : "ล็อกอินไม่สำเร็จ")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <div className="w-full max-w-sm rounded-2xl border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary text-lg font-bold text-primary-foreground">
          X
        </div>
        <h1 className="mt-4 text-xl font-semibold">XSpring Dealer Suite</h1>
        <p className="mt-1 text-sm text-muted-foreground">เข้าสู่ระบบด้วยบัญชี Google</p>

        <div className="mt-6 flex justify-center">
          {!GOOGLE_CLIENT_ID ? (
            <p className="text-sm text-red-500">ยังไม่ได้ตั้ง VITE_GOOGLE_CLIENT_ID</p>
          ) : loading ? (
            <p className="text-sm text-muted-foreground">กำลังตรวจสอบ...</p>
          ) : (
            <GoogleLogin
              onSuccess={(res) => handleCredential(res.credential)}
              onError={() => setError("Google login ไม่สำเร็จ")}
              theme="filled_black"
              shape="pill"
            />
          )}
        </div>

        {error && <p className="mt-4 text-sm text-red-500">{error}</p>}
      </div>
    </div>
  )
}
