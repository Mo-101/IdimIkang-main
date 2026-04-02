/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback, useRef } from "react";
import TradingViewChart, { TradingViewChartHandle } from "./TradingViewChart";

// === LOCKED CONFIG ===
const CONFIG = {
  pairs: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  minScore: 45,
  cooldownBars: 32,
  blockStrongUptrend: true,
  atrSl: 1.0,
  atrTp: 3.0,
};

// === INDICATOR MATH (pure functions) ===
function computeEMA(data: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result = [data[0]];
  for (let i = 1; i < data.length; i++) {
    result.push(data[i] * k + result[i - 1] * (1 - k));
  }
  return result;
}

function computeRSI(closes: number[], period = 14): number[] {
  const rsi = new Array(closes.length).fill(50);
  if (closes.length < period + 1) return rsi;
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) avgGain += diff; else avgLoss += Math.abs(diff);
  }
  avgGain /= period; avgLoss /= period;
  rsi[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    avgGain = (avgGain * (period - 1) + (diff > 0 ? diff : 0)) / period;
    avgLoss = (avgLoss * (period - 1) + (diff < 0 ? Math.abs(diff) : 0)) / period;
    rsi[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return rsi;
}

function computeATR(highs: number[], lows: number[], closes: number[], period = 14): number[] {
  const tr = [highs[0] - lows[0]];
  for (let i = 1; i < highs.length; i++) {
    tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
  }
  return computeEMA(tr, period);
}

function computeMACD(closes: number[]): { macd: number[], signal: number[], hist: number[] } {
  const ema12 = computeEMA(closes, 12);
  const ema26 = computeEMA(closes, 26);
  const macd = ema12.map((v, i) => v - ema26[i]);
  const signal = computeEMA(macd, 9);
  const hist = macd.map((v, i) => v - signal[i]);
  return { macd, signal, hist };
}

// === REGIME CLASSIFIER ===
function classifyRegime(ema20: number, ema50: number, rsi: number, adxApprox: number): string {
  const bull = ema20 > ema50;
  if (adxApprox > 30 && bull && rsi > 55) return "STRONG_UPTREND";
  if (adxApprox > 20 && bull) return "UPTREND";
  if (adxApprox > 30 && !bull && rsi < 45) return "STRONG_DOWNTREND";
  if (adxApprox > 20 && !bull) return "DOWNTREND";
  return "RANGING";
}

// === SIGNAL SCORER ===
function scoreSignal(close: number, emaFast: number, emaSlow: number, rsi: number, macdHist: number, prevMacdHist: number, volRatio: number, regime: string, side: string): { score: number, reasons: string[] } {
  let score = 0;
  const reasons: string[] = [];
  if (side === "LONG") {
    if (emaFast > emaSlow) { score += 25; reasons.push("EMA aligned"); }
    if (close > emaFast) { score += 7; reasons.push("Price > EMA20"); }
    if (rsi >= 40 && rsi <= 65) { score += 15; reasons.push(`RSI ${rsi.toFixed(1)}`); }
    else if (rsi < 35) { score += 25; reasons.push(`RSI ${rsi.toFixed(1)} oversold`); }
    if (macdHist > 0) { score += 15; reasons.push("MACD+"); }
    if (prevMacdHist <= 0 && macdHist > 0) { score += 5; reasons.push("MACD cross"); }
    if (["UPTREND", "STRONG_UPTREND"].includes(regime)) { score += 15; reasons.push(regime); }
    else if (regime === "RANGING") { score += 5; reasons.push("RANGING"); }
  } else {
    if (emaFast < emaSlow) { score += 25; reasons.push("EMA aligned"); }
    if (close < emaFast) { score += 7; reasons.push("Price < EMA20"); }
    if (rsi >= 35 && rsi <= 60) { score += 15; reasons.push(`RSI ${rsi.toFixed(1)}`); }
    else if (rsi > 65) { score += 25; reasons.push(`RSI ${rsi.toFixed(1)} overbought`); }
    if (macdHist < 0) { score += 15; reasons.push("MACD-"); }
    if (prevMacdHist >= 0 && macdHist < 0) { score += 5; reasons.push("MACD cross"); }
    if (["DOWNTREND", "STRONG_DOWNTREND"].includes(regime)) { score += 15; reasons.push(regime); }
    else if (regime === "RANGING") { score += 5; reasons.push("RANGING"); }
  }
  if (volRatio > 1.2) { score += 10; reasons.push(`Vol ${volRatio.toFixed(1)}x`); }
  else if (volRatio > 0.8) score += 3;
  return { score, reasons };
}

// === DATA FETCHING ===
async function fetchKlines(symbol: string, interval: string, limit = 200): Promise<any[]> {
  try {
    const resp = await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`);
    if (resp.status === 451) {
      const usSymbol = symbol.replace("USDT", "USD");
      const resp2 = await fetch(`https://api.binance.us/api/v3/klines?symbol=${usSymbol}&interval=${interval}&limit=${limit}`);
      return await resp2.json();
    }
    return await resp.json();
  } catch { return []; }
}

