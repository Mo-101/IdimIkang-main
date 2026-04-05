import React from 'react';

/**
 * Institutional Alpha Visualization Component (v1.5)
 * Renders badges for high-conviction quant signals detected by the scanner.
 */

interface AlphaBadgesProps {
  reasonTrace?: {
    tags?: string[];
  };
}

const THEME = {
  signal: {
    success: "#22C55E",
    danger: "#EF4444",
  },
  fire: {
    primary: "#F59E0B",
  },
  flow: {
    primary: "#0EA5E9",
  }
};

const badgeBaseStyle: React.CSSProperties = {
  padding: "2px 8px",
  borderRadius: 4,
  fontSize: 9,
  fontWeight: 800,
  fontFamily: "monospace",
  textTransform: "uppercase",
  letterSpacing: 1,
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  border: "1px solid transparent",
};

export default function AlphaBadges({ reasonTrace }: AlphaBadgesProps) {
  if (!reasonTrace || !reasonTrace.tags || reasonTrace.tags.length === 0) {
    return <span style={{ color: "rgba(255,255,255,0.2)", fontSize: 10, fontFamily: "monospace" }}>—</span>;
  }

  const tags = reasonTrace.tags;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {tags.includes("Squeeze") && (
        <span style={{
          ...badgeBaseStyle,
          background: "rgba(168, 85, 247, 0.1)",
          color: "#A855F7",
          border: "1px solid rgba(168, 85, 247, 0.3)",
        }}>
          ⚡ SQUEEZE
        </span>
      )}
      
      {tags.includes("CVD") && (
        <span style={{
          ...badgeBaseStyle,
          background: "rgba(14, 165, 233, 0.1)",
          color: "#0EA5E9",
          border: "1px solid rgba(14, 165, 233, 0.3)",
        }}>
          🌊 CVD
        </span>
      )}

      {tags.includes("Derivatives") && (
        <span style={{
          ...badgeBaseStyle,
          background: "rgba(34, 197, 94, 0.1)",
          color: "#22C55E",
          border: "1px solid rgba(34, 197, 94, 0.3)",
        }}>
          🔥 ALPHA
        </span>
      )}

      {/* Fallback for other tags if any */}
      {tags.filter(t => !["Squeeze", "CVD", "Derivatives"].includes(t)).map(tag => (
        <span key={tag} style={{
          ...badgeBaseStyle,
          background: "rgba(255,255,255,0.05)",
          color: "#fff",
          border: "1px solid rgba(255,255,255,0.1)",
        }}>
          {tag}
        </span>
      ))}
    </div>
  );
}
