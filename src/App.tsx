/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback } from "react";
import TradingViewChart from "./TradingViewChart";
import TechnicalAnalysis from "./TechnicalAnalysis";
import TradingPage from "./TradingPage";
import { Gauge, Zap } from "lucide-react";
import { computeStopPctPercent, formatPctForUI, formatPFForUI } from "./utils/risk";
import AlphaBadges from "./AlphaBadges";
import { useSignalsSSE, BackendSignal } from "./hooks/useSignalsSSE";

// === TYPES ===
interface CellStat {
  regime: string;
  score_bucket: number;
  wins: number;
  losses: number;
  expired: number;
  win_rate: number;
  profit_factor: number;
}

interface StatGroup {
  wins: number;
  losses: number;
  expired: number;
  total: number;
  win_rate: number;
  profit_factor: number;
}

interface CycleStats {
  pairs_processed?: number;
  setups_viable_pre_phase2?: number;
  setups_blocked_phase2?: number;
  signals_emitted?: number;
  duration?: number;
}

interface BackendStats {
  simulated: StatGroup;
  live: StatGroup;
  total: StatGroup;
  unresolved: number;
  latest_cycle?: CycleStats;
  logic_version?: string;
  config_version?: string;
}

// === THEME CONSTANTS ===
const THEME = {
  fire: {
    primary: "#F59E0B",
    deep: "#d9d506ff",
    core: "#92400E",
  },
  flow: {
    primary: "#0EA5E9",
    deep: "#0369A1",
    abyss: "#0C4A6E",
  },
  base: {
    sovereign: "#020617",
    slate: "#0F172A",
    border: "rgba(245, 158, 11, 0.15)",
  },
  signal: {
    success: "#22C55E",
    danger: "#EF4444",
  }
};

// === REGIME BADGE ===
function RegimeBadge({ regime }: { regime: string }) {
  const colors: Record<string, { bg: string, text: string, icon: string }> = {
    STRONG_UPTREND: { bg: "rgba(34, 197, 94, 0.05)", text: "#22C55E", icon: "▲▲" },
    UPTREND: { bg: "rgba(34, 197, 94, 0.03)", text: "#22C55E", icon: "▲" },
    RANGING: { bg: "rgba(14, 165, 233, 0.03)", text: THEME.flow.primary, icon: "◆" },
    DOWNTREND: { bg: "rgba(239, 68, 68, 0.03)", text: THEME.signal.danger, icon: "▼" },
    STRONG_DOWNTREND: { bg: "rgba(239, 68, 68, 0.05)", text: THEME.signal.danger, icon: "▼▼" },
    UNKNOWN: { bg: "#1c1917", text: "#737373", icon: "?" },
  };
  const c = colors[regime] || colors.UNKNOWN;
  return (
    <span style={{
      background: c.bg, color: c.text, padding: "4px 12px",
      borderRadius: 4, fontSize: 10, fontWeight: 700, fontFamily: "monospace",
      display: "inline-flex", alignItems: "center", gap: 6, border: `1px solid ${c.text}22`,
      textTransform: "uppercase", letterSpacing: 1,
    }}>
      <span style={{ fontSize: 12 }}>{c.icon}</span> {regime}
    </span>
  );
}

