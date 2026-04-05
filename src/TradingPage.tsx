import React, { useState, useEffect } from 'react';
import ExchangePanel from './ExchangePanel';
import TradingViewChart from './TradingViewChart';
import { Target, Monitor, Layers, ShieldCheck, Wallet, Activity, XOctagon, AlertTriangle, RefreshCw, Zap, Microscope } from 'lucide-react';

interface TradingPageProps {
  theme: any;
}

function TradingPage({ theme }: TradingPageProps) {
  const [selectedPair, setSelectedPair] = useState<string>("BTCUSDT");
  const [exchanges, setExchanges] = useState<{name: string, is_simulated: boolean}[]>([]);
  const [availablePairs, setAvailablePairs] = useState<string[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [balances, setBalances] = useState<any>({});
  const [signals, setSignals] = useState<any[]>([]);
  const [isPanicLoading, setIsPanicLoading] = useState(false);
  const [showPanicConfirm, setShowPanicConfirm] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string>("");

  const fetchData = async () => {
    try {
      const [exResp, posResp, balResp, sigResp] = await Promise.all([
        fetch("/api/trade/exchanges"),
        fetch("/api/trade/positions"),
        fetch("/api/trade/balances"),
        fetch("/api/signals")
      ]);

      const exData = await exResp.json();
      const posData = await posResp.json();
      const balData = await balResp.json();
      const sigData = await sigResp.json();

      setExchanges(exData.active_exchanges || []);
      setPositions(posData.positions || []);
      setBalances(balData.balances || {});
      setSignals(sigData.signals || []);
      setLastUpdate(new Date().toLocaleTimeString());

      if (availablePairs.length === 0 && sigData.signals) {
        const pairs = Array.from(new Set(sigData.signals.map((s: any) => s.pair)));
        if (pairs.length > 0) setAvailablePairs(pairs as string[]);
      }
    } catch (e) {
      console.error("Sovereign Terminal fetch failed", e);
    }
  };

  const [globalPrice, setGlobalPrice] = useState<number | null>(null);

  const fetchGlobalPrice = async () => {
    if (!selectedPair) return;
    try {
      const resp = await fetch(`/api/market/ticker/binance/${selectedPair}`);
      if (resp.ok) {
        const data = await resp.json();
        setGlobalPrice(data.last);
      }
    } catch (e) {}
  };

  useEffect(() => {
    fetchData();
    fetchGlobalPrice();
    const interval = setInterval(fetchData, 8000);
    const priceInterval = setInterval(fetchGlobalPrice, 4000);
    return () => { clearInterval(interval); clearInterval(priceInterval); };
  }, [availablePairs.length, selectedPair]);

  const handleClosePosition = async (exchange: string, symbol: string) => {
    if (!window.confirm(`Sovereign: Confirm MARKET EXIT for ${symbol} on ${exchange}?`)) return;
    try {
      const res = await fetch("/api/trade/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ exchange, symbol })
      });
      if (res.ok) {
        fetchData();
      } else {
        const err = await res.json();
        alert(`Exit failed: ${err.detail}`);
      }
    } catch (e) {
      alert("Network error during exit command.");
    }
  };

  const handlePanic = async () => {
    setIsPanicLoading(true);
    try {
      const res = await fetch("/api/trade/panic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true })
      });
      await res.json();
      setShowPanicConfirm(false);
      fetchData();
    } catch (e) {
      alert("Panic command failed.");
    } finally {
      setIsPanicLoading(false);
    }
  };

  return (
    <div style={{ padding: "30px 40px", height: "100vh", display: "flex", flexDirection: "column", gap: 24, boxSizing: "border-box" }}>
      {/* 1. Header Bar: Balances & Panic */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 32 }}>
        <div style={{ 
          flex: 1, background: theme.base.slate, padding: "12px 24px", borderRadius: 12, 
          border: `1px solid ${theme.base.border}`, display: "flex", alignItems: "center", gap: 32
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
             <Activity size={18} color={theme.signal.success} />
             <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: 2, color: "#fff" }}>COMMAND TERMINAL</span>
          </div>
          
          <div style={{ height: 24, width: 1, background: "rgba(255,b255,255,0.05)" }} />

          <div style={{ display: "flex", gap: 24 }}>
            {Object.entries(balances).slice(0, 4).map(([ex, bal]: [any, any]) => (
              <div key={ex} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <div style={{ fontSize: 8, color: "rgba(255,255,255,0.2)", letterSpacing: 1 }}>{ex.toUpperCase()}</div>
                <div style={{ fontSize: 13, fontWeight: 800, color: theme.fire.primary, fontFamily: "monospace" }}>
                  ${typeof bal === 'number' ? bal.toLocaleString() : "..."}
                </div>
              </div>
            ))}
          </div>

          <div style={{ flex: 1 }} />

          {/* Global Price Tracker */}
          {globalPrice && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
               <div style={{ fontSize: 8, color: "rgba(255,255,255,0.2)", letterSpacing: 1 }}>GLOBAL {selectedPair}</div>
               <div style={{ fontSize: 14, fontWeight: 900, color: theme.signal.success, fontFamily: "monospace" }}>${globalPrice.toLocaleString()}</div>
            </div>
          )}

          <select 
             value={selectedPair} 
             onChange={(e) => setSelectedPair(e.target.value)}
             style={{
               background: "rgba(0,0,0,0.5)", border: `1px solid ${theme.flow.primary}40`,
               color: "#fff", padding: "6px 16px", borderRadius: 8, fontSize: 12, fontWeight: 800, outline: "none"
             }}
           >
              {availablePairs.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
           </select>
        </div>

        {/* Global Panic Trigger */}
        {!showPanicConfirm ? (
          <button 
            onClick={() => setShowPanicConfirm(true)}
            style={{
              background: theme.signal.danger + "20", border: `1px solid ${theme.signal.danger}40`,
              color: theme.signal.danger, display: "flex", alignItems: "center", gap: 10,
              padding: "0 24px", height: 44, borderRadius: 12, cursor: "pointer", fontWeight: 900,
              fontSize: 11, letterSpacing: 1
            }}
          >
            <XOctagon size={16} /> SOVEREIGN PANIC
          </button>
        ) : (
          <div style={{ display: "flex", gap: 8, background: theme.signal.danger, padding: "4px 16px", borderRadius: 12, height: 44, alignItems: "center" }}>
             <button onClick={handlePanic} disabled={isPanicLoading} style={{ background: "#fff", color: theme.signal.danger, border: "none", padding: "6px 12px", borderRadius: 6, fontWeight: 900, fontSize: 10, cursor: "pointer" }}>EXECUTE EXIT</button>
             <button onClick={() => setShowPanicConfirm(false)} style={{ background: "rgba(0,0,0,0.2)", color: "#fff", border: "none", padding: "6px 12px", borderRadius: 6, fontWeight: 900, fontSize: 10, cursor: "pointer" }}>CANCEL</button>
          </div>
        )}
      </div>

      {/* 2. Primary Workstation: Chart & Sidebar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 24, flex: 1, minHeight: 0 }}>
        {/* Central Chart */}
        <div style={{ position: "relative", minHeight: 0 }}>
          <TradingViewChart symbol={selectedPair} theme={theme} />
        </div>

        {/* Sovereign Insight Sidebar */}
        <div style={{ 
          background: theme.base.slate, borderRadius: 16, border: `1px solid ${theme.base.border}`,
          padding: 20, display: "flex", flexDirection: "column", gap: 20, overflowY: "auto"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
             <Microscope size={14} color={theme.flow.primary} />
             <span style={{ fontSize: 10, fontWeight: 900, letterSpacing: 1, color: "rgba(255,255,255,0.4)" }}>SOVEREIGN INSIGHTS</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {signals.slice(0, 12).map((sig, i) => (
              <div key={i} style={{ 
                borderBottom: "1px solid rgba(255,255,255,0.03)", paddingBottom: 10,
                cursor: "pointer",
                opacity: selectedPair === sig.pair ? 1 : 0.6,
                background: selectedPair === sig.pair ? "rgba(255,255,255,0.02)" : "transparent",
                borderRadius: 8, padding: "8px"
              }} onClick={() => setSelectedPair(sig.pair)}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800 }}>{sig.pair}</span>
                  <span style={{ 
                    fontSize: 8, padding: "2px 6px", borderRadius: 4,
                    background: sig.side === 'LONG' ? theme.signal.success + "20" : theme.signal.danger + "20",
                    color: sig.side === 'LONG' ? theme.signal.success : theme.signal.danger
                  }}>{sig.side}</span>
                </div>
                <div style={{ fontSize: 9, color: "rgba(255,255,255,0.3)", display: "flex", gap: 12 }}>
                   <span>SCORE: {sig.score}</span>
                   <span>REGIME: {sig.regime.split('_')[0]}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 3. Execution Layer: The Multi-Vault Grid (Balanced 4x2 Layout) */}
      <div style={{ 
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, 
        flex: 1, overflowY: "auto", paddingRight: 4
      }}>
        {exchanges.map(ex => (
          <ExchangePanel 
            key={ex.name} 
            exchange={ex.name} 
            isSimulated={ex.is_simulated} 
            symbol={selectedPair} 
            theme={theme} 
          />
        ))}
      </div>

      {/* 4. Active Positions Bar (Compact) */}
      <div style={{ 
        background: theme.base.slate, padding: "8px 24px", borderRadius: 12, 
        border: `1px solid ${theme.base.border}`, display: "flex", alignItems: "center", gap: 32
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
           <Zap size={14} color={theme.signal.success} /> 
           <span style={{ fontSize: 10, fontWeight: 900, color: "rgba(255,255,255,0.4)" }}>LIVE EXPOSURE</span>
        </div>
        
        <div style={{ display: "flex", gap: 20, flex: 1, overflowX: "auto" }}>
          {positions.length > 0 ? positions.map((p, i) => (
            <div key={i} style={{ 
              display: "flex", alignItems: "center", gap: 12, background: "rgba(0,0,0,0.2)",
              padding: "4px 12px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.03)"
            }}>
               <span style={{ fontSize: 10, fontWeight: 800 }}>{p.pair || p.symbol}</span>
               <span style={{ 
                 fontSize: 11, fontWeight: 900, fontFamily: "monospace",
                 color: parseFloat(p.unrealizedPnl) > 0 ? theme.signal.success : theme.signal.danger
               }}>
                 {parseFloat(p.unrealizedPnl) > 0 ? "+" : ""}{parseFloat(p.unrealizedPnl).toFixed(1)}
               </span>
               <XOctagon 
                 size={12} 
                 style={{ cursor: "pointer", opacity: 0.5 }} 
                 onClick={() => handleClosePosition(p.exchange, p.symbol)}
               />
            </div>
          )) : (
            <span style={{ fontSize: 10, color: "rgba(255,255,255,0.1)" }}>NO ACTIVE ORDERS DISPATCHED</span>
          )}
        </div>

        <RefreshCw size={12} style={{ cursor: "pointer", opacity: 0.3 }} onClick={fetchData} />
      </div>
    </div>
  );
}

export default TradingPage;
