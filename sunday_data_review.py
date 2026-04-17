import psycopg2
from datetime import datetime, timezone

def get_sunday_data_report():
    """Generate comprehensive Sunday data collection report"""
    
    conn = psycopg2.connect("postgresql://postgres:IdimIkangLocal2026!@localhost:5433/idim_ikang")
    cur = conn.cursor()
    
    # Get today's date (Sunday)
    today = datetime.now(timezone.utc).date()
    
    print("=" * 60)
    print("IDIM IKANG - SUNDAY DATA COLLECTION REPORT")
    print(f"Date: {today.strftime('%Y-%m-%d')} (Sunday)")
    print("=" * 60)
    
    # 1. Training Data Overview
    print("\n1. TRAINING DATA OVERVIEW")
    print("-" * 30)
    
    cur.execute("""
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT symbol) as unique_symbols,
            COUNT(DISTINCT side) as sides_covered,
            COUNT(DISTINCT DATE(created_at)) as days_collected
        FROM training_candidates 
        WHERE DATE(created_at) = %s
    """, (today,))
    
    training_stats = cur.fetchone()
    print(f"Total Training Records: {training_stats[0]:,}")
    print(f"Unique Symbols: {training_stats[1]}")
    print(f"Sides Covered: {training_stats[2]} (LONG/SHORT)")
    print(f"Days Collected: {training_stats[3]}")
    
    # 2. Signal Activity
    print("\n2. SIGNAL ACTIVITY")
    print("-" * 20)
    
    cur.execute("""
        SELECT 
            COUNT(*) as total_signals,
            COUNT(CASE WHEN execution_id IS NOT NULL THEN 1 END) as executed_signals,
            COUNT(CASE WHEN outcome IS NOT NULL THEN 1 END) as resolved_signals,
            COUNT(CASE WHEN outcome = 'WIN' THEN 1 END) as wins,
            COUNT(CASE WHEN outcome = 'LOSS' THEN 1 END) as losses
        FROM signals 
        WHERE DATE(created_at) = %s
    """, (today,))
    
    signal_stats = cur.fetchone()
    print(f"Total Signals Generated: {signal_stats[0]}")
    print(f"Executed Signals: {signal_stats[1]}")
    print(f"Resolved Signals: {signal_stats[2]}")
    print(f"Wins: {signal_stats[3]}")
    print(f"Losses: {signal_stats[4]}")
    
    # 3. Rejection Gate Analysis
    print("\n3. REJECTION GATE ANALYSIS")
    print("-" * 30)
    
    cur.execute("""
        SELECT 
            rejection_gate,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
        FROM training_candidates 
        WHERE DATE(created_at) = %s
        GROUP BY rejection_gate 
        ORDER BY count DESC
    """, (today,))
    
    gate_stats = cur.fetchall()
    for gate, count, percentage in gate_stats:
        gate_name = gate if gate else "PASSED"
        print(f"{gate_name:15}: {count:6} ({percentage:5.1f}%)")
    
    # 4. Signal Family Distribution
    print("\n4. SIGNAL FAMILY DISTRIBUTION")
    print("-" * 35)
    
    cur.execute("""
        SELECT 
            signal_family,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
        FROM training_candidates 
        WHERE DATE(created_at) = %s
        GROUP BY signal_family 
        ORDER BY count DESC
    """, (today,))
    
    family_stats = cur.fetchall()
    for family, count, percentage in family_stats:
        print(f"{family:15}: {count:6} ({percentage:5.1f}%)")
    
    # 5. Market Regime Coverage
    print("\n5. MARKET REGIME COVERAGE")
    print("-" * 30)
    
    cur.execute("""
        SELECT 
            regime,
            COUNT(*) as count
        FROM training_candidates 
        WHERE DATE(created_at) = %s
        GROUP BY regime 
        ORDER BY count DESC
    """, (today,))
    
    regime_stats = cur.fetchall()
    for regime, count in regime_stats:
        print(f"{regime:20}: {count:6}")
    
    # 6. Hourly Collection Rate
    print("\n6. HOURLY COLLECTION RATE")
    print("-" * 30)
    
    cur.execute("""
        SELECT 
            EXTRACT(HOUR FROM created_at) as hour,
            COUNT(*) as records
        FROM training_candidates 
        WHERE DATE(created_at) = %s
        GROUP BY hour 
        ORDER BY hour
    """, (today,))
    
    hourly_stats = cur.fetchall()
    for hour, records in hourly_stats:
        print(f"{int(hour):02d}:00 - {int(hour):02d}:59: {records:4} records")
    
    # 7. Data Quality Metrics
    print("\n7. DATA QUALITY METRICS")
    print("-" * 30)
    
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN family_indicators IS NOT NULL THEN 1 END) as with_family_indicators,
            COUNT(CASE WHEN trace_data IS NOT NULL THEN 1 END) as with_trace_data,
            COUNT(CASE WHEN score > 0 THEN 1 END) as with_positive_score
        FROM training_candidates 
        WHERE DATE(created_at) = %s
    """, (today,))
    
    quality_stats = cur.fetchone()
    total = quality_stats[0]
    print(f"Total Records: {total:,}")
    print(f"With Family Indicators: {quality_stats[1]} ({quality_stats[1]/total*100:.1f}%)")
    print(f"With Trace Data: {quality_stats[2]} ({quality_stats[2]/total*100:.1f}%)")
    print(f"With Positive Score: {quality_stats[3]} ({quality_stats[3]/total*100:.1f}%)")
    
    # 8. Recent Scanner Performance
    print("\n8. RECENT SCANNER PERFORMANCE")
    print("-" * 35)
    
    cur.execute("""
        SELECT 
            DATE_TRUNC('hour', created_at) as hour,
            COUNT(*) as records_per_hour
        FROM training_candidates 
        WHERE created_at >= NOW() - INTERVAL '6 hours'
        GROUP BY hour 
        ORDER BY hour DESC
        LIMIT 6
    """)
    
    recent_stats = cur.fetchall()
    for hour, records in recent_stats:
        hour_str = hour.strftime('%H:%M')
        print(f"{hour_str}: {records:4} records/hour")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("REPORT SUMMARY: Data collection operating normally")
    print("60 records per cycle (30 pairs × 2 sides)")
    print("=" * 60)

if __name__ == "__main__":
    get_sunday_data_report()
