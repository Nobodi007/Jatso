import { useSyncExternalStore } from "react"

// แท็บ "คริปโต | หุ้นสหรัฐ" ที่ใช้ร่วมกันทั้งหน้า landing (ช่องค้นหา ตารางหน้าแรก หน้า Market)
// เลือกที่ไหนก็จำไว้ แล้วทุกจุดเปลี่ยนตามกัน
export type AssetTab = "crypto" | "stocks"

const KEY = "nobodi:assetTab"
const listeners = new Set<() => void>()

const read = (): AssetTab => {
  try {
    return localStorage.getItem(KEY) === "stocks" ? "stocks" : "crypto"
  } catch {
    return "crypto"
  }
}

let current: AssetTab = read()

export function setAssetTab(next: AssetTab) {
  current = next
  try {
    localStorage.setItem(KEY, next)
  } catch {
    /* localStorage ใช้ไม่ได้ก็ใช้แค่ในหน้านี้ */
  }
  listeners.forEach((l) => l())
}

const subscribe = (cb: () => void) => {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}
const getSnapshot = () => current

export function useAssetTab(): [AssetTab, (next: AssetTab) => void] {
  const tab = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  return [tab, setAssetTab]
}
