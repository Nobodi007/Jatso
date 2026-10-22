import { useCallback, useEffect, useState } from "react";

const API = "https://xspring-api.onrender.com/api/stock-book";

export type StockPosition = {
  symbol: string; qty: number; avg_cost: number; last: number;
  market_value: number; unrealized_pnl: number; unrealized_pct: number;
};
export type StockPortfolio = {
  initial_cash: number; cash: number; market_value: number;
  equity: number; pnl: number; pnl_pct: number;
  positions: StockPosition[];
};

export function useStockBook(getToken: () => string | null) {
  const [data, setData] = useState<StockPortfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const headers = useCallback(() => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${getToken() ?? ""}`,
  }), [getToken]);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}/portfolio`, { headers: headers() });
      if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { refresh(); }, [refresh]);

  const placeOrder = useCallback(async (o: {
    symbol: string; side: "buy" | "sell"; qty: number; price?: number | null;
  }) => {
    const r = await fetch(`${API}/trade`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(o),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail ?? `HTTP ${r.status}`);
    await refresh(); // อัปเดตเงินสดทันทีหลังซื้อขาย
    return j;
  }, [headers, refresh]);

  return { data, loading, error, refresh, placeOrder };
}