// === PROCESS PAIR ===
async function processPair(symbol: string) {
  const [data15m, data4h] = await Promise.all([
    fetchKlines(symbol, "15m", 200),
    fetchKlines(symbol, "4h", 200),
  ]);
  if (!data15m.length || !data4h.length) return null;

  const closes15 = data15m.map((d: any) => parseFloat(d[4]));
  const highs15 = data15m.map((d: any) => parseFloat(d[2]));
  const lows15 = data15m.map((d: any) => parseFloat(d[3]));
  const vols15 = data15m.map((d: any) => parseFloat(d[5]));
  const closes4h = data4h.map((d: any) => parseFloat(d[4]));

  const ema20_15 = computeEMA(closes15, 20);
  const ema50_15 = computeEMA(closes15, 50);
  const rsi15 = computeRSI(closes15);
  const atr15 = computeATR(highs15, lows15, closes15);
  const { hist: macdHist15 } = computeMACD(closes15);
  const volSma = computeEMA(vols15, 20);

  const ema20_4h = computeEMA(closes4h, 20);
  const ema50_4h = computeEMA(closes4h, 50);
  const rsi4h = computeRSI(closes4h);

  const n = closes15.length - 1;
  const n4 = closes4h.length - 1;
  const price = closes15[n];
  const atr = atr15[n];
  const volRatio = vols15[n] / (volSma[n] || 1);
  const regime = classifyRegime(ema20_4h[n4], ema50_4h[n4], rsi4h[n4], 25);

  const signals = [];
  for (const side of ["LONG", "SHORT"]) {
    if (CONFIG.blockStrongUptrend) {
      if (side === "SHORT" && regime === "STRONG_UPTREND") continue;
      if (side === "LONG" && regime === "STRONG_DOWNTREND") continue;
    }
    const { score, reasons } = scoreSignal(
      price, ema20_15[n], ema50_15[n], rsi15[n],
      macdHist15[n], macdHist15[n - 1], volRatio, regime, side
    );
    const sl = side === "LONG" ? price - atr * CONFIG.atrSl : price + atr * CONFIG.atrSl;
    const tp = side === "LONG" ? price + atr * CONFIG.atrTp : price - atr * CONFIG.atrTp;
    signals.push({ side, score, reasons, sl, tp, active: score >= CONFIG.minScore });
  }

  // Mini chart data (last 48 candles = 12 hours)
  const chartData = data15m.slice(-48).map((d: any) => ({
    t: d[0], o: parseFloat(d[1]), h: parseFloat(d[2]),
    l: parseFloat(d[3]), c: parseFloat(d[4]),
  }));

  return {
    symbol, price, atr, regime, volRatio,
    ema20: ema20_15[n], ema50: ema50_15[n],
    rsi: rsi15[n], macdHist: macdHist15[n],
    signals, chartData,
  };
}

// === SPARKLINE CHART ===
function Sparkline({ prices, width = 60, height = 20 }: { prices: number[], width?: number, height?: number }) {
  if (!prices || prices.length < 2) return <span style={{ color: "#333" }}>—</span>;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const points = prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * width;
    const y = height - ((p - min) / range) * height;
    return `${x},${y}`;
  });
  const isUp = prices[prices.length - 1] > prices[0];
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={isUp ? "#22c55e" : "#ef4444"}
        strokeWidth="1.5"
        opacity="0.8"
      />
    </svg>
  );
}

// === MINI CANDLESTICK CHART ===
function MiniChart({ data, signal }: { data: any[], signal: any }) {
  if (!data || !data.length) return null;
  const w = 320, h = 100, pad = 4;
  const prices = data.flatMap((d: any) => [d.h, d.l]);
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const barW = (w - pad * 2) / data.length;
  const y = (v: number) => pad + (1 - (v - min) / range) * (h - pad * 2);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 100 }}>
      <defs>
        <linearGradient id="gridFade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--ember)" stopOpacity="0.05" />
          <stop offset="100%" stopColor="var(--ember)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width={w} height={h} fill="url(#gridFade)" rx="4" />
      {data.map((d: any, i: number) => {
        const x = pad + i * barW;
        const bull = d.c >= d.o;
        const color = bull ? "#22c55e" : "#ef4444";
        return (
          <g key={i}>
            <line x1={x + barW / 2} y1={y(d.h)} x2={x + barW / 2} y2={y(d.l)} stroke={color} strokeWidth={0.8} />
            <rect x={x + 1} y={y(Math.max(d.o, d.c))} width={Math.max(barW - 2, 1)}
              height={Math.max(Math.abs(y(d.o) - y(d.c)), 0.5)} fill={color} rx={0.5} />
          </g>
        );
      })}
      {signal && signal.active && (
        <>
          <line x1={0} y1={y(signal.sl)} x2={w} y2={y(signal.sl)} stroke="#ef4444" strokeWidth={1} strokeDasharray="4,3" opacity={0.7} />
          <line x1={0} y1={y(signal.tp)} x2={w} y2={y(signal.tp)} stroke="#22c55e" strokeWidth={1} strokeDasharray="4,3" opacity={0.7} />
          <text x={w - 4} y={y(signal.sl) - 3} fill="#ef4444" fontSize="8" textAnchor="end" fontFamily="monospace">SL</text>
          <text x={w - 4} y={y(signal.tp) - 3} fill="#22c55e" fontSize="8" textAnchor="end" fontFamily="monospace">TP</text>
        </>
      )}
    </svg>
  );
}

