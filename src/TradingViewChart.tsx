import React, { useImperativeHandle, forwardRef } from 'react';

interface TradingViewChartProps {
  pair: string;
  interval?: string;
  theme?: 'light' | 'dark';
  onIntervalChange?: (interval: string) => void;
  onStudyAdd?: (studyName: string) => void;
}

export interface TradingViewChartHandle {
  takeScreenshot: () => Promise<void>;
  resetChart: () => void;
  setSymbol: (symbol: string, interval?: string) => void;
}

declare global {
  interface Window {
    TradingView: any;
    Datafeeds: any;
    Brokers: any;
    tvWidget: any;
  }
}

const TradingViewChart = forwardRef<TradingViewChartHandle, TradingViewChartProps>(
  ({ pair, interval = '15', theme = 'dark', onIntervalChange, onStudyAdd }, ref) => {
    const containerRef = React.useRef<HTMLDivElement>(null);
    const isReadyRef = React.useRef(false);
    const widgetRef = React.useRef<any>(null);

    useImperativeHandle(ref, () => ({
      takeScreenshot: async () => {
        if (!widgetRef.current || !isReadyRef.current) return;
        const canvas = await widgetRef.current.takeClientScreenshot();
        const link = document.createElement('a');
        link.download = `idim-ikang-${pair}-${Date.now()}.png`;
        link.href = canvas.toDataURL();
        link.click();
      },
      resetChart: () => {
        if (!widgetRef.current || !isReadyRef.current) return;
        widgetRef.current.activeChart().executeActionById('chartReset');
      },
      setSymbol: (symbol: string, interval: string = '15') => {
        if (!widgetRef.current || !isReadyRef.current) return;
        widgetRef.current.setSymbol(symbol, interval, () => {
          console.log(`[IDIM IKANG] Symbol changed to ${symbol}`);
        });
      }
    }));

    // Handle Theme Changes
    React.useEffect(() => {
      if (widgetRef.current && isReadyRef.current) {
        widgetRef.current.changeTheme(theme === 'dark' ? 'Dark' : 'Light').then(() => {
          const overrides = theme === 'dark' ? {
            "paneProperties.background": "#0A0B0D",
            "paneProperties.vertGridProperties.color": "#1A1B1F",
            "paneProperties.horzGridProperties.color": "#1A1B1F",
            "scalesProperties.textColor": "#8E9299",
          } : {
            "paneProperties.background": "#ffffff",
            "paneProperties.vertGridProperties.color": "#f0f3fa",
            "paneProperties.horzGridProperties.color": "#f0f3fa",
            "scalesProperties.textColor": "#131722",
          };
          widgetRef.current.applyOverrides(overrides);
        });
      }
    }, [theme]);

    // Handle Symbol Changes
    React.useEffect(() => {
      if (widgetRef.current && isReadyRef.current) {
        widgetRef.current.setSymbol(pair, widgetRef.current.activeChart().resolution(), () => {
          console.log(`[IDIM IKANG] Symbol updated to ${pair}`);
        });
      }
    }, [pair]);

    // Handle Interval Changes
    React.useEffect(() => {
      if (widgetRef.current && isReadyRef.current) {
        const currentResolution = widgetRef.current.activeChart().resolution();
        if (currentResolution !== interval) {
          widgetRef.current.activeChart().setResolution(interval, () => {
            console.log(`[IDIM IKANG] Interval updated to ${interval}`);
          });
        }
      }
    }, [interval]);

    React.useEffect(() => {
      const scriptId = 'tradingview-library-script';
      let script = document.getElementById(scriptId) as HTMLScriptElement;

      const initWidget = () => {
        if (!containerRef.current) return;
        if (widgetRef.current) return;

        // Custom Datafeed Implementation
        class CustomDatafeed {
          private _datafeedUrl = "https://demo-feed-data.tradingview.com";
          
          async onReady(callback: any) {
            setTimeout(() => callback({
              supports_search: true,
              supports_group_request: false,
              supports_marks: true,
              supports_timescale_marks: true,
              supports_time: true,
              exchanges: [{ value: 'BINANCE', name: 'Binance', desc: 'Binance Exchange' }],
              symbols_types: [{ name: 'Crypto', value: 'crypto' }],
              supported_resolutions: ['1', '5', '15', '30', '60', '240', '1D', '1W']
            }), 0);
          }

          searchSymbols(userInput: string, exchange: string, symbolType: string, onResultReadyCallback: any) {
            onResultReadyCallback([
              { symbol: 'BTCUSDT', full_name: 'BINANCE:BTCUSDT', description: 'Bitcoin / TetherUS', exchange: 'Binance', type: 'crypto' },
              { symbol: 'ETHUSDT', full_name: 'BINANCE:ETHUSDT', description: 'Ethereum / TetherUS', exchange: 'Binance', type: 'crypto' },
              { symbol: 'SOLUSDT', full_name: 'BINANCE:SOLUSDT', description: 'Solana / TetherUS', exchange: 'Binance', type: 'crypto' },
            ]);
          }

          resolveSymbol(symbolName: string, onSymbolResolvedCallback: any, _onResolveErrorCallback: any) {
            setTimeout(() => onSymbolResolvedCallback({
              name: symbolName,
              full_name: `BINANCE:${symbolName}`,
              description: symbolName,
              type: 'crypto',
              session: '24x7',
              timezone: 'Etc/UTC',
              exchange: 'Binance',
              minmov: 1,
              pricescale: 100,
              has_intraday: true,
              has_no_volume: false,
              supported_resolutions: ['1', '5', '15', '30', '60', '240', '1D', '1W'],
              volume_precision: 8,
              data_status: 'streaming',
            }), 0);
          }

          getBars(symbolInfo: any, resolution: string, periodParams: any, onHistoryCallback: any, _onErrorCallback: any) {
            const { from, to } = periodParams;
            fetch(`${this._datafeedUrl}/history?symbol=${symbolInfo.name}&resolution=${resolution}&from=${from}&to=${to}`)
              .then(r => r.json())
              .then(data => {
                if (data.s !== 'ok' && data.s !== 'no_data') {
                  _onErrorCallback(data.errmsg);
                  return;
                }
                const bars = [];
                if (data.s === 'ok') {
                  for (let i = 0; i < data.t.length; ++i) {
                    bars.push({
                      time: data.t[i] * 1000,
                      low: data.l[i],
                      high: data.h[i],
                      open: data.o[i],
                      close: data.c[i],
                      volume: data.v[i]
                    });
                  }
                }
                onHistoryCallback(bars, { noData: data.s === 'no_data' });
              })
              .catch(e => _onErrorCallback(e));
          }

          subscribeBars(symbolInfo: any, resolution: string, onRealtimeCallback: any, subscriberUID: string) {}
          unsubscribeBars(subscriberUID: string) {}
        }

        const widgetOptions = {
          symbol: pair,
          datafeed: new CustomDatafeed(),
          interval: interval as any,
          container: containerRef.current,
          library_path: 'https://trading-terminal.tradingview-widget.com/charting_library/',
          locale: 'en',
          disabled_features: ['use_localstorage_for_settings', 'header_symbol_search', 'symbol_search_hot_key'],
          enabled_features: ['study_templates'],
          charts_storage_url: 'https://saveload.tradingview.com',
          charts_storage_api_version: '1.1',
          client_id: 'tradingview.com',
          user_id: 'public_user_id',
          fullscreen: false,
          autosize: true,
          theme: theme === 'dark' ? 'Dark' : 'Light',
          custom_themes: {
            dark: {
              "color1": ["#fbefea", "#f7dfd5", "#f3cfc0", "#efbfaa", "#ebaf95", "#e89f80", "#e48f6b", "#e07f56", "#dc6f41", "#d85f2b", "#d03f01", "#bf3a01", "#ad3501", "#9c2f01", "#8b2a01", "#792501", "#682001", "#571a00", "#451500", "#341000"],
              "color2": ["#f8eeee", "#f1dede", "#eacdcd", "#e2bcbc", "#dbacac", "#d49b9b", "#cd8a8a", "#c67a7a", "#bf6969", "#b75858", "#a93737", "#9b3232", "#8d2e2e", "#7f2929", "#712525", "#632020", "#551c1c", "#461717", "#381212", "#2a0e0e"],
              "color3": ["#fff0f0", "#ffe1e1", "#ffd3d3", "#ffc4c4", "#ffb5b5", "#ffa6a6", "#ff9797", "#ff8888", "#ff7a7a", "#ff6b6b", "#ff4d4d", "#ea4747", "#d54040", "#bf3a3a", "#aa3333", "#952d2d", "#802727", "#6a2020", "#551a1a", "#401313"],
              "color4": ["#f2fffb", "#e6fff7", "#d9fff2", "#ccffee", "#bfffea", "#b3ffe6", "#a6ffe1", "#99ffdd", "#8cffd9", "#80ffd5", "#66ffcc", "#5eeabb", "#55d5aa", "#4dbf99", "#44aa88", "#3c9577", "#338066", "#2b6a55", "#225544", "#1a4033"],
              "color5": ["#fffff0", "#ffffe0", "#feffd1", "#feffc2", "#feffb2", "#feffa3", "#fdff94", "#fdff84", "#fdff75", "#fdff66", "#fcff47", "#e7ea41", "#d2d53b", "#bdbf35", "#a8aa2f", "#939529", "#7e8024", "#696a1e", "#545518", "#3f4012"],
              "color6": ["#fff1ff", "#ffe2ff", "#ffd4ff", "#ffc5ff", "#ffb7ff", "#ffa9ff", "#ff9aff", "#ff8cff", "#ff7dff", "#ff6fff", "#ff52ff", "#ea4bea", "#d544d5", "#bf3ebf", "#aa37aa", "#953095", "#802980", "#6a226a", "#551b55", "#401540"],
              "color7": ["#eff8ff", "#dff1ff", "#cfeaff", "#bee3ff", "#aedcff", "#9ed5ff", "#8eceff", "#7ec7ff", "#6ec0ff", "#5db9ff", "#3dabff", "#389dea", "#338fd5", "#2e80bf", "#2972aa", "#246495", "#1f5680", "#19476a", "#143955", "#0f2b40"],
              "white": "#ffffff",
              "black": "#000000"
            }
          },
          overrides: theme === 'dark' ? {
            "paneProperties.background": "#0A0B0D",
            "paneProperties.vertGridProperties.color": "#1A1B1F",
            "paneProperties.horzGridProperties.color": "#1A1B1F",
            "symbolWatermarkProperties.transparency": 90,
            "scalesProperties.textColor": "#8E9299",
            "mainSeriesProperties.candleStyle.upColor": "#10b981",
            "mainSeriesProperties.candleStyle.downColor": "#f43f5e",
            "mainSeriesProperties.candleStyle.drawWick": true,
            "mainSeriesProperties.candleStyle.drawBorder": true,
            "mainSeriesProperties.candleStyle.borderColor": "#10b981",
            "mainSeriesProperties.candleStyle.borderUpColor": "#10b981",
            "mainSeriesProperties.candleStyle.borderDownColor": "#f43f5e",
            "mainSeriesProperties.candleStyle.wickUpColor": "#10b981",
            "mainSeriesProperties.candleStyle.wickDownColor": "#f43f5e",
          } : {
            "paneProperties.background": "#ffffff",
            "paneProperties.vertGridProperties.color": "#f0f3fa",
            "paneProperties.horzGridProperties.color": "#f0f3fa",
            "symbolWatermarkProperties.transparency": 90,
            "scalesProperties.textColor": "#131722",
            "mainSeriesProperties.candleStyle.upColor": "#10b981",
            "mainSeriesProperties.candleStyle.downColor": "#f43f5e",
          }
        };

        const tvWidget = new window.TradingView.widget(widgetOptions);
        widgetRef.current = tvWidget;

        tvWidget.onChartReady(() => {
          isReadyRef.current = true;
          console.log('[IDIM IKANG] TradingView Chart Ready');
          
          // Initial Indicators
          tvWidget.activeChart().createStudy('Moving Average Exponential', false, false, [20], { 'plot.color': '#3b82f6' });
          tvWidget.activeChart().createStudy('Moving Average Exponential', false, false, [50], { 'plot.color': '#8b5cf6' });
          tvWidget.activeChart().createStudy('Bollinger Bands', true, false, [25, 1]);
          
          // Event Subscriptions
          tvWidget.subscribe('study', (event: any) => {
            if (onStudyAdd) onStudyAdd(event.value);
          });

          tvWidget.activeChart().onIntervalChanged().subscribe(null, (interval: string) => {
            if (onIntervalChange) onIntervalChange(interval);
          });

          // Hide the marks from the test datafeed
          setTimeout(() => {
            tvWidget.activeChart().clearMarks();
          }, 1000);
        });
      };

      if (!script) {
        script = document.createElement('script');
        script.id = scriptId;
        script.src = 'https://trading-terminal.tradingview-widget.com/charting_library/charting_library.standalone.js';
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
        // Script persists across re-renders
      };
    }, []);

    React.useEffect(() => {
      return () => {
        if (widgetRef.current) {
          widgetRef.current.remove();
          widgetRef.current = null;
          isReadyRef.current = false;
        }
      };
    }, []);

    return (
      <div 
        id="tv_chart_container" 
        ref={containerRef} 
        className="w-full h-full"
        style={{ minHeight: '400px' }}
      />
    );
  }
);

TradingViewChart.displayName = 'TradingViewChart';

export default TradingViewChart;