// === SIGNAL CARD ===
function SignalCard({ signal }: { signal: BackendSignal }) {
  const color = signal.side === "LONG" ? THEME.signal.success : THEME.signal.danger;
  const bucket = signal.reason_trace?.score_bucket || (Math.floor(signal.score / 5) * 5);
  const stopPctVal = computeStopPctPercent(signal.entry, signal.stop_loss);

  return (
    <div style={{
      background: `linear-gradient(90deg, ${color}08 0%, transparent 100%)`,
      border: `1px solid ${color}20`,
      borderRadius: 8, padding: "12px 16px", marginTop: 10,
      borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            color: "#fff", fontWeight: 800, fontSize: 11, fontFamily: "monospace",
            background: color, padding: "2px 10px", borderRadius: 4,
          }}>{signal.side}</span>
          <span style={{ color: THEME.fire.primary, fontSize: 24, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace" }}>
            {signal.score}<span style={{ fontSize: 14, color: "rgba(255,255,255,0.2)" }}>/100</span>
          </span>
        </div>
        <span style={{
          fontSize: 9, fontWeight: 800, fontFamily: "monospace", padding: "3px 8px", borderRadius: 4,
          background: "rgba(255,255,255,0.05)", color: THEME.fire.primary,
          border: `1px solid ${THEME.fire.primary}44`, letterSpacing: 1,
        }}>
          BUCKET {bucket} • ALLOWED
        </span>
      </div>
      <div style={{ marginTop: 12, fontSize: 11, fontFamily: "monospace", color: "rgba(255,255,255,0.5)", lineHeight: 1.8 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>ENTRY REF</span>
          <span style={{ color: "#fff", fontWeight: 600 }}>${signal.entry.toLocaleString()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>STOP LOSS</span>
          <span style={{ color: THEME.signal.danger, fontWeight: 600 }}>
            ${signal.stop_loss.toLocaleString()}
            <span style={{ fontSize: 9, opacity: 0.6 }}>
              ({formatPctForUI(Math.abs(signal.entry - signal.stop_loss) / signal.entry * 100)})
            </span>
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span>TAKE PROFIT (MAX)</span>
          <span style={{ color: THEME.signal.success, fontWeight: 600 }}>${signal.take_profit.toLocaleString()}</span>
        </div>
        {signal.reason_trace?.tp1 && (
          <div style={{ display: "flex", justifyContent: "space-between", color: "rgba(34, 197, 94, 0.7)", fontSize: 10 }}>
            <span>TP1 / BREAKEVEN</span>
            <span>${signal.reason_trace.tp1.toLocaleString()}</span>
          </div>
        )}
        <div style={{
          marginTop: 10, paddingTop: 10, borderTop: "1px dashed rgba(255,255,255,0.05)",
          display: "flex", justifyContent: "space-between", fontSize: 10, color: "rgba(255,255,255,0.4)"
        }}>
          <div>
            SIZE: <span style={{ color: "#fff", fontWeight: "bold" }}>{signal.reason_trace?.position_size?.toFixed(4) || "0.00"}</span>
          </div>
          <div>
            RISK: <span style={{ color: THEME.fire.primary, fontWeight: "bold" }}>${signal.reason_trace?.risk_usd || "0.00"}</span>
          </div>
        </div>
        <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
          {signal.reason_trace?.reasons_pass?.map((r: string, i: number) => (
            <span key={i} style={{
              background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: 3,
              padding: "2px 8px", fontSize: 9, color: "rgba(255,255,255,0.3)",
            }}>{r}</span>
          ))}
        </div>

        {/* --- V1.5 IRON GATES AUDIT --- */}
        <div style={{
          marginTop: 15, padding: "10px 12px", background: "rgba(0,0,0,0.2)", borderRadius: 8,
          border: `1px solid ${THEME.base.border}`, display: "flex", flexDirection: "column", gap: 6
        }}>
          <div style={{ fontSize: 9, fontWeight: 800, color: THEME.fire.primary, display: "flex", justifyContent: "space-between", letterSpacing: 2 }}>
            <span>IRON GATES AUDIT</span>
            <span>v1.5-QUANT-ALPHA</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontFamily: "monospace" }}>
            <span style={{ color: "rgba(255,255,255,0.3)" }}>G_sq (SQUEEZE)</span>
            <span style={{ color: signal.reason_trace?.recent_squeeze_fire ? THEME.signal.success : THEME.signal.danger }}>
              {signal.reason_trace?.recent_squeeze_fire ? "● PASSED" : "○ FAILED"}
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontFamily: "monospace" }}>
            <span style={{ color: "rgba(255,255,255,0.3)" }}>G_vol (CONVICTION)</span>
            <span style={{ color: (signal.reason_trace?.volume_ratio || 0) >= 1.2 ? THEME.signal.success : THEME.signal.danger }}>
              {(signal.reason_trace?.volume_ratio || 0) >= 1.2 ? "● PASSED" : "○ FAILED"}
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontFamily: "monospace" }}>
            <span style={{ color: "rgba(255,255,255,0.3)" }}>G_alpha (INSTITUTIONAL)</span>
            <span style={{ color: (signal.reason_trace?.derivatives_bonus || 0) > 0 ? THEME.signal.success : "#4b5563" }}>
              {(signal.reason_trace?.derivatives_bonus || 0) > 0 ? "● ACTIVE" : "○ NEUTRAL"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// === PAIR PANEL ===
interface PairPanelProps {
  symbol: string;
  signals: BackendSignal[];
  theme: any;
  key?: string | number;
}

function PairPanel({ symbol, signals, theme }: PairPanelProps) {
  const latestSignal = signals[0];
  const pairLabel = symbol.replace("USDT", "").replace("USD", "");
  const pairColors: Record<string, string> = { BTC: THEME.fire.primary, ETH: THEME.flow.primary, SOL: "#8b5cf6" };
  const accent = pairColors[pairLabel] || THEME.fire.primary;

  if (!latestSignal) return null;

  return (
    <div style={{
      background: THEME.base.slate, border: `1px solid ${THEME.base.border}`, borderRadius: 12,
      padding: 24, flex: 1, minWidth: 320,
      backgroundImage: `radial-gradient(circle at top right, ${accent}08 0%, transparent 40%)`,
      boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", fontFamily: "monospace", marginBottom: 4, letterSpacing: 2 }}>{symbol}</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: "#fff", fontFamily: "'JetBrains Mono', monospace", letterSpacing: -1 }}>
            ${latestSignal.entry.toLocaleString()}
          </div>
        </div>
        <RegimeBadge regime={latestSignal.regime} />
      </div>

      <div style={{ height: 250, marginBottom: 12, borderRadius: 12, overflow: "hidden", border: "1px solid rgba(245, 158, 11, 0.1)", background: "#0F0F0F" }}>
        <TradingViewChart symbol={symbol} theme={theme} interval="15" />
      </div>

      <div style={{
        height: 250, borderRadius: 12, overflow: "hidden", border: "1px solid rgba(245, 158, 11, 0.1)",
        background: "rgba(15, 15, 15, 0.5)", backdropFilter: "blur(10px)", marginBottom: 20
      }}>
        <TechnicalAnalysis symbol={symbol} />
      </div>

      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12,
        marginTop: 16, fontSize: 10, fontFamily: "monospace", color: "rgba(255,255,255,0.2)",
        borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 16,
      }}>
        <div style={{ textAlign: "center" }}>SCAN SCORE<br /><span style={{ color: THEME.fire.primary, fontSize: 18, fontWeight: 800 }}>{latestSignal.score}</span></div>
        <div style={{ textAlign: "center" }}>VOL RATIO<br /><span style={{ color: THEME.signal.success, fontSize: 18, fontWeight: 800 }}>{latestSignal.reason_trace?.volume_ratio?.toFixed(2)}x</span></div>
        <div style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center" }}>
          <span style={{ marginBottom: 4 }}>ALPHA</span>
          <AlphaBadges reasonTrace={latestSignal.reason_trace} />
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        <SignalCard signal={latestSignal} />
      </div>
    </div>
  );
}

// === MAIN APP ===
export default function IdimIkangDashboard() {
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { signals: liveSignals, isConnected, error: sseError } = useSignalsSSE();
  const [stats, setStats] = useState<BackendStats | null>(null);
  const [allHistory, setAllHistory] = useState(false);
  const [cellStats, setCellStats] = useState<CellStat[]>([]);
  const [historySignals, setHistorySignals] = useState<BackendSignal[]>([]);
  const [activeTab, setActiveTab] = useState<'DASHBOARD' | 'TRADING'>('DASHBOARD');

  const fetchBackend = useCallback(async () => {
    try {
      const statsResp = await fetch(`/api/stats?all_history=${allHistory}`);
      if (statsResp.ok) setStats(await statsResp.json());

      const signalsResp = await fetch(`/api/signals?all_history=${allHistory}`);
      if (signalsResp.ok) {
        const signalsData = await signalsResp.json();
        setHistorySignals(Array.isArray(signalsData.signals) ? signalsData.signals : []);
      }

      const cellResp = await fetch(`/api/cell-performance?all_history=${allHistory}`);
      if (cellResp.ok) setCellStats(await cellResp.json());

      setLastUpdate(new Date());
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [allHistory]);

  useEffect(() => {
    fetchBackend();
    const interval = setInterval(fetchBackend, 30000);
    return () => clearInterval(interval);
  }, [fetchBackend]);

  const mergedSignals = [...liveSignals, ...historySignals].reduce<BackendSignal[]>((acc, signal) => {
    if (!acc.some(existing => existing.signal_id === signal.signal_id)) {
      acc.push(signal);
    }
    return acc;
  }, []);

  const activeSignals = mergedSignals.filter(s => s.outcome === null);
  const archiveSignals = historySignals.length > 0 ? historySignals : mergedSignals;
  const executionStats = stats && stats.live.total > 0 ? stats.live : stats?.simulated;
  const executionLabel = stats && stats.live.total > 0 ? "LIVE" : "SIM";
  const openSignalsCount = stats?.unresolved ?? activeSignals.length;
  const newSignalsThisCycle = stats?.latest_cycle?.signals_emitted ?? 0;

  const pairedSignals: Record<string, BackendSignal[]> = {};
  activeSignals.forEach(s => {
    if (!pairedSignals[s.pair]) pairedSignals[s.pair] = [];
    pairedSignals[s.pair].push(s);
  });

  return (
    <div style={{ minHeight: "100vh", background: THEME.base.sovereign, color: "#fff", fontFamily: "'Inter', sans-serif" }}>
      <div style={{
        background: "rgba(15, 23, 42, 0.8)", backdropFilter: "blur(20px)",
        borderBottom: `1px solid ${THEME.base.border}`, padding: "16px 60px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        position: "sticky", top: 0, zIndex: 1000,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <img src="/idimikanglogo.png" alt="Idim Ikang Logo" style={{ width: 100, height: 100, objectFit: "contain" }} />
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: 2, color: THEME.fire.primary }}>IDIM IKANG</div>
            <div style={{ fontSize: 10, color: "rgba(255,255,255,0.2)", fontFamily: "monospace", letterSpacing: 2 }}>SOVEREIGN CORE MIRROR</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, background: "rgba(0,0,0,0.2)", padding: 4, borderRadius: 12, border: "1px solid rgba(255,255,255,0.05)" }}>
          <button onClick={() => setActiveTab('DASHBOARD')} style={{
            padding: "10px 24px", borderRadius: 8, border: "none", cursor: "pointer",
            background: activeTab === 'DASHBOARD' ? THEME.fire.primary : "transparent",
            color: activeTab === 'DASHBOARD' ? THEME.base.sovereign : "rgba(255,255,255,0.4)",
            fontSize: 11, fontWeight: 800, letterSpacing: 1, display: "flex", alignItems: "center", gap: 8, transition: "0.2s"
          }}><Gauge size={14} /> DASHBOARD</button>
          <button onClick={() => setActiveTab('TRADING')} style={{
            padding: "10px 24px", borderRadius: 8, border: "none", cursor: "pointer",
            background: activeTab === 'TRADING' ? THEME.fire.primary : "transparent",
            color: activeTab === 'TRADING' ? THEME.base.sovereign : "rgba(255,255,255,0.4)",
            fontSize: 11, fontWeight: 800, letterSpacing: 1, display: "flex", alignItems: "center", gap: 8, transition: "0.2s"
          }}><Zap size={14} /> TRADING</button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
          {stats && (
            <div style={{ display: "flex", gap: 32, padding: "0 24px", borderRight: "1px solid rgba(255,255,255,0.05)", marginRight: 24 }}>
              {/* TOTAL STATS */}
              <div style={{ display: "flex", gap: 16 }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: "rgba(255,255,255,0.3)", letterSpacing: 1 }}>TOTAL WINS</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: THEME.signal.success }}>{stats.total?.wins || 0}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: "rgba(255,255,255,0.3)", letterSpacing: 1 }}>TOTAL LOSSES</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: THEME.signal.danger }}>{stats.total?.losses || 0}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: "rgba(255,255,255,0.3)", letterSpacing: 1 }}>TOTAL WR%</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#fff" }}>{stats.total?.win_rate || 0}%</div>
                </div>
              </div>

              {/* LIVE STATS */}
              <div style={{ display: "flex", gap: 16, padding: "0 16px", borderLeft: "1px solid rgba(255,255,255,0.05)", borderRight: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: THEME.fire.primary, letterSpacing: 1 }}>{executionLabel} WINS</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: THEME.fire.primary }}>{executionStats?.wins || 0}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: THEME.fire.primary, letterSpacing: 1 }}>{executionLabel} WR%</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#fff" }}>{executionStats?.win_rate || 0}%</div>
                </div>
              </div>

              <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: THEME.flow.primary, letterSpacing: 1 }}>ACTIVE OPEN</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: THEME.flow.primary }}>{openSignalsCount}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 8, color: THEME.fire.primary, letterSpacing: 1 }}>NEW THIS CYCLE</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: THEME.fire.primary }}>{newSignalsThisCycle}</div>
                </div>
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 24, fontSize: 11, fontFamily: "monospace" }}>
            <button onClick={() => setAllHistory(!allHistory)} style={{
              background: allHistory ? "rgba(255,255,255,0.1)" : THEME.fire.primary,
              color: allHistory ? "#fff" : THEME.base.sovereign,
              border: "none", padding: "4px 16px", borderRadius: 4, cursor: "pointer",
              fontSize: 10, fontWeight: 800, letterSpacing: 1
            }}>{allHistory ? "MODE: ALL HISTORY" : "MODE: CURRENT ONLY"}</button>
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(255,255,255,0.03)", padding: "4px 12px", borderRadius: 100 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: isConnected ? THEME.signal.success : THEME.signal.danger }} />
              <span style={{ color: isConnected ? THEME.signal.success : THEME.signal.danger }}>{isConnected ? "LIVE STREAM" : "STREAM OFFLINE"}</span>
            </div>
            <div style={{ color: "rgba(255,255,255,0.2)" }}>SYNC: {lastUpdate ? lastUpdate.toLocaleTimeString() : "—"}</div>
          </div>
        </div>
      </div>

      <div style={{ padding: activeTab === 'DASHBOARD' ? "40px 60px" : "0" }}>
        {activeTab === 'DASHBOARD' ? (
          loading ? (
            <div style={{ textAlign: "center", padding: 100, opacity: 0.2 }}>COLLECTING FLOW DATA...</div>
          ) : (
            <>
              <div style={{
                marginBottom: 40, background: THEME.base.slate, border: `1px solid ${THEME.base.border}`,
                borderRadius: 16, padding: 32, backgroundImage: `linear-gradient(225deg, ${THEME.fire.primary}05 0%, transparent 100%)`
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
                  <div style={{ fontSize: 12, color: THEME.fire.primary, fontFamily: "monospace", letterSpacing: 4, fontWeight: 800 }}>WOLFRAM PERFORMANCE</div>
                  <div style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", background: "rgba(255,255,255,0.05)", padding: "4px 12px", borderRadius: 4 }}>v1.5-quant-alpha</div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
                  {Array.isArray(cellStats) && cellStats.map((cell, idx) => (
                    <div key={idx} style={{
                      background: "rgba(255,255,255,0.03)", borderRadius: 12, padding: 16, border: "1px solid rgba(255,255,255,0.05)",
                      display: "flex", flexDirection: "column", gap: 8
                    }}>
                      <div style={{ fontSize: 9, fontWeight: 800, color: THEME.fire.primary }}>{cell.regime}</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: "#fff", fontFamily: "'JetBrains Mono', monospace" }}>{cell.score_bucket}</div>
                      <div style={{ height: 1, background: "rgba(255,255,255,0.05)", margin: "4px 0" }} />
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
                        <span>WR%</span><span style={{ color: THEME.signal.success }}>{cell.win_rate}%</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "rgba(255,255,255,0.5)" }}>
                        <span>PF</span><span style={{ color: THEME.fire.primary }}>{formatPFForUI(cell.profit_factor, cell.wins, cell.losses)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {Object.keys(pairedSignals).length === 0 ? (
                <div style={{
                  padding: 100, textAlign: "center", opacity: 0.3, border: `1px dashed ${THEME.base.border}`, borderRadius: 16,
                  fontFamily: "monospace", fontSize: 11, letterSpacing: 2
                }}>
                  NO ACTIVE SOVEREIGN SIGNALS DETECTED IN CURRENT BUCKET
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 32 }}>
                  {Object.keys(pairedSignals).map(symbol => (
                    <PairPanel key={symbol} symbol={symbol} signals={pairedSignals[symbol]} theme={THEME} />
                  ))}
                </div>
              )}

              {/* Covenant Archive */}
              <div style={{ marginTop: 60, background: THEME.base.slate, border: `1px solid ${THEME.base.border}`, borderRadius: 16, padding: 32 }}>
                <div style={{
                  fontSize: 12, color: THEME.fire.primary, fontFamily: "monospace", marginBottom: 20,
                  letterSpacing: 4, fontWeight: 800, borderLeft: `3px solid ${THEME.fire.primary}`, paddingLeft: 16,
                }}>COVENANT HISTORY ARCHIVE</div>
                  <div style={{ overflowX: "auto" }}>
                    <div style={{ minWidth: 1400, maxHeight: 500, overflow: "auto" }}>
                      {/* Header Row */}
                      <div style={{
                        display: "grid",
                        gridTemplateColumns: "160px 100px 60px 55px 55px 90px 80px 60px 85px 80px 80px 90px 70px 100px",
                        gap: 8, padding: "10px 16px",
                        borderBottom: `2px solid ${THEME.fire.primary}`,
                        color: THEME.fire.primary, fontSize: 9, fontFamily: "monospace",
                        fontWeight: 800, letterSpacing: 1, position: "sticky", top: 0,
                        background: THEME.base.slate, zIndex: 10
                      }}>
                        <span>TIME</span>
                        <span>PAIR</span>
                        <span>SIDE</span>
                        <span>SCORE</span>
                        <span>R-MULT</span>
                        <span>ENTRY</span>
                        <span>SL / TP</span>
                        <span>OUTCOME</span>
                        <span>FAMILY</span>
                        <span>MKT REGIME</span>
                        <span>BTC REGIME</span>
                        <span>EXEC SOURCE</span>
                        <span>HOUR</span>
                        <span>POLICY</span>
                      </div>
                      {archiveSignals.map((s) => {
                        const outcome = (s.outcome || "OPEN").toUpperCase();
                        const outcomeColor = outcome === "WIN" || outcome === "PARTIAL_WIN" || outcome === "LIVE_WIN"
                          ? THEME.signal.success
                          : outcome === "LOSS" || outcome === "LIVE_LOSS"
                            ? THEME.signal.danger
                            : outcome === "EXPIRED"
                              ? "#b45309"
                              : "rgba(255,255,255,0.25)";
                        const rVal = s.r_multiple != null ? (s.r_multiple >= 0 ? `+${Number(s.r_multiple).toFixed(2)}` : Number(s.r_multiple).toFixed(2)) : "—";
                        const rColor = s.r_multiple != null ? (s.r_multiple >= 0 ? THEME.signal.success : THEME.signal.danger) : "rgba(255,255,255,0.2)";
                        const family = (s.signal_family || "—").toUpperCase();
                        const familyColor = family === "TREND" ? "#60a5fa" : family === "MOMENTUM" ? "#f59e0b" : family === "MEAN_REVERSION" ? "#a78bfa" : family === "VOLATILITY" ? "#34d399" : "rgba(255,255,255,0.2)";
                        const execColor = s.execution_source === "live" ? THEME.fire.primary : "rgba(255,255,255,0.3)";

                        return (
                          <div key={s.signal_id} style={{
                          display: "grid",
                          gridTemplateColumns: "160px 100px 60px 55px 55px 90px 80px 60px 85px 80px 80px 90px 70px 100px",
                          gap: 8, padding: "8px 16px",
                          borderBottom: "1px solid rgba(255,255,255,0.03)",
                          color: "rgba(255,255,255,0.4)", fontSize: 10, fontFamily: "monospace",
                          transition: "background 0.15s",
                        }}
                          onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.03)")}
                          onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                        >
                          <span style={{ color: "rgba(255,255,255,0.5)" }}>{new Date(s.ts).toLocaleString()}</span>
                          <span style={{ fontWeight: 800, color: "#fff" }}>{s.pair}</span>
                          <span style={{ color: s.side === "LONG" ? THEME.signal.success : THEME.signal.danger, fontWeight: 700 }}>{s.side}</span>
                          <span style={{ color: THEME.fire.primary, fontWeight: 700 }}>{s.score}</span>
                          <span style={{ color: rColor, fontWeight: 700 }}>{rVal}</span>
                          <span>${s.entry?.toLocaleString() ?? '—'}</span>
                          <span style={{ fontSize: 9 }}>{s.stop_loss ? `$${s.stop_loss.toLocaleString()}` : '—'}</span>
                          <span style={{ color: outcomeColor, fontWeight: 800, fontSize: 9 }}>{outcome}</span>
                          <span style={{ color: familyColor, fontSize: 9 }}>{family}</span>
                          <span style={{ fontSize: 9 }}>{(s.market_regime || '—').toUpperCase()}</span>
                          <span style={{ fontSize: 9 }}>{(s.btc_regime || '—').toUpperCase()}</span>
                          <span style={{ color: execColor, fontSize: 9, fontWeight: 700 }}>{(s.execution_source || 'SIM').toUpperCase()}</span>
                          <span>{s.signal_hour_utc != null ? `${String(s.signal_hour_utc).padStart(2, '0')}:00` : '—'}</span>
                          <span style={{ fontSize: 8, color: "rgba(255,255,255,0.2)" }}>{s.policy_version || '—'}</span>
                        </div>
                      );
                    })}
                    </div>
                </div>
              </div>
            </>
          )
        ) : (
          <TradingPage theme={THEME} />
        )}
      </div>
    </div>
  );
}
