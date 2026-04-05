#!/bin/bash
# Idim Ikang v1.3 Canonical Review Bundle
# Aggregates PM2 status and Postgres analytics for doctrine-aligned reviews.

echo "=========================================================================="
echo "IDIM IKANG v1.3 CANONICAL REVIEW BUNDLE"
echo "Timestamp: $(date -u)"
echo "=========================================================================="

echo -e "\n[1] PM2 SERVICE HEALTH"
echo "--------------------------------------------------------------------------"
pm2 status

echo -e "\n[2] DATABASE ROW COUNTS"
echo "--------------------------------------------------------------------------"
sudo -u postgres psql -d idim_ikang -c "SELECT 
    (SELECT COUNT(*) FROM signals) as signals, 
    (SELECT COUNT(*) FROM funding_rates) as funding, 
    (SELECT COUNT(*) FROM open_interest) as oi, 
    (SELECT COUNT(*) FROM ls_ratios) as ls;"

echo -e "\n[3] OUTCOME DISTRIBUTION"
echo "--------------------------------------------------------------------------"
sudo -u postgres psql -d idim_ikang -c "SELECT outcome, COUNT(*) FROM signals GROUP BY outcome ORDER BY outcome;"

echo -e "\n[4] GLOBAL PERFORMANCE (WR / PF)"
echo "--------------------------------------------------------------------------"
sudo -u postgres psql -d idim_ikang -c "SELECT 
    COUNT(*) AS resolved_signals, 
    SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) AS wins, 
    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses, 
    ROUND(100.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome IN ('WIN','LOSS') THEN 1 ELSE 0 END),0), 4) AS win_rate_pct, 
    ROUND(3.0 * SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END)::numeric / NULLIF(SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END),0), 4) AS profit_factor 
FROM signals WHERE outcome IN ('WIN','LOSS');"

echo -e "\n[5] SIGNAL DENSITY BY PAIR"
echo "--------------------------------------------------------------------------"
sudo -u postgres psql -d idim_ikang -c "SELECT pair, COUNT(*) FROM signals GROUP BY pair ORDER BY COUNT(*) DESC, pair LIMIT 15;"

echo -e "\n[6] SIGNAL DENSITY BY WOLFRAM CELL"
echo "--------------------------------------------------------------------------"
sudo -u postgres psql -d idim_ikang -c "SELECT regime, ROUND(score)::int AS score_bucket, COUNT(*) FROM signals GROUP BY regime, ROUND(score)::int ORDER BY COUNT(*) DESC, regime, score_bucket;"

echo -e "\n[7] RECENT SYSTEM ANOMALIES (LAST 30)"
echo "--------------------------------------------------------------------------"
sudo -u postgres psql -d idim_ikang -c "SELECT ts, level, component, event FROM system_logs ORDER BY ts DESC LIMIT 30;"

echo "=========================================================================="
echo "END OF BUNDLE"
echo "=========================================================================="
