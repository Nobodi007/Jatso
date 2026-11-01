/**
 * โบรกเกอร์ไทยที่ซื้อหุ้นสหรัฐได้ + สูตรคำนวณค่าคอมมิชชั่นโดยประมาณ
 *
 * - ค่าที่ได้เป็น "ค่าประมาณ" เท่านั้น ค่าจริงคือที่โบรกหักตามใบยืนยันรายการ (ช่อง fee แก้ทับได้เสมอ)
 * - คิดเฉพาะค่าคอมมิชชั่น ไม่รวมค่าฝั่งขาย (SEC fee, FINRA TAF), ADR fee, ค่าแปลงเงิน/โอน
 * - rate = null แปลว่ายังไม่มีอัตราที่ยืนยันแล้ว ระบบจะไม่เดา ให้ผู้ใช้กรอกเอง
 * - ข้อมูลอ่านจากภาพหน้าเปรียบเทียบค่าธรรมเนียมและเอกสารของโบรก ตรวจ `asOf` และ `checks` ก่อนเชื่อตัวเลข
 */

export type Tier = {
  /** ใช้ tier นี้เมื่อราคาหุ้น >= minPrice (USD) */
  minPrice: number;
  /** USD ต่อหุ้น */
  perShare?: number;
  /** เปอร์เซ็นต์ของมูลค่า เช่น 0.10 = 0.10% */
  pct?: number;
};

export type FeeRule = {
  tiers: Tier[]; // เรียงตาม minPrice จากน้อยไปมาก
  /** ค่าขั้นต่ำต่อรายการ (USD) */
  min?: number;
  /** อัตราข้างบนยังไม่รวม VAT 7% (true = บวก VAT ให้) */
  vat: boolean;
};

export type Plan = {
  id: string;
  label: string;
  /** null = ไม่มีอัตราที่ยืนยันแล้ว */
  rule: FeeRule | null;
  note?: string;
};

export type Broker = {
  id: string;
  /** ชื่อที่บันทึกลง real_accounts.broker (ต้องยาว 1–40 ตัวอักษร) */
  name: string;
  /** ชื่อเก่าที่เคยบันทึกไว้แล้วให้จับคู่กับโบรกนี้ */
  aliases?: string[];
  /** ไฟล์ใน public/brokers */
  logo: string;
  /** โลโก้สีขาว ต้องวางบนพื้นมืด */
  logoOnDark?: boolean;
  plans: Plan[];
  /** สิ่งที่ผู้ใช้ควรรู้ก่อนเชื่อค่าประมาณ */
  checks?: string[];
};

export const DATA_AS_OF = "2025-12 (อ่านจากภาพหน้าจอและเอกสารโบรก ยังไม่ได้ตรวจกับหน้าทางการ)";

export const VAT_RATE = 0.07;

const perShare = (rate: number, min?: number, vat = false): FeeRule => ({ tiers: [{ minPrice: 0, perShare: rate }], min, vat });
const pct = (p: number, min?: number, vat = false): FeeRule => ({ tiers: [{ minPrice: 0, pct: p }], min, vat });

