"""ค่าคงที่และเพดานทั้งหมดของ Backtest Lab (แพ็กเกจนี้แยกขาดจาก Backtest เดิมและ Risk Center)"""
ENGINE_VERSION = "backtest-lab/0.1.0"
SPEC_VERSION = 1

BENCHMARK = "^GSPC"                 # S&P 500 Price Index (ไม่ใช่ SPY)
FULL_HISTORY_START = "1980-01-01"   # ดึงประวัติทั้งหมดครั้งเดียวแล้ว cache (Yahoo ส่งเท่าที่มี)

# เพดานต่อการรัน (ป้องกัน rate limit / CPU)
MAX_SYMBOLS = 30
MAX_YEARS = 40
MIN_TRADING_DAYS = 20
MIN_CAPITAL, MAX_CAPITAL = 1_000.0, 10_000_000_000.0
MAX_COMMISSION_BPS = 200.0
MAX_SLIPPAGE_BPS = 500.0
MAX_SPEC_BYTES = 20_000
MAX_FILL_DAYS = 5                    # ช่องว่างข้อมูลสูงสุดที่ยอม forward-fill ติดกัน
MIN_TRADE_NOTIONAL = 1.0             # ไม่ส่งคำสั่งที่มูลค่าต่ำกว่านี้ (USD)

# ค่า default ที่ประกาศชัด (ผู้ใช้ตั้งเองได้)
DEFAULT_COMMISSION_BPS = 0.0
DEFAULT_SLIPPAGE_BPS = 5.0

# cache ราคา
PRICE_TTL_SECONDS = 12 * 3600
OVERLAP_DAYS = 7                     # ดึงซ้อนทับเพื่อตรวจว่าราคาเก่าถูกปรับ (split) หรือไม่
OVERLAP_TOL = 1e-3

# งานและการจำกัด
MAX_CONCURRENT_RUNS = 2
RUN_TIMEOUT_SECONDS = 120
RATE_LIMIT_RUNS = 6
RATE_LIMIT_WINDOW_SECONDS = 600
MAX_STORED_RUNS_PER_USER = 50
MAX_TRADES_IN_RESULT = 2000
