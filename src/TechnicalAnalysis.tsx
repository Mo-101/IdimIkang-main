import { useEffect, useRef } from "react";

interface TechnicalAnalysisProps {
  symbol: string;
}

export function TechnicalAnalysis({ symbol }: TechnicalAnalysisProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol,
      interval: "1h",
      width: "100%",
      isTransparent: true,
      height: "100%",
      locale: "en",
      colorTheme: "dark",
    });

    container.appendChild(script);

    return () => {
      container.innerHTML = "";
    };
  }, [symbol]);

  return (
    <div className="tradingview-widget-container" ref={containerRef} style={{ height: "100%", width: "100%" }} />
  );
}

export default TechnicalAnalysis;