export const BROKERS: Broker[] = [
  {
    id: "webull-th",
    name: "Webull Thailand",
    aliases: ["Webull"],
    logo: "webull.png",
    plans: [
      { id: "std", label: "0.10% ไม่มีขั้นต่ำ", rule: pct(0.1, undefined, true) },
      {
        id: "overnight-015",
        label: "Overnight 0.15% (ถ้าประกาศใช้แล้ว)",
        rule: pct(0.15, undefined, true),
        note: "หน้าเปรียบเทียบระบุว่า Overnight (20:00-04:00 ET) ตอนนี้ยัง 0.10% และจะเปลี่ยนเป็น 0.15% ภายหลังตามประกาศ",
      },
    ],
    checks: ["ขั้นต่ำ 5 USD ต่อออเดอร์เป็นขนาดออเดอร์ขั้นต่ำ ไม่ใช่ค่าคอมขั้นต่ำ"],
  },
  {
    id: "krungsri",
    name: "Krungsri Securities",
    logo: "krungsri.png",
    plans: [
      {
        id: "online",
        label: "ออนไลน์",
        rule: {
          tiers: [
            { minPrice: 0, perShare: 0.04 },
            { minPrice: 20, perShare: 0.07 },
          ],
          min: 3.99,
          vat: true,
        },
      },
    ],
    checks: ["เศษหุ้น (แฟร็กชั่น) $1.99 อ่านไม่ชัดว่าต่อออเดอร์หรือไม่ ระบบไม่คิดให้"],
  },
  {
    id: "beyond",
    name: "Beyond Securities",
    logo: "beyond.webp",
    plans: [{ id: "self", label: "ส่งคำสั่งเอง", rule: perShare(0.08, 4.99, true) }],
    checks: ["เอกสารที่อ่านลงวันที่ 18 ธ.ค. 2024 อาจเก่า", "อัตราผ่านผู้แนะนำ $0.10/หุ้น ยังไม่ได้ใส่ (ไม่ทราบขั้นต่ำ)"],
  },
  {
    id: "kbank",
    name: "Kasikorn Securities",
    logo: "kbank.svg",
    logoOnDark: true,
    plans: [
      {
        id: "online",
        label: "ออนไลน์",
        rule: {
          tiers: [
            { minPrice: 0, perShare: 0.02 },
            { minPrice: 20, perShare: 0.08 },
          ],
          min: 4.99,
          vat: false,
        },
      },
    ],
    checks: ["ไม่ชัดว่าอัตรารวมหรือไม่รวม VAT ติ๊ก +VAT เองได้"],
  },
  {
    id: "tisco",
    name: "TISCO Securities",
    logo: "tisco.webp",
    plans: [{ id: "std", label: "มาตรฐาน", rule: perShare(0.08, 4.99, false) }],
    checks: ["ค่าเท่ากับ Beyond/KS ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "innovestx",
    name: "InnovestX",
    logo: "innovestx.png",
    plans: [{ id: "std", label: "มาตรฐาน", rule: perShare(0.08, 4.99, true) }],
  },
  {
    id: "bualuang",
    name: "Bualuang Securities",
    logo: "bualuang.png",
    plans: [
      { id: "global-invest", label: "Global Invest", rule: perShare(0.08, 10, false) },
      { id: "global-trade-master", label: "Global Trade Master", rule: perShare(0.08, 3, false) },
    ],
    checks: ["เศษหุ้น 1 USD/รายการ ระบบไม่คิดให้", "ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "finansia",
    name: "Finansia Syrus",
    logo: "finansia.svg",
    plans: [{ id: "std", label: "หุ้นสหรัฐปกติ", rule: perShare(0.08, undefined, false) }],
    checks: ["เศษหุ้นคิด 1 (ตารางไม่ระบุหน่วย) ระบบไม่คิดให้", "ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "yuanta",
    name: "Yuanta Securities",
    logo: "yuanta.png",
    plans: [
      { id: "online", label: "ออนไลน์ 0.05/หุ้น", rule: perShare(0.05, 1.5, false) },
      { id: "offline", label: "Offline 0.10%", rule: pct(0.1, 30, false) },
    ],
    checks: ["เศษหุ้น 1 USD/รายการ ระบบไม่คิดให้", "ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "dime",
    name: "Dime!",
    logo: "dime.png",
    plans: [
      {
        id: "std",
        label: "หลังรายการฟรีของเดือน",
        rule: {
          tiers: [
            { minPrice: 0, perShare: 0.01 },
            { minPrice: 6.67, pct: 0.15 },
          ],
          vat: false,
        },
        note: "ฟรี 1 รายการ/เดือน (รวมหุ้นไทยและออปชันสหรัฐ) ระบบไม่รู้ว่ารายการไหนเป็นรายการฟรี ถ้าเป็นรายการฟรีให้ใส่ 0",
      },
    ],
    checks: ["ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "liberator",
    name: "Liberator",
    logo: "liberator.png",
    logoOnDark: true,
    plans: [{ id: "std", label: "0.10% ของมูลค่า", rule: pct(0.1, undefined, false) }],
    checks: ["ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "pi",
    name: "Pi Securities",
    logo: "pi.png",
    plans: [{ id: "std", label: "0.20% ไม่มีขั้นต่ำ", rule: pct(0.2, undefined, true) }],
  },
  {
    id: "daol",
    name: "DAOL Securities",
    logo: "daol.png",
    plans: [
      { id: "self", label: "ส่งคำสั่งเอง 0.10%", rule: pct(0.1, 1, false) },
      { id: "advisor", label: "ผ่านที่ปรึกษา 0.35%", rule: pct(0.35, undefined, false), note: "ไม่ทราบค่าขั้นต่ำของแบบผ่านที่ปรึกษา" },
    ],
    checks: ["ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "aira",
    name: "AIRA Securities",
    logo: "aira.png",
    plans: [{ id: "std", label: "มาตรฐาน", rule: perShare(0.04, 10, false) }],
    checks: ["ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "ktx",
    name: "Krungthai KTX",
    logo: "ktx.png",
    plans: [{ id: "std", label: "all-in", rule: perShare(0.06, 10, false) }],
    checks: ["เขียนว่า all-in fees แต่หมายเหตุถูกตัด ไม่รู้ว่ารวมอะไรบ้าง"],
  },
  {
    id: "cgsi",
    name: "CGS International",
    logo: "cgsi.png",
    logoOnDark: true,
    plans: [{ id: "std", label: "มาตรฐาน", rule: perShare(0.01, 12, false) }],
    checks: ["$0.01 อ่านเป็นต่อหุ้นตามบริบท ควรตรวจซ้ำ", "ฝั่งขายมี SEC fee 0.00278% ระบบไม่คิดให้"],
  },
  {
    id: "dbsv",
    name: "DBS Vickers",
    logo: "dbsv.svg",
    plans: [
      { id: "online", label: "ออนไลน์ 0.25%", rule: pct(0.25, 20, false) },
      { id: "phone", label: "โทรสั่ง 0.40%", rule: pct(0.4, 20, false), note: "ขั้นต่ำของแบบโทรสั่งสมมติเท่าแบบออนไลน์ ($20) ควรตรวจซ้ำ" },
    ],
    checks: ["ไม่ชัดว่ารวมหรือไม่รวม VAT"],
  },
  {
    id: "asiaplus",
    name: "Asia Plus",
    logo: "asiaplus.svg",
    logoOnDark: true,
    plans: [
      { id: "standard", label: "Standard 0.50%", rule: pct(0.5, undefined, false) },
      { id: "silver", label: "Silver 0.35%", rule: pct(0.35, undefined, false) },
      { id: "gold", label: "Gold 0.25%", rule: pct(0.25, undefined, false) },
      { id: "diamond", label: "Diamond 0.15%", rule: pct(0.15, undefined, false) },
    ],
    checks: ["ไม่เห็นค่าขั้นต่ำในภาพ จึงไม่ได้ใส่ขั้นต่ำ", "ข้อมูลลงวันที่ 8 ธ.ค. 2568"],
  },
  // ---- Maybank, Phillip, UOB Kay Hian: เพิ่มจากหน้าทางการที่ผู้ใช้ส่งมา ----
  {
    id: "maybank",
    name: "Maybank Securities",
    logo: "maybank.svg",
    plans: [{ id: "std", label: "0.30%", rule: pct(0.3, undefined, true) }],
    checks: [
      "เอกสาร (ม.ค. 2025) ระบุค่าคอมและค่าใช้จ่ายทั้งหมดบวก VAT 7%",
      "ขั้นต่ำสหรัฐ 600 ต่อรายการ (เอกสารไม่ระบุหน่วย น่าจะเป็นบาท ≈ 17-19 USD) ระบบไม่ได้ใส่ขั้นต่ำ ออเดอร์เล็กจึงจะคิดต่ำกว่าจริงมาก",
    ],
  },
  {
    id: "phillip",
    name: "Phillip Securities",
    logo: "phillip.svg",
    plans: [
      { id: "online", label: "ออนไลน์ 0.20% (ขั้นต่ำ $8)", rule: pct(0.2, 8, true) },
      { id: "dealer", label: "ผ่านเทรดเดอร์ 0.35% (ขั้นต่ำ $20)", rule: pct(0.35, 20, true) },
    ],
    checks: [
      "หน้าเว็บระบุว่าอัตรายังไม่รวมค่าธรรมเนียมและภาษี และมีผลตั้งแต่ 1 เม.ย. 2565 ควรตรวจว่ายังใช้อยู่",
      "ฝั่งขายมีค่าอีก $0.000195/หุ้น สูงสุด $9.79 (ตั้งแต่ 1 ม.ค. 2026) ระบบไม่คิดให้",
    ],
  },
  {
    id: "uob",
    name: "UOB Kay Hian",
    logo: "uob.png",
    plans: [
      {
        id: "online",
        label: "ออนไลน์ (Global Trade)",
        rule: {
          tiers: [
            { minPrice: 0, perShare: 0.08 },
            { minPrice: 10, pct: 0.2 },
          ],
          min: 8,
          vat: false,
        },
      },
      {
        id: "dealer",
        label: "ผ่าน IC/RM/Dealer",
        rule: {
          tiers: [
            { minPrice: 0, perShare: 0.1 },
            { minPrice: 10, pct: 0.25 },
          ],
          min: 10,
          vat: false,
        },
      },
    ],
    checks: ["หุ้นราคา < $10 คิด 8 เซนต์/หุ้น (ผ่านเทรดเดอร์ 10 เซนต์) ส่วน > $10 คิด % ราคา $10 พอดีหน้าเว็บไม่ระบุ ระบบใช้ %", "ไม่ชัดว่ารวมหรือไม่รวม VAT และหน้าเว็บไม่แสดงวันที่"],
  },
  // ---- ยังไม่มีอัตราที่ยืนยันแล้ว: ให้กรอกค่าธรรมเนียมเอง ----
  {
    id: "sbito",
    name: "SBITO",
    logo: "sbito.png",
    logoOnDark: false,
    plans: [{ id: "none", label: "ยังไม่ยืนยันอัตรา", rule: null }],
    checks: ["หน้าเปรียบเทียบระบุว่ายังไม่ยืนยันอัตราค่าคอมหุ้นสหรัฐ"],
  },
];

const norm = (s: string) => s.trim().toLowerCase();

export function findBroker(name: string | null | undefined): Broker | undefined {
  const n = norm(name ?? "");
  if (!n) return undefined;
  return BROKERS.find((b) => norm(b.name) === n || (b.aliases ?? []).some((a) => norm(a) === n));
}

export function findPlan(broker: Broker | undefined, planId: string | null | undefined): Plan | undefined {
  if (!broker) return undefined;
  return broker.plans.find((p) => p.id === planId) ?? broker.plans[0];
}

export type FeeEstimate = {
  /** ค่าประมาณ (USD ปัดเป็นเซ็นต์) */
  fee: number;
  /** ข้อความอธิบายสั้น ๆ ว่าคิดมาอย่างไร */
  basis: string;
};

const cents = (x: number) => Math.round((x + Number.EPSILON) * 100) / 100;

function tierFor(rule: FeeRule, price: number): Tier {
  let hit = rule.tiers[0];
  for (const t of rule.tiers) if (price >= t.minPrice) hit = t;
  return hit;
}

/**
 * คำนวณค่าคอมมิชชั่นโดยประมาณ คืน null ถ้าคำนวณไม่ได้ (ไม่มีอัตรา หรือ qty/price ไม่ถูกต้อง)
 * `addVat` = บวก VAT 7% หรือไม่ (ผู้ใช้เปลี่ยนค่าตั้งต้นของโบรกได้)
 */
export function estimateFee(rule: FeeRule | null, qty: number, price: number, addVat: boolean): FeeEstimate | null {
  if (!rule || !(qty > 0) || !(price > 0) || !Number.isFinite(qty) || !Number.isFinite(price)) return null;
  const t = tierFor(rule, price);
  const parts: string[] = [];
  let base: number;
  if (t.perShare !== undefined) {
    base = t.perShare * qty;
    parts.push(`$${t.perShare}/หุ้น`);
  } else if (t.pct !== undefined) {
    base = (t.pct / 100) * qty * price;
    parts.push(`${t.pct}%`);
  } else {
    return null;
  }
  if (rule.min !== undefined && base < rule.min) {
    base = rule.min;
    parts.push(`ขั้นต่ำ $${rule.min}`);
  }
  let fee = base;
  if (addVat) {
    fee = base * (1 + VAT_RATE);
    parts.push("+VAT 7%");
  }
  return { fee: cents(fee), basis: parts.join(" · ") };
}

const tierText = (t: Tier) => (t.perShare !== undefined ? `$${t.perShare}/หุ้น` : `${t.pct}% ของมูลค่า`);

/** อธิบายอัตราเป็นข้อความ เช่น "0.1% ของมูลค่า · ไม่มีขั้นต่ำ · +VAT 7%" */
export function describeRule(rule: FeeRule, addVat: boolean): string {
  const parts: string[] = [];
  if (rule.tiers.length === 1) {
    parts.push(tierText(rule.tiers[0]));
  } else {
    parts.push(
      rule.tiers
        .map((t, i) => `${t.minPrice === 0 ? `ราคา < $${rule.tiers[i + 1].minPrice}` : `ราคา ≥ $${t.minPrice}`}: ${tierText(t)}`)
        .join(" · "),
    );
  }
  parts.push(rule.min !== undefined ? `ขั้นต่ำ $${rule.min}` : "ไม่มีขั้นต่ำ");
  if (addVat) parts.push("+VAT 7%");
  return parts.join(" · ");
}

/** ค่าขั้นต่ำต่อรายการ (รวม VAT ถ้าเลือก) คืน null ถ้าโบรกนี้ไม่มีขั้นต่ำ */
export function minFee(rule: FeeRule, addVat: boolean): number | null {
  return rule.min !== undefined ? cents(rule.min * (addVat ? 1 + VAT_RATE : 1)) : null;
}
