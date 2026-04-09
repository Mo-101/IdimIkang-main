import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

def check_signals():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    print("\n--- CTSI/ONT HISTORY ---")
    cur.execute("""
        SELECT pair, side, regime, score, to_char(ts, 'YYYY-MM-DD HH24:MI:SS') as ts, logic_version 
        FROM signals 
        WHERE pair IN ('CTSIUSDT','ONTUSDT') 
        ORDER BY ts DESC 
        LIMIT 10;
    """)
    for row in cur.fetchall():
        print(row)
        
    print("\n--- RECENT GATE REVERSALS / REJECTIONS ---")
    cur.execute("""
        SELECT event, details->>'pair' as pair, details->>'reason' as reason, to_char(ts, 'HH24:MI:SS') as time
        FROM system_logs
        WHERE event LIKE 'gate%' OR event LIKE 'g%'
        ORDER BY ts DESC
        LIMIT 20;
    """)
    for row in cur.fetchall():
        print(row)

    print("\n--- RECENT SCAN STATUS ---")
    cur.execute("""
        SELECT
            event,
            details->>'duration' as dur,
            details->>'pairs_processed' as pairs_processed,
            details->>'setups_viable_pre_phase2' as viable_pre_phase2,
            details->>'setups_blocked_phase2' as blocked_phase2,
            details->>'signals_emitted' as signals_emitted,
            to_char(ts, 'HH24:MI:SS') as time
        FROM system_logs
        WHERE event IN ('scan_start', 'scan_complete')
        ORDER BY ts DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        print(row)

    conn.close()

if __name__ == "__main__":
    check_signals()
