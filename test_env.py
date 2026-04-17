import os, sys
sys.path.insert(0, "/home/idona/MoStar/IdimIkang-main-1/observer_bundle")
from dotenv import load_dotenv
load_dotenv("/home/idona/MoStar/IdimIkang-main-1/observer_bundle/.env")
url = os.environ.get("DATABASE_URL", "MISSING")
print(f"DATABASE_URL: {url[:60]}")
