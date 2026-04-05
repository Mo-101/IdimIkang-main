import React from 'react';

/**
 * Institutional Alpha Visualization Component (v1.5)
 * Renders badges for high-conviction quant signals detected by the scanner.
 */

interface AlphaBadgesProps {
  reasonTrace?: {
    tags?: string[];
    recent_squeeze_fire?: boolean;
    volume_ratio?: number;
    derivatives_bonus?: number;
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
  if (!reasonTrace) {
    return <span style={{ color: "rgba(255,255,255,0.2)", fontSize: 10, fontFamily: "monospace" }}>—</span>;
  }

  const tags = reasonTrace.tags || [];
  const hasSqueeze = reasonTrace.recent_squeeze_fire;
  const hasVol = (reasonTrace.volume_ratio || 0) >= 1.2;
  const hasAlpha = (reasonTrace.derivatives_bonus || 0) > 0;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {hasSqueeze && (
        <span style={{
          ...badgeBaseStyle,
          background: "rgba(168, 85, 247, 0.1)",
          color: "#A855F7",
          border: "1px solid rgba(168, 85, 247, 0.3)",
        }}>
          G_SQ
        </span>
      )}
      
      {hasVol && (
        <span style={{
          ...badgeBaseStyle,
          background: "rgba(14, 165, 233, 0.1)",
          color: "#0EA5E9",
          border: "1px solid rgba(14, 165, 233, 0.3)",
        }}>
          G_VOL
        </span>
      )}

      {hasAlpha && (
        <span style={{
          ...badgeBaseStyle,
          background: "rgba(34, 197, 94, 0.1)",
          color: "#22C55E",
          border: "1px solid rgba(34, 197, 94, 0.3)",
        }}>
          G_ALPHA
        </span>
      )}

      {/* Logic for legacy tags or other markers */}
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