// === REGIME BADGE ===
function RegimeBadge({ regime }: { regime: string }) {
  const colors: Record<string, { bg: string, text: string, icon: string }> = {
    STRONG_UPTREND: { bg: "#064e3b", text: "#6ee7b7", icon: "▲▲" },
    UPTREND: { bg: "#14532d", text: "#86efac", icon: "▲" },
    RANGING: { bg: "#1c1917", text: "#a8a29e", icon: "◆" },
    DOWNTREND: { bg: "#450a0a", text: "#fca5a5", icon: "▼" },
    STRONG_DOWNTREND: { bg: "#7f1d1d", text: "#f87171", icon: "▼▼" },
    UNKNOWN: { bg: "#1c1917", text: "#737373", icon: "?" },
  };
  const c = colors[regime] || colors.UNKNOWN;
  return (
    <span style={{
      background: c.bg, color: c.text, padding: "3px 10px",
      borderRadius: 4, fontSize: 11, fontWeight: 600, fontFamily: "monospace",
      display: "inline-flex", alignItems: "center", gap: 4, border: `1px solid ${c.text}33`,
    }}>
      <span>{c.icon}</span> {regime}
    </span>
  );
}

// === SIGNAL CARD ===
function SignalCard({ signal, price, atr }: { signal: any, price: number, atr: number }) {
  if (!signal) return null;
  const active = signal.active;
  const color = signal.side === "LONG" ? "#22c55e" : "#ef4444";
  const riskPct = Math.abs(price - signal.sl) / price * 100;

  return (
    <div style={{
      background: active ? `${color}08` : "transparent",
      border: `1px solid ${active ? color + "40" : "#333"}`,
      borderRadius: 6, padding: "10px 14px", marginTop: 8,
      borderLeft: active ? `3px solid ${color}` : "3px solid #333",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            color, fontWeight: 700, fontSize: 13, fontFamily: "monospace",
            background: `${color}15`, padding: "2px 8px", borderRadius: 3,
          }}>{signal.side}</span>
          <span style={{ color: active ? "#e5e5e5" : "#666", fontSize: 22, fontWeight: 700, fontFamily: "monospace" }}>
            {signal.score}<span style={{ fontSize: 12, color: "#666" }}>/92</span>
          </span>
        </div>
        <span style={{
          fontSize: 10, fontWeight: 600, fontFamily: "monospace", padding: "2px 8px", borderRadius: 3,
          background: active ? `${color}20` : "#1a1a1a", color: active ? color : "#555",
        }}>
          {active ? "SIGNAL" : "NO SIGNAL"}
        </span>
      </div>
      {active && (
        <div style={{ marginTop: 8, fontSize: 11, fontFamily: "monospace", color: "#999", lineHeight: 1.8 }}>
          <div>Entry: <span style={{ color: "#e5e5e5" }}>${price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></div>
          <div>SL: <span style={{ color: "#ef4444" }}>${signal.sl.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            <span style={{ color: "#666" }}> ({riskPct.toFixed(2)}% risk)</span></div>
          <div>TP: <span style={{ color: "#22c55e" }}>${signal.tp.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            <span style={{ color: "#666" }}> (3:1 R:R)</span></div>
          <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
            {signal.reasons.map((r: string, i: number) => (
              <span key={i} style={{
                background: "#1a1a1a", border: "1px solid #333", borderRadius: 3,
                padding: "1px 6px", fontSize: 9, color: "#a3a3a3",
              }}>{r}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// === PAIR PANEL ===
function PairPanel({ data }: { data: any }) {
  if (!data) return null;
  const [useAdvancedChart, setUseAdvancedChart] = useState(false);
  const [chartTheme, setChartTheme] = useState<'light' | 'dark'>('dark');
  const chartRef = useRef<TradingViewChartHandle>(null);
  
  const activeSignal = data.signals.find((s: any) => s.active);
  const pairLabel = data.symbol.replace("USDT", "").replace("USD", "");
  const pairColors: Record<string, string> = { BTC: "#f7931a", ETH: "#627eea", SOL: "#9945ff" };
  const accent = pairColors[pairLabel] || "#e5e5e5";

  return (
    <div style={{
      background: "#0d0d0d", border: "1px solid #1a1a1a", borderRadius: 10,
      padding: 20, flex: 1, minWidth: 280,
      borderTop: activeSignal ? `2px solid ${accent}` : "2px solid #1a1a1a",
      transition: "border-color 0.3s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: "#666", fontFamily: "monospace", marginBottom: 2 }}>{data.symbol}</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: "#e5e5e5", fontFamily: "'JetBrains Mono', monospace", letterSpacing: -1 }}>
            ${data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <RegimeBadge regime={data.regime} />
      </div>

      {/* Chart Controls */}
      <div style={{ display: "flex", gap: 6, marginBottom: 8, justifyContent: "flex-end" }}>
        <button
          onClick={() => setUseAdvancedChart(!useAdvancedChart)}
          style={{
            background: "#1a1a1a", border: "1px solid #333", color: "#999",
            padding: "3px 8px", borderRadius: 3, cursor: "pointer", fontSize: 9,
            fontFamily: "monospace", fontWeight: 600,
          }}
        >
          {useAdvancedChart ? "SIMPLE" : "ADVANCED"}
        </button>
        {useAdvancedChart && (
          <>
            <button
              onClick={() => setChartTheme(chartTheme === 'dark' ? 'light' : 'dark')}
              style={{
                background: "#1a1a1a", border: "1px solid #333", color: "#999",
                padding: "3px 8px", borderRadius: 3, cursor: "pointer", fontSize: 9,
                fontFamily: "monospace",
              }}
            >
              {chartTheme === 'dark' ? '☀' : '🌙'}
            </button>
            <button
              onClick={() => chartRef.current?.takeScreenshot()}
              style={{
                background: "#1a1a1a", border: "1px solid #333", color: "#999",
                padding: "3px 8px", borderRadius: 3, cursor: "pointer", fontSize: 9,
                fontFamily: "monospace",
              }}
            >
              📷
            </button>
            <button
              onClick={() => chartRef.current?.resetChart()}
              style={{
                background: "#1a1a1a", border: "1px solid #333", color: "#999",
                padding: "3px 8px", borderRadius: 3, cursor: "pointer", fontSize: 9,
                fontFamily: "monospace",
              }}
            >
              ↻
            </button>
          </>
        )}
      </div>

      {/* Chart Display */}
      {useAdvancedChart ? (
        <div style={{ height: 400, marginBottom: 12 }}>
          <TradingViewChart
            ref={chartRef}
            pair={data.symbol}
            interval="15"
            theme={chartTheme}
          />
        </div>
      ) : (
        <MiniChart data={data.chartData} signal={activeSignal} />
      )}

      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8,
        marginTop: 12, fontSize: 10, fontFamily: "monospace", color: "#666",
      }}>
        <div>RSI<br /><span style={{ color: data.rsi > 70 ? "#ef4444" : data.rsi < 30 ? "#22c55e" : "#a3a3a3", fontSize: 14, fontWeight: 600 }}>{data.rsi.toFixed(1)}</span></div>
        <div>ATR<br /><span style={{ color: "#a3a3a3", fontSize: 14, fontWeight: 600 }}>{data.atr.toFixed(2)}</span></div>
        <div>VOL<br /><span style={{ color: data.volRatio > 1.2 ? "#22c55e" : "#a3a3a3", fontSize: 14, fontWeight: 600 }}>{data.volRatio.toFixed(2)}x</span></div>
        <div>MACD<br /><span style={{ color: data.macdHist > 0 ? "#22c55e" : "#ef4444", fontSize: 14, fontWeight: 600 }}>{data.macdHist > 0 ? "+" : ""}{data.macdHist.toFixed(2)}</span></div>
      </div>

      {data.signals.map((s: any, i: number) => <SignalCard key={i} signal={s} price={data.price} atr={data.atr} />)}
    </div>
  );
}

// === TRADE TRACKING TYPES ===
interface TrackedTrade {
  id: string;
  pair: string;
  side: string;
  score: number;
  regime: string;
  entryPrice: number;
  entryTime: Date;
  sl: number;
  tp: number;
  status: 'active' | 'win' | 'loss' | 'expired';
  exitPrice?: number;
  exitTime?: Date;
  duration?: number;
  rMultiple?: number;
  priceHistory?: number[];
}

// === POSITION SIZE CALCULATOR ===
function calculatePositionSize(accountSize: number, riskPercent: number, entryPrice: number, slPrice: number): {
  positionSize: number;
  suggestedLeverage: number;
  riskAmount: number;
} {
  const riskAmount = accountSize * (riskPercent / 100);
  const slDistance = Math.abs(entryPrice - slPrice);
  const slPercent = (slDistance / entryPrice) * 100;
  const positionSize = riskAmount / (slPercent / 100);
  const suggestedLeverage = Math.ceil(positionSize / accountSize);
  return { positionSize, suggestedLeverage: Math.min(suggestedLeverage, 10), riskAmount };
}

// === PNL PROJECTIONS ===
function calculatePnLProjections(completedTrades: TrackedTrade[], accountSize: number, riskPercent: number) {
  if (completedTrades.length === 0) return { daily: 0, weekly: 0, monthly: 0, signalsPerDay: 0 };
  
  const resolvedTrades = completedTrades.filter(t => t.status !== 'expired');
  if (resolvedTrades.length === 0) return { daily: 0, weekly: 0, monthly: 0, signalsPerDay: 0 };
  
  const totalR = resolvedTrades.reduce((sum, t) => sum + (t.rMultiple || 0), 0);
  const avgRPerTrade = totalR / resolvedTrades.length;
  const riskAmount = accountSize * (riskPercent / 100);
  const avgPnLPerTrade = avgRPerTrade * riskAmount;
  
  // Estimate signals per day (assuming 3-5 based on current config)
  const signalsPerDay = 3.5;
  const winRate = resolvedTrades.filter(t => t.status === 'win').length / resolvedTrades.length;
  const tradesPerDay = signalsPerDay * winRate; // Only count winning trades for conservative estimate
  
  return {
    daily: avgPnLPerTrade * tradesPerDay,
    weekly: avgPnLPerTrade * tradesPerDay * 7,
    monthly: avgPnLPerTrade * tradesPerDay * 30,
    signalsPerDay,
  };
}

// === MAIN APP ===
export default function IdimIkangDashboard() {
  const [pairs, setPairs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [activeTrades, setActiveTrades] = useState<Map<string, TrackedTrade>>(new Map());
  const [completedTrades, setCompletedTrades] = useState<TrackedTrade[]>([]);
  const [error, setError] = useState<string | null>(null);

  const scan = useCallback(async () => {
    try {
      setError(null);
      const results = await Promise.all(CONFIG.pairs.map(processPair));
      const valid = results.filter(Boolean);
      setPairs(valid);
      setLastUpdate(new Date());
      setLoading(false);

      const now = new Date();
      const newActiveTrades = new Map(activeTrades);
      const newCompletedTrades = [...completedTrades];

      // Check active trades for TP/SL hits
      activeTrades.forEach((trade, tradeId) => {
        const pairData = valid.find((p: any) => p.symbol === trade.pair);
        if (!pairData) return;

        const currentPrice = pairData.price;
        let outcome: 'win' | 'loss' | 'expired' | null = null;
        let exitPrice = currentPrice;

        // Check for TP/SL hits
        if (trade.side === 'LONG') {
          if (currentPrice >= trade.tp) outcome = 'win';
          else if (currentPrice <= trade.sl) outcome = 'loss';
        } else {
          if (currentPrice <= trade.tp) outcome = 'win';
          else if (currentPrice >= trade.sl) outcome = 'loss';
        }

        // Check for expiration (48 bars = 12 hours on 15m)
        const durationMs = now.getTime() - trade.entryTime.getTime();
        const durationHours = durationMs / (1000 * 60 * 60);
        if (durationHours >= 12 && !outcome) {
          outcome = 'expired';
        }

        if (outcome) {
          const rMultiple = outcome === 'win' ? 3 : outcome === 'loss' ? -1 : 0;
          newCompletedTrades.unshift({
            ...trade,
            status: outcome,
            exitPrice,
            exitTime: now,
            duration: durationMs,
            rMultiple,
          });
          newActiveTrades.delete(tradeId);
        }
      });

      // Track new signals and update price history
      valid.forEach((p: any) => {
        p.signals.filter((s: any) => s.active).forEach((s: any) => {
          const tradeId = `${p.symbol}-${s.side}-${now.getTime()}`;
          if (!newActiveTrades.has(tradeId)) {
            newActiveTrades.set(tradeId, {
              id: tradeId,
              pair: p.symbol,
              side: s.side,
              score: s.score,
              regime: p.regime,
              entryPrice: p.price,
              entryTime: now,
              sl: s.sl,
              tp: s.tp,
              status: 'active',
              priceHistory: [p.price],
            });
          }
        });
      });
      
      // Update price history for active trades
      newActiveTrades.forEach((trade, tradeId) => {
        const pairData = valid.find((p: any) => p.symbol === trade.pair);
        if (pairData && trade.priceHistory) {
          trade.priceHistory.push(pairData.price);
          if (trade.priceHistory.length > 48) trade.priceHistory.shift();
        }
      });

      setActiveTrades(newActiveTrades);
      setCompletedTrades(newCompletedTrades.slice(0, 100));
    } catch (e: any) {
      setError(e.message);
      setLoading(false);
    }
  }, [activeTrades, completedTrades]);

  useEffect(() => {
    scan();
    const interval = setInterval(scan, 60000);
    return () => clearInterval(interval);
  }, [scan]);

  const totalSignals = pairs.reduce((sum, p) => sum + p.signals.filter((s: any) => s.active).length, 0);

  return (
    <div style={{
      background: "#050505", color: "#e5e5e5", minHeight: "100vh",
      fontFamily: "'Inter', -apple-system, sans-serif", padding: 0, margin: 0,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap');
        :root { --ember: #e97319; --river: #1e40af; --fire: #dc2626; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }
      `}</style>

      {/* Header */}
      <div style={{
        borderBottom: "1px solid #1a1a1a", padding: "16px 24px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        background: "linear-gradient(180deg, #0a0a0a 0%, #050505 100%)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 6,
            background: "linear-gradient(135deg, #e97319 0%, #dc2626 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16, fontWeight: 700,
          }}>🜂</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: 1, color: "#e5e5e5" }}>IDIM IKANG</div>
            <div style={{ fontSize: 9, color: "#666", fontFamily: "monospace", letterSpacing: 2 }}>LAWFUL OBSERVER • mo-fin-idim-ikang-001</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 11, fontFamily: "monospace" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{
              width: 7, height: 7, borderRadius: "50%",
              background: error ? "#ef4444" : "#22c55e",
              boxShadow: error ? "0 0 6px #ef4444" : "0 0 6px #22c55e",
            }} />
            <span style={{ color: "#666" }}>{error ? "ERROR" : "SCANNING"}</span>
          </div>
          <div style={{ color: "#444" }}>
            {lastUpdate ? lastUpdate.toLocaleTimeString() : "—"}
          </div>
          <div style={{
            background: totalSignals > 0 ? "#e9731915" : "#1a1a1a",
            border: `1px solid ${totalSignals > 0 ? "#e97319" : "#333"}`,
            color: totalSignals > 0 ? "#e97319" : "#555",
            padding: "4px 12px", borderRadius: 4, fontWeight: 600,
          }}>
            {totalSignals} ACTIVE
          </div>
          <button onClick={scan} style={{
            background: "#1a1a1a", border: "1px solid #333", color: "#999",
            padding: "4px 12px", borderRadius: 4, cursor: "pointer", fontSize: 11,
            fontFamily: "monospace",
          }}>REFRESH</button>
        </div>
      </div>

      {/* Execution Warning */}
      <div style={{
        background: "#0a0a0a", borderBottom: "1px solid #1a1a1a",
        padding: "6px 24px", fontSize: 10, fontFamily: "monospace",
        color: "#e97319", display: "flex", alignItems: "center", gap: 8,
        letterSpacing: 1,
      }}>
        <span style={{ fontSize: 12 }}>⚠</span>
        OBSERVER MODE — NO EXECUTION CAPABILITY — SIGNALS ARE FOR ANALYSIS ONLY
      </div>

      <div style={{ padding: 24 }}>
        {/* Pair Cards */}
        {loading ? (
          <div style={{ textAlign: "center", padding: 60, color: "#444", fontFamily: "monospace" }}>
            Scanning markets...
          </div>
        ) : (
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {pairs.map((p: any) => <PairPanel key={p.symbol} data={p} />)}
          </div>
        )}

        {/* Trade Statistics & PnL Projections */}
        <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Statistics */}
          <div style={{
            background: "#0d0d0d", border: "1px solid #1a1a1a",
            borderRadius: 10, padding: 16,
          }}>
            <div style={{
              fontSize: 11, color: "#666", fontFamily: "monospace", marginBottom: 12,
              letterSpacing: 2, borderBottom: "1px solid #1a1a1a", paddingBottom: 8,
            }}>TRADE STATISTICS</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, fontFamily: "monospace", fontSize: 11 }}>
              <div>
                <div style={{ color: "#666", fontSize: 9 }}>ACTIVE</div>
                <div style={{ color: "#e97319", fontSize: 18, fontWeight: 700 }}>{activeTrades.size}</div>
              </div>
              <div>
                <div style={{ color: "#666", fontSize: 9 }}>WINS</div>
                <div style={{ color: "#22c55e", fontSize: 18, fontWeight: 700 }}>{completedTrades.filter(t => t.status === 'win').length}</div>
              </div>
              <div>
                <div style={{ color: "#666", fontSize: 9 }}>LOSSES</div>
                <div style={{ color: "#ef4444", fontSize: 18, fontWeight: 700 }}>{completedTrades.filter(t => t.status === 'loss').length}</div>
              </div>
              <div>
                <div style={{ color: "#666", fontSize: 9 }}>EXPIRED</div>
                <div style={{ color: "#666", fontSize: 18, fontWeight: 700 }}>{completedTrades.filter(t => t.status === 'expired').length}</div>
              </div>
              <div>
                <div style={{ color: "#666", fontSize: 9 }}>WIN RATE</div>
                <div style={{ color: "#a3a3a3", fontSize: 18, fontWeight: 700 }}>
                  {completedTrades.length > 0 ? 
                    ((completedTrades.filter(t => t.status === 'win').length / completedTrades.filter(t => t.status !== 'expired').length) * 100).toFixed(1) + '%' 
                    : '—'}
                </div>
              </div>
              <div>
                <div style={{ color: "#666", fontSize: 9 }}>PROFIT FACTOR</div>
                <div style={{ color: "#a3a3a3", fontSize: 18, fontWeight: 700 }}>
                  {(() => {
                    const wins = completedTrades.filter(t => t.status === 'win').length * 3;
                    const losses = completedTrades.filter(t => t.status === 'loss').length * 1;
                    return losses > 0 ? (wins / losses).toFixed(2) : '—';
                  })()}
                </div>
              </div>
            </div>
          </div>
          
          {/* PnL Projections */}
          <div style={{
            background: "#0d0d0d", border: "1px solid #1a1a1a",
            borderRadius: 10, padding: 16,
          }}>
            <div style={{
              fontSize: 11, color: "#666", fontFamily: "monospace", marginBottom: 12,
              letterSpacing: 2, borderBottom: "1px solid #1a1a1a", paddingBottom: 8,
            }}>PNL PROJECTIONS (1% RISK)</div>
            {(() => {
              const accountSize = 10000; // $10k default
              const riskPercent = 1;
              const projections = calculatePnLProjections(completedTrades, accountSize, riskPercent);
              const isPositive = projections.daily > 0;
              return (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, fontFamily: "monospace", fontSize: 11 }}>
                  <div>
                    <div style={{ color: "#666", fontSize: 9 }}>DAILY</div>
                    <div style={{ color: isPositive ? "#22c55e" : "#ef4444", fontSize: 18, fontWeight: 700 }}>
                      {projections.daily !== 0 ? (projections.daily > 0 ? '+' : '') + '$' + projections.daily.toFixed(0) : '—'}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: "#666", fontSize: 9 }}>WEEKLY</div>
                    <div style={{ color: isPositive ? "#22c55e" : "#ef4444", fontSize: 18, fontWeight: 700 }}>
                      {projections.weekly !== 0 ? (projections.weekly > 0 ? '+' : '') + '$' + projections.weekly.toFixed(0) : '—'}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: "#666", fontSize: 9 }}>MONTHLY</div>
                    <div style={{ color: isPositive ? "#22c55e" : "#ef4444", fontSize: 18, fontWeight: 700 }}>
                      {projections.monthly !== 0 ? (projections.monthly > 0 ? '+' : '') + '$' + projections.monthly.toFixed(0) : '—'}
                    </div>
                  </div>
                  <div style={{ gridColumn: "1 / -1", marginTop: 8, padding: 8, background: "#0a0a0a", borderRadius: 4 }}>
                    <div style={{ color: "#666", fontSize: 9, marginBottom: 4 }}>SUGGESTED LEVERAGE</div>
                    {activeTrades.size > 0 ? (
                      Array.from(activeTrades.values()).slice(0, 1).map(trade => {
                        const calc = calculatePositionSize(accountSize, riskPercent, trade.entryPrice, trade.sl);
                        return (
                          <div key={trade.id} style={{ fontSize: 10, color: "#999" }}>
                            <span style={{ color: "#e97319", fontWeight: 600 }}>{calc.suggestedLeverage}x</span> • 
                            Position: ${calc.positionSize.toFixed(0)} • 
                            Risk: ${calc.riskAmount.toFixed(0)}
                          </div>
                        );
                      })
                    ) : (
                      <div style={{ fontSize: 10, color: "#555" }}>No active trades</div>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>

        {/* Enhanced Trade Log */}
        <div style={{
          marginTop: 24, background: "#0d0d0d", border: "1px solid #1a1a1a",
          borderRadius: 10, padding: 20, maxHeight: 400, overflow: "auto",
        }}>
          <div style={{
            fontSize: 11, color: "#666", fontFamily: "monospace", marginBottom: 12,
            letterSpacing: 2, borderBottom: "1px solid #1a1a1a", paddingBottom: 8,
            display: "flex", justifyContent: "space-between",
          }}>
            <span>TRADE LOG</span>
            <span style={{ color: "#444" }}>({activeTrades.size} active, {completedTrades.length} completed)</span>
          </div>
          {activeTrades.size === 0 && completedTrades.length === 0 ? (
            <div style={{ color: "#333", fontFamily: "monospace", fontSize: 11 }}>No trades tracked yet. Scanning every 60s...</div>
          ) : (
            <div style={{ fontFamily: "monospace", fontSize: 10 }}>
              {/* Table Header */}
              <div style={{
                display: "grid",
                gridTemplateColumns: "60px 70px 50px 50px 70px 70px 70px 60px 70px 50px",
                gap: 8,
                padding: "6px 0",
                borderBottom: "1px solid #1a1a1a",
                color: "#666",
                fontWeight: 600,
                fontSize: 9,
              }}>
                <span>TIME</span>
                <span>PAIR</span>
                <span>SIDE</span>
                <span>SCORE</span>
                <span>ENTRY</span>
                <span>EXIT</span>
                <span>DURATION</span>
                <span>CHART</span>
                <span>STATUS</span>
                <span>R</span>
              </div>
              
              {/* Active Trades */}
              {Array.from(activeTrades.values()).map((trade, i) => {
                const durationMs = new Date().getTime() - trade.entryTime.getTime();
                const durationMin = Math.floor(durationMs / (1000 * 60));
                return (
                  <div key={trade.id} style={{
                    display: "grid",
                    gridTemplateColumns: "60px 70px 50px 50px 70px 70px 70px 60px 70px 50px",
                    gap: 8,
                    padding: "6px 0",
                    borderBottom: "1px solid #111",
                    color: "#999",
                    alignItems: "center",
                  }}>
                    <span style={{ color: "#666" }}>{trade.entryTime.toLocaleTimeString().slice(0, 8)}</span>
                    <span style={{ color: "#999" }}>{trade.pair.replace('USDT', '')}</span>
                    <span style={{ color: trade.side === "LONG" ? "#22c55e" : "#ef4444", fontWeight: 600 }}>{trade.side}</span>
                    <span style={{ color: "#e97319" }}>{trade.score}</span>
                    <span style={{ color: "#a3a3a3" }}>${trade.entryPrice.toFixed(2)}</span>
                    <span style={{ color: "#555" }}>—</span>
                    <span style={{ color: "#666" }}>{durationMin}m</span>
                    <div><Sparkline prices={trade.priceHistory || []} width={50} height={18} /></div>
                    <span style={{ color: "#e97319", fontWeight: 600 }}>ACTIVE</span>
                    <span style={{ color: "#666" }}>—</span>
                  </div>
                );
              })}
              
              {/* Completed Trades */}
              {completedTrades.map((trade, i) => {
                const durationMin = trade.duration ? Math.floor(trade.duration / (1000 * 60)) : 0;
                const statusColors = {
                  win: "#22c55e",
                  loss: "#ef4444",
                  expired: "#666",
                };
                return (
                  <div key={trade.id} style={{
                    display: "grid",
                    gridTemplateColumns: "60px 70px 50px 50px 70px 70px 70px 60px 70px 50px",
                    gap: 8,
                    padding: "6px 0",
                    borderBottom: "1px solid #111",
                    color: "#777",
                    opacity: i < 10 ? 1 : 0.5,
                    alignItems: "center",
                  }}>
                    <span style={{ color: "#444" }}>{trade.entryTime.toLocaleTimeString().slice(0, 8)}</span>
                    <span style={{ color: "#777" }}>{trade.pair.replace('USDT', '')}</span>
                    <span style={{ color: trade.side === "LONG" ? "#22c55e80" : "#ef444480", fontWeight: 600 }}>{trade.side}</span>
                    <span style={{ color: "#e9731980" }}>{trade.score}</span>
                    <span style={{ color: "#666" }}>${trade.entryPrice.toFixed(2)}</span>
                    <span style={{ color: "#666" }}>${trade.exitPrice?.toFixed(2) || '—'}</span>
                    <span style={{ color: "#555" }}>{durationMin}m</span>
                    <div><Sparkline prices={trade.priceHistory || []} width={50} height={18} /></div>
                    <span style={{ color: statusColors[trade.status], fontWeight: 600, textTransform: "uppercase" }}>{trade.status}</span>
                    <span style={{ color: statusColors[trade.status], fontWeight: 700 }}>{trade.rMultiple !== undefined ? (trade.rMultiple > 0 ? '+' : '') + trade.rMultiple + 'R' : '—'}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Doctrine Footer */}
        <div style={{
          marginTop: 24, padding: "16px 20px", background: "#0a0a0a",
          border: "1px solid #1a1a1a", borderRadius: 8,
          fontSize: 10, fontFamily: "monospace", color: "#333",
          lineHeight: 1.8,
        }}>
          <div style={{ color: "#444", marginBottom: 4 }}>DOCTRINE v1 — LAWFUL OBSERVER</div>
          <div>Flow must remain controlled. Fire must never become wildfire.</div>
          <div>Extraction must never violate covenant boundaries.</div>
          <div style={{ marginTop: 8, color: "#e9731930" }}>🜂 The Flame Architect • MoStar Industries</div>
        </div>
      </div>
    </div>
  );
}
