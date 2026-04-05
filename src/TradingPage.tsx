import React, { useState, useEffect } from 'react';
import ExchangePanel from './ExchangePanel';
import { Target, Monitor, Layers, ShieldCheck } from 'lucide-react';

interface TradingPageProps {
  theme: any;
}

function TradingPage({ theme }: TradingPageProps) {
  const [selectedPair, setSelectedPair] = useState<string>("BTCUSDT");
  const [exchanges, setExchanges] = useState<string[]>([]);
  const [availablePairs, setAvailablePairs] = useState<string[]>([]);

  useEffect(() => {
    // Fetch active exchanges and pairs from scanner context
    const fetchData = async () => {
      try {
        const exResp = await fetch("/api/trade/exchanges");
        const exData = await exResp.json();
        setExchanges(exData.active_exchanges);

        const sigResp = await fetch("/api/signals");
        const sigData = await sigResp.json();
        const pairs = Array.from(new Set(sigData.signals.map((s: any) => s.pair)));
        if (pairs.length > 0) {
          setAvailablePairs(pairs as string[]);
          if (!selectedPair) setSelectedPair(pairs[0] as string);
        }
      } catch (e) {
        console.error("Executor data fetch failed", e);
      }
    };
    fetchData();
  }, []);

  return (
    <div style={{ padding: "40px 60px" }}>
      {/* Control Bar */}
      <div style={{ 
        display: "flex", justifyContent: "space-between", alignItems: "center", 
        marginBottom: 40, background: theme.base.slate, padding: "20px 32px",
        borderRadius: 16, border: `1px solid ${theme.base.border}`,
        backgroundImage: `linear-gradient(90deg, ${theme.flow.primary}05 0%, transparent 100%)`
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Target size={20} color={theme.fire.primary} />
            <select 
              value={selectedPair} 
              onChange={(e) => setSelectedPair(e.target.value)}
              style={{
                background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.1)",
                color: "#fff", padding: "8px 16px", borderRadius: 8, fontSize: 13,
                outline: "none", cursor: "pointer", fontWeight: 700
              }}
            >
              <option value="BTCUSDT">BTCUSDT</option>
              <option value="ETHUSDT">ETHUSDT</option>
              <option value="SOLUSDT">SOLUSDT</option>
              {availablePairs.filter(p => !["BTCUSDT", "ETHUSDT", "SOLUSDT"].includes(p)).map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div style={{ height: 24, width: 1, background: "rgba(255,255,255,0.05)" }} />
          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
              <ShieldCheck size={14} color={theme.signal.success} /> 
              <span>DRY RUN: <span style={{ color: theme.signal.success, fontWeight: 700 }}>ACTIVE</span></span>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", fontFamily: "monospace", letterSpacing: 2 }}>
            SOVEREIGN EXECUTOR v1.0
          </div>
        </div>
      </div>

      {/* Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))",
        gap: 32
      }}>
        {exchanges.length > 0 ? exchanges.map(ex => (
          <ExchangePanel key={ex} exchange={ex} symbol={selectedPair} theme={theme} />
        )) : (
          <div style={{ 
            gridColumn: "1 / -1", textAlign: "center", padding: 100, 
            background: theme.base.slate, borderRadius: 20, border: `1px dashed ${theme.base.border}`,
            color: "rgba(255,255,255,0.2)", fontSize: 13
          }}>
            <Monitor size={48} style={{ marginBottom: 20, opacity: 0.1 }} />
            <br />
            NO EXCHANGES INITIALIZED. <br />
            PLEASE ADD API KEYS TO .ENV AND RESTART.
          </div>
        )}
      </div>

      {/* Positions Summary (Future Expansion) */}
      <div style={{ 
        marginTop: 40, padding: 32, background: theme.base.slate, 
        borderRadius: 20, border: `1px solid ${theme.base.border}`,
        opacity: 0.8
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <Layers size={18} color={theme.flow.primary} />
          <span style={{ fontSize: 12, fontWeight: 800, color: "#fff", letterSpacing: 3 }}>LIVE POSITION MONITOR</span>
        </div>
        <div style={{ textAlign: "center", padding: 40, fontSize: 11, color: "rgba(255,255,255,0.2)", fontFamily: "monospace" }}>
          AGGREGATING EXPOSURE ACROSS NODES...
        </div>
      </div>
    </div>
  );
}

export default TradingPage;
