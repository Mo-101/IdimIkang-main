import React, { useEffect, useRef } from 'react';

interface TradingViewChartProps {
  symbol: string;
  theme: any;
}

declare global {
  interface Window {
    TradingView: any;
  }
}

const TradingViewChart: React.FC<TradingViewChartProps> = ({ symbol, theme }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = () => {
      if (containerRef.current) {
        new window.TradingView.widget({
          autosize: true,
          symbol: `BINANCE:${symbol}.P`, // Defaults to Binance Futures for Idim Ikang
          interval: '15',
          timezone: 'Etc/UTC',
          theme: 'dark',
          style: '1',
          locale: 'en',
          toolbar_bg: '#f1f3f6',
          enable_publishing: false,
          hide_side_toolbar: false,
          allow_symbol_change: true,
          container_id: 'tradingview_widget',
          backgroundColor: 'rgba(0, 0, 0, 1)',
          gridColor: 'rgba(255, 255, 255, 0.05)',
          studies: [
            'MASimple@tv-basicstudies', // EMA 20/50 proxies
            'RSI@tv-basicstudies'
          ],
        });
      }
    };
    document.head.appendChild(script);

    return () => {
      // Cleanup script if needed, though TV widget handles its own iframe
    };
  }, [symbol]);

  return (
    <div 
      id="tradingview_widget_container" 
      style={{ 
        height: '100%', width: '100%', borderRadius: 16, overflow: 'hidden',
        border: `1px solid ${theme.base.border}`, background: '#000'
      }}
    >
      <div id="tradingview_widget" style={{ height: '100%', width: '100%' }} ref={containerRef} />
    </div>
  );
};

export default TradingViewChart;
