-- Signal origin check: pre-gate vs post-gate
SELECT
    pair,
    side,
    regime,
    to_char(ts, 'YYYY-MM-DD HH24:MI') AS ts,
    logic_version,
    outcome,
    score
FROM signals
ORDER BY ts DESC
LIMIT 25;

-- Gate rejection breakdown since last restart
SELECT
    event,
    details ->> 'pair' AS pair,
    details ->> 'side' AS side,
    details ->> 'btc' AS btc_regime,
    to_char(ts, 'HH24:MI:SS') AS time
FROM system_logs
WHERE event IN (
    'gate5_btc_reject','gate6_mtfa_reject',
    'gsq_reject','gvwap_reject',
    'gate2_volume_reject','gate3_atr_cap',
    'gate4_reject','scan_complete','scanner_start'
)
ORDER BY ts DESC
LIMIT 40;
