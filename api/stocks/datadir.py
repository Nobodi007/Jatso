"""ที่เก็บไฟล์ถาวรของ screener (snapshot, ราคาย้อนหลัง, รายชื่อหุ้น)

ลำดับ: ตัวแปร DATA_DIR → /data (ถ้าเขียนได้ เช่น mount volume) → /tmp
ถ้าโฮสต์ของคุณลบดิสก์ทุกครั้งที่รีสตาร์ท (เช่นแผนฟรีบางเจ้า) ข้อมูลจะหายและต้องดึงใหม่
"""
import logging
import os

log = logging.getLogger("stocks.datadir")


def _pick() -> str:
    env = os.getenv("DATA_DIR")
    for d in (env, "/data"):
        if d and os.path.isdir(d) and os.access(d, os.W_OK):
            return d
    if env:
        try:
            os.makedirs(env, exist_ok=True)
            return env
        except OSError:
            pass
    return "/tmp"


DATA_DIR = _pick()
if DATA_DIR == "/tmp":
    log.warning("DATA_DIR=/tmp (ชั่วคราว) ข้อมูลจะหายเมื่อเซิร์ฟเวอร์รีสตาร์ท ตั้ง DATA_DIR ไปที่ volume ถาวร")


def path(name: str) -> str:
    return os.path.join(DATA_DIR, name)
