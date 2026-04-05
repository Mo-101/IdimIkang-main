import React, { useState, useEffect } from 'react';
import { Send, Wallet, Activity, TrendingUp, TrendingDown } from 'lucide-react';

interface ExchangePanelProps {
  key?: string;
  exchange: string;
  symbol: string;
  theme: any;
}

function ExchangePanel({ exchange, symbol, theme }: ExchangePanelProps) {
  const [balance, setBalance] = useState<number | string>("...");
  const [amount, setAmount] = useState<string>("");
  const [price, setPrice] = useState<string>("");
  const [orderType, setOrderType] = useState<string>("market");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ msg: string; type: 'info' | 'error' | 'success' } | null>(null);

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
    const inv = setInterval(fetchBalance, 10000);
    return () => clearInterval(inv);
  }, [exchange]);

  const executeOrder = async (side: 'BUY' | 'SELL') => {
    setLoading(true);
    setStatus({ msg: `Sending ${side} Order...`, type: 'info' });
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
          price: price ? parseFloat(price) : null
        })
      });
      const result = await resp.json();
      if (resp.ok) {
        setStatus({ msg: `Order Executed: ${result.order_id || 'Success'}`, type: 'success' });
        fetchBalance();
      } else {
        setStatus({ msg: result.detail || "Order Failed", type: 'error' });
      }
    } catch (e: any) {
      setStatus({ msg: e.message, type: 'error' });
    }
    setLoading(false);
  };

  return (
    <div style={{
      background: "rgba(15, 23, 42, 0.6)",
      border: `1px solid ${theme.base.border}`,
      borderRadius: 16,
      padding: 20,
      display: "flex",
      flexDirection: "column",
      gap: 16,
      backdropFilter: "blur(12px)",
      boxShadow: "0 10px 30px rgba(0,0,0,0.4)"
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Activity size={16} color={theme.fire.primary} />
          <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: 1, color: "#fff" }}>{exchange.toUpperCase()}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
          <Wallet size={12} />
          <span style={{ color: theme.fire.primary, fontWeight: 700 }}>{typeof balance === 'number' ? `$${balance.toLocaleString()}` : balance}</span>
        </div>
      </div>

      <div style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", fontFamily: "monospace" }}>TRADING: {symbol}</div>

      {/* Form */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button 
            onClick={() => setOrderType("market")}
            style={{ 
              flex: 1, padding: "6px", fontSize: 10, borderRadius: 6, cursor: "pointer",
              background: orderType === 'market' ? "rgba(255,255,255,0.1)" : "transparent",
              color: orderType === 'market' ? "#fff" : "rgba(255,255,255,0.3)",
              border: "1px solid rgba(255,255,255,0.1)"
            }}>MARKET</button>
          <button 
            onClick={() => setOrderType("limit")}
            style={{ 
              flex: 1, padding: "6px", fontSize: 10, borderRadius: 6, cursor: "pointer",
              background: orderType === 'limit' ? "rgba(255,255,255,0.1)" : "transparent",
              color: orderType === 'limit' ? "#fff" : "rgba(255,255,255,0.3)",
              border: "1px solid rgba(255,255,255,0.1)"
            }}>LIMIT</button>
        </div>

        <div style={{ position: "relative" }}>
          <input 
            type="number" 
            placeholder="Amount (Contracts)" 
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            style={{ 
              width: "100%", background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.05)",
              padding: "10px 12px", borderRadius: 8, color: "#fff", fontSize: 12, outline: "none"
            }}
          />
        </div>

        {orderType === 'limit' && (
          <div style={{ position: "relative" }}>
            <input 
              type="number" 
              placeholder="Price" 
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              style={{ 
                width: "100%", background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.05)",
                padding: "10px 12px", borderRadius: 8, color: "#fff", fontSize: 12, outline: "none"
              }}
            />
          </div>
        )}

        <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
          <button 
            disabled={loading || !amount}
            onClick={() => executeOrder('BUY')}
            style={{ 
              flex: 1, background: theme.signal.success, color: "#fff", border: "none",
              padding: "12px", borderRadius: 8, fontWeight: 800, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              opacity: (loading || !amount) ? 0.5 : 1, transition: "0.2s"
            }}>
            <TrendingUp size={16} /> BUY
          </button>
          <button 
            disabled={loading || !amount}
            onClick={() => executeOrder('SELL')}
            style={{ 
              flex: 1, background: theme.signal.danger, color: "#fff", border: "none",
              padding: "12px", borderRadius: 8, fontWeight: 800, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              opacity: (loading || !amount) ? 0.5 : 1, transition: "0.2s"
            }}>
            <TrendingDown size={16} /> SELL
          </button>
        </div>
      </div>

      {/* Status Bar */}
      {status && (
        <div style={{ 
          fontSize: 10, padding: "8px 12px", borderRadius: 6, fontFamily: "monospace",
          background: status.type === 'error' ? "rgba(239, 68, 68, 0.1)" : (status.type === 'success' ? "rgba(34, 197, 94, 0.1)" : "rgba(255,255,255,0.05)"),
          color: status.type === 'error' ? theme.signal.danger : (status.type === 'success' ? theme.signal.success : "rgba(255,255,255,0.4)"),
          border: `1px solid ${status.type === 'error' ? theme.signal.danger : (status.type === 'success' ? theme.signal.success : 'transparent')}22`
        }}>
          {status.msg}
        </div>
      )}
    </div>
  );
}

export default ExchangePanel;
