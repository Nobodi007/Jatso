import type { ReactNode } from "react";
import BrokerPicker from "./BrokerPicker";
import { DATA_AS_OF } from "./brokerFees";
import type { BrokerFee } from "./useBrokerFee";

type Props = {
  /** ชื่อโบรกที่บันทึกอยู่ */
  broker: string;
  /** เลือกโบรกใหม่ (หน้าหลักเป็นคนเรียก PUT /account) */
  onSelectBroker: (name: string) => void;
  busy: boolean;
  fee: BrokerFee;
};

export default function BrokerPanel({ broker, onSelectBroker, busy, fee }: Props) {
  const b = fee.broker;
  const rule = fee.plan?.rule ?? null;
  const notes = [fee.plan?.note, ...(b?.checks ?? [])].filter((x): x is string => !!x);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full max-w-sm">
          <span className="text-xs text-muted-foreground">โบรกเกอร์</span>
          <div className="mt-1">
            <BrokerPicker value={broker} onSelect={onSelectBroker} disabled={busy} />
          </div>
        </div>

        {b && b.plans.length > 1 && (
          <label className="block text-sm">
            <span className="text-xs text-muted-foreground">แผน/ช่องทาง</span>
            <select
              className="mt-1 block rounded-xl border border-border bg-background px-3 py-2 text-sm"
              value={fee.plan?.id ?? ""}
              onChange={(e: { target: { value: string } }) => fee.setPlanId(e.target.value)}
            >
              {b.plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        )}

        {rule && (
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={fee.vatOn} onChange={(e: { target: { checked: boolean } }) => fee.setVatOn(e.target.checked)} />
            <span>บวก VAT 7%</span>
          </label>
        )}
      </div>

      {b && !rule && (
        <p className="text-sm text-amber-500">ยังไม่มีอัตราค่าคอมของ {b.name} ในระบบ ช่องค่าธรรมเนียมจึงไม่คำนวณให้ ให้กรอกตามใบยืนยันรายการของโบรก</p>
      )}
      {!b && broker && <p className="text-sm text-muted-foreground">ไม่คำนวณค่าธรรมเนียมให้โบรกนี้ ให้กรอกเอง</p>}

      {(notes.length > 0 || b) && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer select-none">ข้อควรรู้เรื่องค่าประมาณ</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>ค่าที่ได้เป็นค่าคอมมิชชั่นโดยประมาณ ค่าจริงคือที่โบรกหักตามใบยืนยันรายการ แก้ช่องค่าธรรมเนียมได้เสมอ</li>
            <li>ไม่รวมค่าฝั่งขาย (SEC fee, FINRA TAF), ADR fee และค่าแปลงเงิน/โอน ถ้าโบรกหักแยก ให้บวกเข้าช่องเอง</li>
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
            <li>ที่มาข้อมูล: {DATA_AS_OF}</li>
          </ul>
        </details>
      )}
    </div>
  );
}

/** ข้อความใต้ช่องค่าธรรมเนียม: แสดงตัวเลขที่คำนวณได้ หรืออัตราของโบรกที่เลือก */
export function FeeHint({ fee, side }: { fee: BrokerFee; side: "buy" | "sell" }) {
  const rule = fee.plan?.rule ?? null;
  let body: ReactNode;
  if (fee.manual) {
    body = (
      <>
        กรอกเอง{" "}
        <button type="button" className="underline" onClick={fee.recalc}>
          คำนวณใหม่
        </button>
      </>
    );
  } else if (!fee.broker) {
    body = "โบรกนี้ไม่มีอัตราในระบบ กรอกเอง";
  } else if (!rule) {
    body = `${fee.broker.name}: ยังไม่มีอัตราในระบบ กรอกตามใบยืนยันรายการ`;
  } else if (fee.est) {
    body = (
      <>
        <span className="font-medium text-foreground">ประมาณ ${fee.est.fee.toFixed(2)}</span> · {fee.est.basis}
      </>
    );
  } else {
    body = (
      <>
        อัตรา {fee.describe}
        {fee.floor !== null ? " · ใส่ขั้นต่ำให้ก่อน จะคำนวณใหม่เมื่อใส่จำนวนและราคา" : " · ใส่จำนวนและราคาเพื่อให้คำนวณ"}
      </>
    );
  }
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      {body}
      {side === "sell" && " · ฝั่งขายอาจมี SEC fee/TAF เพิ่ม"}
    </p>
  );
}
