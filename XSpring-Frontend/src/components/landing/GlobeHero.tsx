import { useEffect, useRef, useCallback, useState } from "react"
import createGlobe from "cobe"

type RGB = [number, number, number]
type Marker = { id: string; location: [number, number] }
type Arc = { id: string; from: [number, number]; to: [number, number] }

/* ---------- ข้อมูลบนโลก (อยู่นอกคอมโพเนนต์ เพื่อไม่ให้สร้างโลกใหม่ทุกครั้งที่ render) ---------- */
const MARKERS: Marker[] = [
  { id: "bkk", location: [13.7563, 100.5018] },
  { id: "sf", location: [37.7595, -122.4367] },
  { id: "nyc", location: [40.7128, -74.006] },
  { id: "tokyo", location: [35.6762, 139.6503] },
  { id: "london", location: [51.5074, -0.1278] },
  { id: "sydney", location: [-33.8688, 151.2093] },
  { id: "dubai", location: [25.2048, 55.2708] },
  { id: "saopaulo", location: [-23.5505, -46.6333] },
]

const ARCS: Arc[] = [
  { id: "bkk-tokyo", from: [13.7563, 100.5018], to: [35.6762, 139.6503] },
  { id: "bkk-london", from: [13.7563, 100.5018], to: [51.5074, -0.1278] },
  { id: "nyc-london", from: [40.7128, -74.006], to: [51.5074, -0.1278] },
  { id: "sf-tokyo", from: [37.7595, -122.4367], to: [35.6762, 139.6503] },
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
    baseColor: [1, 1, 1] as RGB,
    markerColor: [0.3, 0.45, 0.85] as RGB, // น้ำเงิน
    arcColor: [0.3, 0.45, 0.85] as RGB,
    glowColor: [0.94, 0.93, 0.91] as RGB,
    mapBrightness: 10,
  },
}

/* ---------- ตรวจธีมมืด/สว่างของเว็บ (class "dark" หรือ data-theme หรือค่าเครื่อง) ---------- */
function readIsDark(): boolean {
  if (typeof document === "undefined") return true
  const el = document.documentElement
  if (el.classList.contains("dark")) return true
  if (el.classList.contains("light")) return false
  const attr = el.getAttribute("data-theme")
  if (attr) return attr === "dark"
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true
}

function useIsDark(): boolean {
  const [isDark, setIsDark] = useState(readIsDark)
  useEffect(() => {
    const update = () => setIsDark(readIsDark())
    const obs = new MutationObserver(update)
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    })
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)")
    mq?.addEventListener?.("change", update)
    return () => {
      obs.disconnect()
      mq?.removeEventListener?.("change", update)
    }
  }, [])
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
    </div>
  )
}

/* ---------- ตัวที่เอาไปใช้ใน Landing ---------- */
export function GlobeHero() {
  const isDark = useIsDark()
  return (
    <div className="flex w-full items-center justify-center overflow-hidden">
      <div className="w-full max-w-[460px]">
        <Globe key={isDark ? "dark" : "light"} isDark={isDark} />
      </div>
    </div>
  )
}
