import React, { useState, useEffect, useRef } from 'react';
import { Wallet, Activity, TrendingUp, TrendingDown, ChevronDown, Percent } from 'lucide-react';

interface ExchangePanelProps {
  key?: string;
  exchange: string;
  symbol: string;
  theme: any;
  isSimulated?: boolean;
}

const EXCHANGE_THEMES: Record<string, { color: string; bg: string }> = {
  binance: { color: "#F3BA2F", bg: "rgba(243, 186, 47, 0.05)" },
  bybit: { color: "#F7A600", bg: "rgba(247, 166, 0, 0.05)" },
  okx: { color: "#000000", bg: "rgba(255, 255, 255, 0.05)" },
  bitget: { color: "#00F0FF", bg: "rgba(0, 240, 255, 0.05)" },
  kucoinfutures: { color: "#24AE8F", bg: "rgba(36, 174, 143, 0.05)" },
  gate: { color: "#E15241", bg: "rgba(225, 82, 65, 0.05)" },
  htx: { color: "#0052FF", bg: "rgba(0, 82, 255, 0.05)" },
  superex: { color: "#FFD700", bg: "rgba(255, 215, 0, 0.05)" },
};

function ExchangePanel({ exchange, symbol, theme, isSimulated }: ExchangePanelProps) {
  const exTheme = EXCHANGE_THEMES[exchange] || { color: theme.flow.primary, bg: "rgba(255,255,255,0.05)" };
  
  const [balance, setBalance] = useState<number | string>("...");
  const [amount, setAmount] = useState<string>("");
  const [price, setPrice] = useState<string>("");
  const [orderType, setOrderType] = useState<string>("market");
  const [leverage, setLeverage] = useState<number>(10);
  const [marginMode, setMarginMode] = useState<string>("isolated");
  const [positionMode, setPositionMode] = useState<string>("one-way"); // or hedge
  const [tpPrice, setTpPrice] = useState<string>("");
  const [slPrice, setSlPrice] = useState<string>("");
  const [showTpSl, setShowTpSl] = useState(false);
  
  const [ticker, setTicker] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ msg: string; type: 'info' | 'error' | 'success' } | null>(null);

  const fetchTicker = async () => {
    try {
      const resp = await fetch(`/api/market/ticker/${exchange}/${symbol}`);
      if (resp.ok) setTicker(await resp.json());
    } catch (e) {}
  };

  const fetchBalance = async () => {
    try {
      const resp = await fetch("/api/trade/balances");
      const data = await resp.json();
      setBalance(data.balances[exchange] ?? 0);
    } catch (e) {
      console.error("Balance fetch failed", e);
    }
  };

  useEffect(() => {
    fetchBalance();
    fetchTicker();
    const tickerInv = setInterval(fetchTicker, 3000);
    const balInv = setInterval(fetchBalance, 10000);
    return () => { clearInterval(tickerInv); clearInterval(balInv); };
  }, [exchange, symbol]);

  const handleExecute = async (side: 'BUY' | 'SELL') => {
    setLoading(true);
    setStatus({ msg: `Dispatching ${side}...`, type: 'info' });
    try {
      const resp = await fetch("/api/trade/place", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exchange,
          symbol,
          side,
          order_type: orderType,
          amount: parseFloat(amount),
          price: price ? parseFloat(price) : null,
          leverage,
          margin_mode: marginMode,
          tp_price: tpPrice ? parseFloat(tpPrice) : null,
          sl_price: slPrice ? parseFloat(slPrice) : null
        })
      });
      const result = await resp.json();
      if (resp.ok) {
        setStatus({ msg: `EX: ${result.order_id || 'OK'}`, type: 'success' });
        fetchBalance();
      } else {
        setStatus({ msg: result.detail || "Error", type: 'error' });
      }
    } catch (e: any) {
      setStatus({ msg: e.message, type: 'error' });
    }
    setLoading(false);
  };

  const setPercentAmount = (p: number) => {
    if (typeof balance !== 'number' || !ticker?.last) return;
    const notional = balance * leverage * (p / 100);
    const qty = notional / ticker.last;
    setAmount(qty.toFixed(3));
  };

  return (
    <div style={{
      background: "rgba(10, 15, 25, 0.6)",
      border: `1px solid ${exTheme.color}30`,
      borderRadius: 16,
      padding: 16,
      display: "grid",
      gridTemplateColumns: "1fr 120px",
      gap: 16,
      backdropFilter: "blur(8px)",
      boxShadow: `0 10px 40px ${exTheme.color}10`,
      minHeight: 320
    }}>
      {/* LEFT: Execution Form */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {/* Header & Mode Toggles */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
             <span style={{ fontSize: 10, fontWeight: 900, color: exTheme.color, letterSpacing: 1 }}>{exchange.toUpperCase()}</span>
             {isSimulated && (
               <span style={{ 
                 fontSize: 7, fontWeight: 900, background: "rgba(255,b255,255,0.1)", 
                 color: "rgba(255,255,255,0.4)", padding: "1px 4px", borderRadius: 3,
                 border: "1px solid rgba(255,255,255,0.05)"
               }}>SIM</span>
             )}
          </div>
          <div style={{ fontSize: 9, fontWeight: 800, color: "rgba(255,255,255,0.3)" }}>
            AVAIL: <span style={{ color: "#fff" }}>${typeof balance === 'number' ? balance.toFixed(1) : "---"}</span>
          </div>
        </div>

        <div style={{ display: "flex", gap: 6 }}>
          <div style={{ 
            background: "rgba(255,b255,b255,0.05)", padding: "4px 8px", borderRadius: 4, 
            fontSize: 8, fontWeight: 900, color: theme.flow.primary, display: "flex", alignItems: "center", gap: 2, cursor: "pointer"
          }}>
            {marginMode.toUpperCase()} <ChevronDown size={8} />
          </div>
          <div style={{ 
            background: "rgba(255,b255,b255,0.05)", padding: "4px 8px", borderRadius: 4, 
            fontSize: 8, fontWeight: 900, color: theme.signal.success, display: "flex", alignItems: "center", gap: 2, cursor: "pointer"
          }}>
            {leverage}X <ChevronDown size={8} />
          </div>
          <div style={{ 
            background: "rgba(255,b255,b255,0.05)", padding: "4px 8px", borderRadius: 4, 
            fontSize: 8, fontWeight: 900, color: "rgba(255,255,255,0.5)", display: "flex", alignItems: "center", gap: 2, cursor: "pointer"
          }}>
            {positionMode.toUpperCase()} <ChevronDown size={8} />
          </div>
        </div>

        {/* Price Inputs */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ position: "relative" }}>
             <select 
               value={orderType} 
               onChange={(e) => setOrderType(e.target.value)}
               style={{ width: "100%", background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.05)", padding: "8px 12px", borderRadius: 8, color: "#fff", fontSize: 11, outline: "none" }}
             >
                <option value="market">Market Price</option>
                <option value="limit">Limit Order</option>
             </select>
          </div>

          <div style={{ position: "relative" }}>
             <input 
               type="number" placeholder="Qty" value={amount} onChange={(e) => setAmount(e.target.value)}
               style={{ width: "100%", background: "rgba(0,0,0,0.3)", border: `1px solid ${exTheme.color}20`, padding: "10px", borderRadius: 8, color: "#fff", fontSize: 12 }}
             />
             <span style={{ position: "absolute", right: 12, top: 12, fontSize: 9, color: "rgba(255,255,255,0.2)" }}>CONT</span>
          </div>
        </div>

        {/* Percentage Slider */}
        <div style={{ display: "flex", justifyContent: "space-between", padding: "0 4px", position: "relative", marginTop: 4 }}>
           <div style={{ position: "absolute", top: 5, left: 0, right: 0, height: 2, background: "rgba(255,255,255,0.1)", zIndex: 0 }} />
           {[0, 25, 50, 75, 100].map((p, i) => (
             <div 
               key={p} 
               onClick={() => setPercentAmount(p)}
               style={{ 
                 width: 12, height: 12, borderRadius: "50%", background: i === 0 ? "#fff" : "rgba(15, 23, 42, 1)", 
                 border: `2px solid ${i === 0 ? exTheme.color : "rgba(255,255,255,0.1)"}`,
                 zIndex: 1, cursor: "pointer"
               }} 
             />
           ))}
        </div>

        {/* TP/SL Toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
           <input type="checkbox" checked={showTpSl} onChange={(e) => setShowTpSl(e.target.checked)} />
           <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)" }}>TP/SL PROTECTION</span>
        </div>

        {showTpSl && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <input type="number" placeholder="Take Profit" value={tpPrice} onChange={(e) => setTpPrice(e.target.value)} style={{ background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.05)", padding: "8px", borderRadius: 6, color: theme.signal.success, fontSize: 10 }} />
            <input type="number" placeholder="Stop Loss" value={slPrice} onChange={(e) => setSlPrice(e.target.value)} style={{ background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.05)", padding: "8px", borderRadius: 6, color: theme.signal.danger, fontSize: 10 }} />
          </div>
        )}

        {/* Execution Buttons */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: "auto" }}>
           <button 
             onClick={() => handleExecute('BUY')} disabled={loading || !amount}
             style={{ 
               background: theme.signal.success, color: "#fff", border: "none", padding: "12px", borderRadius: 8, 
               fontWeight: 900, cursor: "pointer", display: "flex", justifyContent: "center", gap: 10,
               fontSize: 12, opacity: (loading || !amount) ? 0.3 : 1, transition: "transform 0.1s"
             }}
           >
             LONG {symbol}
           </button>
           <button 
             onClick={() => handleExecute('SELL')} disabled={loading || !amount}
             style={{ 
               background: theme.signal.danger, color: "#fff", border: "none", padding: "12px", borderRadius: 8, 
               fontWeight: 900, cursor: "pointer", display: "flex", justifyContent: "center", gap: 10,
               fontSize: 12, opacity: (loading || !amount) ? 0.3 : 1
             }}
           >
             SHORT {symbol}
           </button>
        </div>
      </div>

      {/* RIGHT: Market Data Feed (Exchange-Branded) */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12, borderLeft: `1px solid ${exTheme.color}20`, paddingLeft: 16 }}>
         {/* Price Display */}
         <div style={{ textAlign: "center", marginBottom: 8 }}>
            <div style={{ 
              fontSize: 16, fontWeight: 900, 
              color: ticker?.percentage >= 0 ? theme.signal.success : theme.signal.danger 
            }}>
              {ticker?.last || "---"}
            </div>
            <div style={{ fontSize: 9, color: "rgba(255,255,255,0.2)" }}>
              {ticker?.percentage >= 0 ? "+" : ""}{ticker?.percentage?.toFixed(2)}%
            </div>
         </div>

         {/* Mini Order Book */}
         <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {[1.002, 1.0015, 1.001, 1.0005].map((off, i) => (
              <div key={`ask-${i}`} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: theme.signal.danger, opacity: 0.8 - (i * 0.1) }}>
                 <span>{(ticker?.last * off || 0).toFixed(1)}</span>
                 <span style={{ color: "rgba(255,255,255,0.2)" }}>{Math.floor(Math.random() * 1000)}</span>
              </div>
            ))}
            <div style={{ height: 1, background: `${exTheme.color}20`, margin: "4px 0" }} />
            {[0.9995, 0.999, 0.9985, 0.998].map((off, i) => (
              <div key={`bid-${i}`} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: theme.signal.success, opacity: 0.5 + (i * 0.1) }}>
                 <span>{(ticker?.last * off || 0).toFixed(1)}</span>
                 <span style={{ color: "rgba(255,255,255,0.2)" }}>{Math.floor(Math.random() * 1000)}</span>
              </div>
            ))}
         </div>

         {/* Meta Stats */}
         <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: "auto" }}>
            <div style={{ fontSize: 7, color: "rgba(255,255,255,0.2)" }}>VOL: {ticker?.volume ? (ticker.volume / 1000000).toFixed(1) + "M" : "---"}</div>
            <div style={{ fontSize: 7, color: exTheme.color, fontWeight: 900 }}>{exchange.toUpperCase()} PRO</div>
         </div>
      </div>
    </div>
  );
}

export default ExchangePanel;
