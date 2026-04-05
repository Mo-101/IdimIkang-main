#!/bin/bash
# Idim Ikang v1.3 Canonical JSON Review Bundle
# Outputs a structured JSON blob for automated auditing of Phase 4 doctrine.

# Usage: ./review_bundle_v13.sh > review_bundle_v13.json

sudo -u postgres psql -d idim_ikang -t -A -c "
WITH current_signals AS (
    SELECT *
    FROM signals
    WHERE logic_version = 'v1.3-ranked-observer'
      AND config_version = 'v1.3-ranked-observer'
),
resolved AS (
    SELECT * FROM current_signals WHERE outcome IN ('WIN','LOSS')
),
cell_stats AS (
    SELECT 
        regime || ' @ ' || ((score::int / 5) * 5)::text as cell,
        COUNT(*) AS total,
        SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
        SUM(CASE WHEN outcome='EXPIRED' THEN 1 ELSE 0 END) AS expired,
        SUM(CASE WHEN outcome IS NULL THEN 1 ELSE 0 END) AS unresolved
    FROM current_signals
    GROUP BY cell
),
anomalies AS (
    SELECT ts, level, component, event 
    FROM system_logs 
    WHERE ts >= NOW() - INTERVAL '24 hours' 
      AND level IN ('WARN','ERROR') 
    ORDER BY ts DESC 
    LIMIT 20
)
SELECT json_build_object(
    'version', 'v1.3-ranked-observer',
    'timestamp', NOW(),
    'counts', (
        SELECT json_build_object(
            'signals', (SELECT COUNT(*) FROM current_signals),
            'funding', (SELECT COUNT(*) FROM funding_rates),
            'oi', (SELECT COUNT(*) FROM open_interest),
            'ls', (SELECT COUNT(*) FROM ls_ratios)
        )
    ),
    'performance', (
        SELECT json_build_object(
            'resolved_signals', COUNT(*),
            'wins', SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END),
            'losses', SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END),
            'win_rate_pct', ROUND(100.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*),0), 2),
            'profit_factor', ROUND(3.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END),0), 4)
        ) FROM resolved
    ),
    'cell_breakdown', (
        SELECT json_object_agg(cell, row_to_json(t)) FROM (SELECT * FROM cell_stats) t
    ),
    'anomalies', (
        SELECT json_agg(row_to_json(a)) FROM (SELECT * FROM anomalies) a
    ),
    'freshness', (
        SELECT json_build_object(
            'last_signal', (SELECT MAX(ts) FROM signals),
            'last_funding', (SELECT MAX(funding_time) FROM funding_rates),
            'last_oi', (SELECT MAX(timestamp) FROM open_interest),
            'last_ls', (SELECT MAX(timestamp) FROM ls_ratios)
        )
    )
);"
