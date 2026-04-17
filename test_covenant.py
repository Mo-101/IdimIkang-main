#!/usr/bin/env python3
import sys, os
sys.path.insert(0, "/home/idona/MoStar/IdimIkang-main-1/observer_bundle")
os.chdir("/home/idona/MoStar/IdimIkang-main-1/observer_bundle")

# config.py loads .env via load_dotenv() at import time
import config
from ops_covenant import enforce_execution_doctrine, covenant_startup, infra_health

print(f"ENABLE_LIVE_TRADING: {config.ENABLE_LIVE_TRADING}")
print(f"Doctrine reason: {config._DOCTRINE_REASON}")
print(f"Infra health: {infra_health.overall_health():.0%}")
print(f"\n{infra_health.status_report()}")
