import os
import sys
from dotenv import load_dotenv

# Add bundle to path
sys.path.append(os.getcwd())

load_dotenv()

try:
    import scanner
    # Override DATABASE_URL if not in ENV to avoid top-level crash
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "postgresql://localhost/dummy"
    
    regime = scanner.get_btc_macro_regime()
    print(f"BTC_REGIME_CURRENT: {regime}")
except Exception as e:
    print(f"PROBE_FAILED: {e}")
