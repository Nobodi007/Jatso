import { useEffect, useRef, useCallback, useState } from "react"
import createGlobe from "cobe"

type RGB = [number, number, number]
type Marker = { id: string; location: [number, number] }
type Arc = { id: string; from: [number, number]; to: [number, number] }

/* ---------- ข้อมูลบนโลก (อยู่นอกคอมโพเนนต์ เพื่อไม่ให้สร้างโลกใหม่ทุกครั้งที่ render) ---------- */
const MARKERS: Marker[] = [
  { id: "bkk", location: [13.7563, 100.5018] },
  { id: "nyc", location: [40.7128, -74.006] },
  { id: "london", location: [51.5074, -0.1278] },
  { id: "tokyo", location: [35.6762, 139.6503] },
  { id: "sydney", location: [-33.8688, 151.2093] },
]

const LABELS: Record<string, string> = {
  bkk: "Bangkok",
  nyc: "NYSE · NASDAQ",
  london: "London",
  tokyo: "Tokyo",
  sydney: "Sydney",
}

const ARCS: Arc[] = [
  { id: "bkk-nyc", from: [13.7563, 100.5018], to: [40.7128, -74.006] },
  { id: "nyc-london", from: [40.7128, -74.006], to: [51.5074, -0.1278] },
  { id: "bkk-london", from: [13.7563, 100.5018], to: [51.5074, -0.1278] },
  { id: "bkk-tokyo", from: [13.7563, 100.5018], to: [35.6762, 139.6503] },
]
/* ---------- สีตามธีม: แก้ตรงนี้ที่เดียว ---------- */
const THEME = {
  dark: {
    dark: 1,
    baseColor: [0.16, 0.2, 0.18] as RGB,
    markerColor: [0.06, 0.8, 0.5] as RGB, // เขียว
    arcColor: [0.06, 0.8, 0.5] as RGB,
    glowColor: [0.02, 0.15, 0.1] as RGB,
    mapBrightness: 5,
  },
  light: {
    dark: 0,
    baseColor: [1, 1, 1] as RGB, // ลูกโลกขาว กลืนไปกับพื้นหลัง
    markerColor: [0.9, 0.1, 0.1] as RGB, // แดง
    arcColor: [0.9, 0.1, 0.1] as RGB, // เส้นแดง
    glowColor: [1, 1, 1] as RGB,
    mapBrightness: 6,
  },
}

/* ---------- ตรวจธีมจาก "สีพื้นหลังจริง" ของหน้า (เดินขึ้นไปหา element ที่มีสีพื้นหลัง) ---------- */
// แปลงสี CSS ทุกรูปแบบ (รวม oklch/lab ที่ Tailwind v4 ใช้) เป็น RGB ผ่าน canvas
let _ctx: CanvasRenderingContext2D | null = null
function lumOf(color: string): { lum: number; alpha: number } | null {
  if (!_ctx) {
    _ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })
  }
  if (!_ctx) return null
  _ctx.clearRect(0, 0, 1, 1)
  _ctx.fillStyle = "#000"
  _ctx.fillStyle = color
  _ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = _ctx.getImageData(0, 0, 1, 1).data
  return { lum: (0.299 * r + 0.587 * g + 0.114 * b) / 255, alpha: a / 255 }
}

function useIsDark(ref: React.RefObject<HTMLElement | null>): boolean {
  const [isDark, setIsDark] = useState(true)
  useEffect(() => {
    const check = () => {
      let node: HTMLElement | null = ref.current
      while (node) {
        const v = lumOf(getComputedStyle(node).backgroundColor)
        if (v && v.alpha > 0.5) {
          setIsDark(v.lum < 0.5) // พื้นหลังเข้ม = ธีมมืด
          return
        }
        node = node.parentElement
      }
      // ไม่เจอสีพื้นหลังเลย: ใช้สีตัวหนังสือแทน
      if (ref.current) {
        const t = lumOf(getComputedStyle(ref.current).color)
        if (t) setIsDark(t.lum > 0.5)
      }
    }
    check()
    const id = setInterval(check, 400)
    return () => clearInterval(id)
  }, [ref])
  return isDark
}

