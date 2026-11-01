import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { estimateFee, findBroker, findPlan, type Broker, type FeeEstimate, type Plan } from "./brokerFees";

const PLAN_KEY = "xs.realPortfolio.plan.v1:"; // + broker.id (เก็บแผนที่เลือกไว้ในเครื่องนี้)

const readPlan = (brokerId?: string): string => {
  if (!brokerId) return "";
  try {
    return window.localStorage.getItem(PLAN_KEY + brokerId) ?? "";
  } catch {
    return "";
  }
};
const writePlan = (brokerId: string, planId: string) => {
  try {
    window.localStorage.setItem(PLAN_KEY + brokerId, planId);
  } catch {
    /* localStorage ใช้ไม่ได้ (private mode ฯลฯ) แผนจะกลับเป็นค่าแรกเมื่อโหลดใหม่ */
  }
};

export type BrokerFee = {
  broker?: Broker;
  plan?: Plan;
  setPlanId: (id: string) => void;
  vatOn: boolean;
  setVatOn: (v: boolean) => void;
  est: FeeEstimate | null;
  /** true = ผู้ใช้แก้ช่องค่าธรรมเนียมเอง ระบบจะไม่คำนวณทับ */
  manual: boolean;
  /** เรียกเมื่อผู้ใช้พิมพ์ในช่องค่าธรรมเนียม */
  markManual: () => void;
  /** กลับไปใช้ค่าที่ระบบคำนวณ */
  recalc: () => void;
};

/**
 * คำนวณค่าธรรมเนียมจากโบรกที่เลือก + จำนวนหุ้น + ราคา แล้วเขียนลงช่อง fee ผ่าน `setFee`
 * จนกว่าผู้ใช้จะแก้ช่องเอง (manual) และกลับมาคำนวณเมื่อเปลี่ยนโบรก/แผน หรือกด recalc
 */
export function useBrokerFee(brokerName: string, qty: number, price: number, setFee: (v: string) => void): BrokerFee {
  const broker = useMemo(() => findBroker(brokerName), [brokerName]);
  const [planId, setPlanIdState] = useState("");
  const [vatOn, setVatOn] = useState(false);
  const [manual, setManual] = useState(false);

  const setFeeRef = useRef(setFee);
  setFeeRef.current = setFee;

  useEffect(() => {
    setPlanIdState(readPlan(broker?.id));
    setManual(false);
  }, [broker?.id]);

  const plan = findPlan(broker, planId);

  useEffect(() => {
    setVatOn(!!plan?.rule?.vat);
    setManual(false);
  }, [broker?.id, plan?.id]);

  const est = useMemo(() => estimateFee(plan?.rule ?? null, qty, price, vatOn), [plan, qty, price, vatOn]);

  useEffect(() => {
    if (manual) return;
    setFeeRef.current(est ? est.fee.toFixed(2) : "0");
  }, [est, manual]);

  const setPlanId = useCallback(
    (id: string) => {
      setPlanIdState(id);
      if (broker) writePlan(broker.id, id);
    },
    [broker],
  );

  return {
    broker,
    plan,
    setPlanId,
    vatOn,
    setVatOn,
    est,
    manual,
    markManual: useCallback(() => setManual(true), []),
    recalc: useCallback(() => setManual(false), []),
  };
}
