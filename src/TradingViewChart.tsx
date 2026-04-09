import React, { useEffect, useRef } from 'react';

interface TradingViewChartProps {
  symbol: string;
  theme: any;
  interval?: string;
}

declare global {
  interface Window {
    TradingView: any;
  }
}

const TradingViewChart: React.FC<TradingViewChartProps> = ({ symbol, theme, interval = '15' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const containerId = `tradingview_widget_${symbol.replace(/[^a-zA-Z0-9]/g, '_')}`;

  useEffect(() => {
    const scriptId = 'tradingview-core-script';
    let script = document.getElementById(scriptId) as HTMLScriptElement;

    const initWidget = () => {
      if (containerRef.current && window.TradingView) {
        new window.TradingView.widget({
          autosize: true,
          symbol: `BINANCE:${symbol}.P`, // Defaults to Binance Futures for Idim Ikang
          interval: interval,
          timezone: 'Etc/UTC',
          theme: 'dark',
          style: '1',
          locale: 'en',
          toolbar_bg: '#f1f3f6',
          enable_publishing: false,
          hide_side_toolbar: false,
          allow_symbol_change: true,
          container_id: containerId,
          backgroundColor: theme?.base?.sovereign || 'rgba(0, 0, 0, 1)',
          gridColor: 'rgba(255, 255, 255, 0.05)',
          studies: [
            'MASimple@tv-basicstudies', // EMA 20/50 proxies
            'RSI@tv-basicstudies'
          ],
        });
      }
    };

    if (!script) {
      script = document.createElement('script');
      script.id = scriptId;
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = initWidget;
      document.head.appendChild(script);
    } else {
      if (window.TradingView) {
        initWidget();
      } else {
        script.addEventListener('load', initWidget);
      }
    }

    return () => {
      if (script) {
        script.removeEventListener('load', initWidget);
      }
    };
  }, [symbol, interval, containerId, theme]);

  return (
    <div 
      id={`${containerId}_container`} 
      style={{ 
        height: '100%', width: '100%', borderRadius: 16, overflow: 'hidden',
        border: `1px solid ${theme?.base?.border || 'rgba(255,255,255,0.1)'}`, background: '#000'
      }}
    >
      <div id={containerId} style={{ height: '100%', width: '100%' }} ref={containerRef} />
    </div>
  );
};

export default TradingViewChart;