/* ---------- ลูกโลก (cobe) ---------- */
function Globe({ isDark }: { isDark: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const pointerInteracting = useRef<{ x: number; y: number } | null>(null)
  const lastPointer = useRef<{ x: number; y: number; t: number } | null>(null)
  const dragOffset = useRef({ phi: 0, theta: 0 })
  const velocity = useRef({ phi: 0, theta: 0 })
  const phiOffsetRef = useRef(0)
  const thetaOffsetRef = useRef(0)
  const isPausedRef = useRef(false)

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    pointerInteracting.current = { x: e.clientX, y: e.clientY }
    if (canvasRef.current) canvasRef.current.style.cursor = "grabbing"
    isPausedRef.current = true
  }, [])

  const handlePointerMove = useCallback((e: PointerEvent) => {
    if (pointerInteracting.current === null) return
    const deltaX = e.clientX - pointerInteracting.current.x
    const deltaY = e.clientY - pointerInteracting.current.y
    dragOffset.current = { phi: deltaX / 300, theta: deltaY / 1000 }
    const now = Date.now()
    if (lastPointer.current) {
      const dt = Math.max(now - lastPointer.current.t, 1)
      const maxV = 0.15
      velocity.current = {
        phi: Math.max(-maxV, Math.min(maxV, ((e.clientX - lastPointer.current.x) / dt) * 0.3)),
        theta: Math.max(-maxV, Math.min(maxV, ((e.clientY - lastPointer.current.y) / dt) * 0.08)),
      }
    }
    lastPointer.current = { x: e.clientX, y: e.clientY, t: now }
  }, [])

  const handlePointerUp = useCallback(() => {
    if (pointerInteracting.current !== null) {
      phiOffsetRef.current += dragOffset.current.phi
      thetaOffsetRef.current += dragOffset.current.theta
      dragOffset.current = { phi: 0, theta: 0 }
      lastPointer.current = null
    }
    pointerInteracting.current = null
    if (canvasRef.current) canvasRef.current.style.cursor = "grab"
    isPausedRef.current = false
  }, [])

  useEffect(() => {
    window.addEventListener("pointermove", handlePointerMove, { passive: true })
    window.addEventListener("pointerup", handlePointerUp, { passive: true })
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
    }
  }, [handlePointerMove, handlePointerUp])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const c = isDark ? THEME.dark : THEME.light
    const THETA = 0.2
    const SPEED = 0.003
    let globe: ReturnType<typeof createGlobe> | null = null
    let animationId = 0
    let phi = 0
    let ro: ResizeObserver | null = null

    const markers = MARKERS.map((m) => ({ location: m.location, size: 0.03, id: m.id }))
    const arcs = ARCS.map((a) => ({ from: a.from, to: a.to, id: a.id }))

    function init() {
      const width = canvas!.offsetWidth
      if (width === 0 || globe) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)

      globe = createGlobe(canvas!, {
        devicePixelRatio: dpr,
        width,
        height: width,
        phi: 0,
        theta: THETA,
        dark: c.dark,
        diffuse: 1.5,
        mapSamples: 16000,
        mapBrightness: c.mapBrightness,
        baseColor: c.baseColor,
        markerColor: c.markerColor,
        glowColor: c.glowColor,
        markerElevation: 0.01,
        markers,
        arcs,
        arcColor: c.arcColor,
        arcWidth: 0.5,
        arcHeight: 0.25,
        opacity: 0.8,
      })

      const animate = () => {
        if (!isPausedRef.current) {
          phi += SPEED
          if (Math.abs(velocity.current.phi) > 0.0001 || Math.abs(velocity.current.theta) > 0.0001) {
            phiOffsetRef.current += velocity.current.phi
            thetaOffsetRef.current += velocity.current.theta
            velocity.current.phi *= 0.95
            velocity.current.theta *= 0.95
          }
          const tMin = -0.4
          const tMax = 0.4
          if (thetaOffsetRef.current < tMin) thetaOffsetRef.current += (tMin - thetaOffsetRef.current) * 0.1
          else if (thetaOffsetRef.current > tMax) thetaOffsetRef.current += (tMax - thetaOffsetRef.current) * 0.1
        }
        globe!.update({
          phi: phi + phiOffsetRef.current + dragOffset.current.phi,
          theta: THETA + thetaOffsetRef.current + dragOffset.current.theta,
        })
        animationId = requestAnimationFrame(animate)
      }
      animate()
      setTimeout(() => {
        if (canvas) canvas.style.opacity = "1"
      })
    }

    if (canvas.offsetWidth > 0) {
      init()
    } else {
      ro = new ResizeObserver((entries) => {
        if (entries[0]?.contentRect.width > 0) {
          ro?.disconnect()
          init()
        }
      })
      ro.observe(canvas)
    }

    return () => {
      if (animationId) cancelAnimationFrame(animationId)
      ro?.disconnect()
      if (globe) globe.destroy()
    }
  }, [isDark])

  return (
    <div className="relative aspect-square w-full select-none">
      <canvas
        ref={canvasRef}
        onPointerDown={handlePointerDown}
        style={{
          width: "100%",
          height: "100%",
          cursor: "grab",
          opacity: 0,
          transition: "opacity 1.2s ease",
          borderRadius: "50%",
          touchAction: "none",
        }}
      />
      {CAN_ANCHOR &&
        MARKERS.map((m) => (
          <div
            key={m.id}
            style={
              {
                position: "absolute",
                positionAnchor: `--cobe-${m.id}`,
                bottom: "anchor(top)",
                left: "anchor(center)",
                translate: "-50% 0",
                marginBottom: 8,
                padding: "2px 6px",
                background: isDark ? "#052e22" : "#1a1a2e",
                color: isDark ? "#6ee7b7" : "#fff",
                border: isDark ? "1px solid rgba(52,211,153,.4)" : "none",
                fontFamily: "monospace",
                fontSize: "0.6rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                whiteSpace: "nowrap",
                pointerEvents: "none",
                opacity: `var(--cobe-visible-${m.id}, 0)`,
                filter: `blur(calc((1 - var(--cobe-visible-${m.id}, 0)) * 8px))`,
                transition: "opacity 0.8s, filter 0.8s",
              } as any
            }
          >
            {LABELS[m.id]}
          </div>
        ))}
    </div>
  )
}

/* ---------- ตัวที่เอาไปใช้ใน Landing ---------- */
export function GlobeHero() {
  const ref = useRef<HTMLDivElement>(null)
  const isDark = useIsDark(ref)
  return (
    <div ref={ref} className="flex w-full items-center justify-center overflow-hidden">
      <div className="w-full max-w-[460px]">
        <Globe key={isDark ? "dark" : "light"} isDark={isDark} />
      </div>
    </div>
  )
}
