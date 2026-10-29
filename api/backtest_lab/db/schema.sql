-- Backtest Lab schema (ข้อเสนอ — ยังไม่ได้รัน ต้องได้รับอนุมัติก่อน)
-- ตารางใหม่ล้วน ไม่แตะตารางเดิมของ Jatso

create table if not exists bt_price_cache (
  symbol      text primary key,
  source      text        not null,
  first_date  date        not null,
  last_date   date        not null,
  fetched_at  timestamptz not null,
  payload     text        not null        -- gzip+base64 ของ JSON แท่งราคา
);

create table if not exists bt_runs (
  id             uuid primary key,
  email          text        not null,
  status         text        not null check (status in ('queued','running','done','failed')),
  spec           jsonb       not null,
  spec_hash      text        not null,
  engine_version text        not null,
  result         jsonb,
  error          jsonb,
  created_at     timestamptz not null default now(),
  started_at     timestamptz,
  finished_at    timestamptz
);
create index if not exists bt_runs_email_created on bt_runs (email, created_at desc);
create index if not exists bt_runs_email_hash    on bt_runs (email, spec_hash);

-- service role ข้าม RLS อยู่แล้ว (โค้ดกรอง email ทุก query); เปิด RLS ไว้เพื่อกัน anon key เข้าถึง
alter table bt_price_cache enable row level security;
alter table bt_runs        enable row level security;

-- ROLLBACK:
--   drop table if exists bt_runs;
--   drop table if exists bt_price_cache;
