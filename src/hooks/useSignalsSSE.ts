import { useEffect, useState, useCallback } from 'react';

export interface BackendSignal {
  signal_id: string;
  pair: string;
  ts: string;
  side: 'LONG' | 'SHORT';
  entry: number;
  stop_loss: number;
  take_profit: number;
  score: number;
  regime: string;
  reason_trace: any;
  outcome?: string;
  r_multiple?: number;
  signal_family?: string;
  market_regime?: string;
  btc_regime?: string;
  signal_hour_utc?: number;
  setup_score?: number;
  execution_score?: number;
  execution_source?: string;
  policy_version?: string;
  fill_price?: number;
  created_at?: string;
  updated_at?: string;
}

export function useSignalsSSE() {
  const [signals, setSignals] = useState<BackendSignal[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchInitialSignals = useCallback(async () => {
    try {
      const response = await fetch('/api/signals');
      const data = await response.json();
      if (data.signals) {
        setSignals(data.signals);
      }
    } catch (err) {
      console.error('Failed to fetch initial signals:', err);
    }
  }, []);

  useEffect(() => {
    fetchInitialSignals();

    const eventSource = new EventSource('/api/stream');

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
      console.log('SSE connection opened');
    };

    eventSource.addEventListener('new_signal', (event: MessageEvent) => {
      try {
        const newSignal: BackendSignal = JSON.parse(event.data);
        setSignals(prev => {
          // Avoid duplicates
          if (prev.some(s => s.signal_id === newSignal.signal_id)) {
            return prev;
          }
          return [newSignal, ...prev].slice(0, 100);
        });
      } catch (err) {
        console.error('Failed to parse signal from SSE:', err);
      }
    });

    eventSource.onerror = (err) => {
      console.error('SSE error:', err);
      setIsConnected(false);
      setError('Connection lost – reconnecting...');
      // Browser EventSource handles reconnection automatically
    };

    return () => {
      eventSource.close();
    };
  }, [fetchInitialSignals]);

  return { signals, isConnected, error };
}
