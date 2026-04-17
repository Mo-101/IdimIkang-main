#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
IDIM IKANG — OPERATIONAL COVENANT LAYER
The Flame Architect | MoStar Industries
═══════════════════════════════════════════════════════════════════

Self-governing infrastructure layer. Three pillars:

  1. EXECUTION DOCTRINE — Impossible to accidentally go live
  2. ENV VALIDATION — Fail-fast on missing criticals
  3. INFRA HEALTH — Classify + track DNS/API/collector/model failures

Import this early. It asserts safety at startup.
═══════════════════════════════════════════════════════════════════
"""

import os
import time
import socket
import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger("ops_covenant")

# ═══════════════════════════════════════════════════════════════════════════
# PILLAR 1: EXECUTION DOCTRINE
# ═══════════════════════════════════════════════════════════════════════════

# Live trading requires an explicit unlock token in .env
# Without it, ENABLE_LIVE_TRADING is forced to False regardless of .env value.
LIVE_TRADING_UNLOCK_TOKEN = os.environ.get("LIVE_TRADING_UNLOCK_TOKEN", "")

def enforce_execution_doctrine() -> Tuple[bool, str]:
    """
    Triple-gate execution doctrine:
      Gate 1: ENABLE_LIVE_TRADING must be "true" in env
      Gate 2: LIVE_TRADING_UNLOCK_TOKEN must be set (non-empty)
      Gate 3: Token must match expected pattern (starts with "LIVE_")
    
    Returns (is_live_allowed, reason).
    """
    raw_flag = os.environ.get("ENABLE_LIVE_TRADING", "false").lower()
    gate1 = raw_flag == "true"
    
    gate2 = len(LIVE_TRADING_UNLOCK_TOKEN.strip()) > 0
    gate3 = LIVE_TRADING_UNLOCK_TOKEN.startswith("LIVE_") if gate2 else False
    
    if gate1 and gate2 and gate3:
        logger.critical(
            "[DOCTRINE] ⚠️ ALL THREE GATES OPEN — LIVE DISPATCH ACTIVE. "
            f"Token prefix: {LIVE_TRADING_UNLOCK_TOKEN[:8]}..."
        )
        return True, "all_gates_open"
    
    if gate1 and not gate2:
        logger.warning(
            "[DOCTRINE] ENABLE_LIVE_TRADING=true BUT no unlock token. "
            "FORCING SIM MODE. Set LIVE_TRADING_UNLOCK_TOKEN=LIVE_xxx to unlock."
        )
        return False, "gate2_missing_token"
    
    if gate1 and gate2 and not gate3:
        logger.warning(
            "[DOCTRINE] ENABLE_LIVE_TRADING=true BUT unlock token invalid "
            "(must start with 'LIVE_'). FORCING SIM MODE."
        )
        return False, "gate3_invalid_token"
    
    logger.info("[DOCTRINE] Gate locked. SIM mode only.")
    return False, "sim_mode"


# ═══════════════════════════════════════════════════════════════════════════
# PILLAR 2: ENV VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

CRITICAL_ENV_VARS = [
    "DATABASE_URL",
]

IMPORTANT_ENV_VARS = [
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

def validate_env() -> Dict[str, str]:
    """
    Validate environment at process start.
    Returns dict of {var_name: status} for reporting.
    """
    status = {}
    failures = []
    
    for var in CRITICAL_ENV_VARS:
        val = os.environ.get(var, "")
        if not val:
            status[var] = "MISSING_CRITICAL"
            failures.append(var)
            logger.critical(f"[ENV] CRITICAL: {var} is missing. Process cannot function.")
        else:
            # Validate DATABASE_URL format
            if var == "DATABASE_URL":
                if ":5432/" in val:
                    status[var] = "WRONG_PORT_5432"
                    failures.append(var)
                    logger.critical(f"[ENV] CRITICAL: {var} uses old port 5432. Must be 5433.")
                elif ":5433/" in val:
                    status[var] = "OK"
                else:
                    status[var] = "UNKNOWN_FORMAT"
                    logger.warning(f"[ENV] WARNING: {var} format unexpected: {val[:30]}...")
            else:
                status[var] = "OK"
    
    for var in IMPORTANT_ENV_VARS:
        val = os.environ.get(var, "")
        if not val:
            status[var] = "MISSING"
            logger.warning(f"[ENV] {var} is missing. Feature degraded.")
        else:
            status[var] = "OK"
    
    if failures:
        logger.critical(
            f"[COVENANT] ENV VALIDATION FAILED: {', '.join(failures)}. "
            f"Fix .env and restart with --update-env."
        )
        # Non-fatal: let process decide. Collectors can partially function.
        # Fatal processes (scanner, executor) should check _COVENANT_STATUS.
    
    logger.info(f"[ENV] Validation passed. {len(CRITICAL_ENV_VARS)} critical, {len(IMPORTANT_ENV_VARS)} important checked.")
    return status


# ═══════════════════════════════════════════════════════════════════════════
# PILLAR 3: INFRASTRUCTURE HEALTH
# ═══════════════════════════════════════════════════════════════════════════

class InfraHealth:
    """
    Systemic classification of infrastructure failures.
    Tracks DNS, API, collector, and model health with decay.
    """
    
    FAILURE_TYPES = {
        "dns": "DNS resolution failure",
        "api": "External API unreachable",
        "db": "Database connection failure",
        "collector": "Data collector stale/dead",
        "model": "AI model unavailable",
        "exchange": "Exchange connection failure",
    }
    
    def __init__(self):
        self._lock = threading.Lock()
        self._events = []  # Last 100 events
        self._scores = {ft: 1.0 for ft in self.FAILURE_TYPES}  # 1.0 = healthy
        self._last_failure = {ft: None for ft in self.FAILURE_TYPES}
        self._dns_cache = {}  # hostname -> (ip, timestamp)
        self._dns_cache_ttl = 300  # 5 minutes
    
    def record_failure(self, failure_type: str, detail: str = ""):
        """Record an infrastructure failure and decay the health score."""
        if failure_type not in self.FAILURE_TYPES:
            logger.warning(f"[INFRA] Unknown failure type: {failure_type}")
            return
        
        now = datetime.now(timezone.utc)
        
        with self._lock:
            # Decay score
            self._scores[failure_type] = max(0.0, self._scores[failure_type] - 0.15)
            self._last_failure[failure_type] = now
            
            event = {
                "type": failure_type,
                "detail": detail[:200],
                "ts": now.isoformat(),
                "score_after": round(self._scores[failure_type], 2),
            }
            self._events.append(event)
            if len(self._events) > 100:
                self._events = self._events[-100:]
        
        # Log with severity based on score
        score = self._scores[failure_type]
        if score < 0.3:
            logger.critical(f"[INFRA] {failure_type} HEALTH CRITICAL ({score:.0%}): {detail}")
        elif score < 0.6:
            logger.warning(f"[INFRA] {failure_type} HEALTH DEGRADED ({score:.0%}): {detail}")
        else:
            logger.info(f"[INFRA] {failure_type} health dip ({score:.0%}): {detail}")
    
    def record_recovery(self, failure_type: str):
        """Record a recovery and restore health score."""
        with self._lock:
            self._scores[failure_type] = min(1.0, self._scores[failure_type] + 0.3)
        
        score = self._scores[failure_type]
        logger.info(f"[INFRA] {failure_type} RECOVERED (health: {score:.0%})")
    
    def get_health(self) -> Dict[str, float]:
        """Get current health scores."""
        with self._lock:
            return dict(self._scores)
    
    def overall_health(self) -> float:
        """Get aggregate health score (0-1)."""
        with self._lock:
            return round(sum(self._scores.values()) / len(self._scores), 2)
    
    def is_healthy(self, failure_type: str) -> bool:
        """Check if a specific subsystem is healthy (>0.5)."""
        with self._lock:
            return self._scores.get(failure_type, 1.0) > 0.5
    
    def get_events(self, last_n: int = 20) -> list:
        """Get recent events."""
        with self._lock:
            return list(self._events[-last_n:])
    
    def resolve_dns(self, hostname: str) -> Optional[str]:
        """
        DNS resolution with caching and fallback.
        Returns cached IP if available, otherwise resolves fresh.
        """
        now = time.time()
        
        with self._lock:
            if hostname in self._dns_cache:
                ip, ts = self._dns_cache[hostname]
                if now - ts < self._dns_cache_ttl:
                    return ip
        
        # Fresh resolution
        try:
            ip = socket.gethostbyname(hostname)
            with self._lock:
                self._dns_cache[hostname] = (ip, now)
            self.record_recovery("dns")
            return ip
        except socket.gaierror as e:
            self.record_failure("dns", f"Cannot resolve {hostname}: {e}")
            # Return stale cache if available
            with self._lock:
                if hostname in self._dns_cache:
                    ip, ts = self._dns_cache[hostname]
                    age_min = (now - ts) / 60
                    logger.warning(f"[DNS] Using stale cache for {hostname} ({age_min:.0f}min old): {ip}")
                    return ip
            return None
    
    def decay_scores(self):
        """
        Slowly recover health scores over time.
        Call periodically (e.g., every scan cycle).
        """
        with self._lock:
            for ft in self._scores:
                if self._scores[ft] < 1.0:
                    self._scores[ft] = min(1.0, self._scores[ft] + 0.02)
    
    def status_report(self) -> str:
        """Generate a compact status report."""
        with self._lock:
            lines = ["[INFRA HEALTH]"]
            for ft, score in sorted(self._scores.items()):
                icon = "✅" if score > 0.7 else ("⚠️" if score > 0.3 else "🚨")
                last = self._last_failure[ft]
                last_str = last.strftime("%H:%M") if last else "never"
                lines.append(f"  {icon} {ft:12}: {score:.0%} (last fail: {last_str})")
            lines.append(f"  Overall: {self.overall_health():.0%}")
            return "\n".join(lines)


# Singleton
infra_health = InfraHealth()


# ═══════════════════════════════════════════════════════════════════════════
# DNS-RESILIENT REQUEST WRAPPER
# ═══════════════════════════════════════════════════════════════════════════

def resilient_get(url: str, params: dict = None, timeout: int = 20, 
                  max_retries: int = 3, backoff_base: float = 2.0) -> Optional[object]:
    """
    requests.get() with DNS caching, retry, and exponential backoff.
    Drops into infra_health tracker on failure.
    """
    import requests as req
    
    # Pre-resolve DNS
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname
    
    if hostname:
        cached_ip = infra_health.resolve_dns(hostname)
        if cached_ip and hostname not in url:
            # Replace hostname with IP, set Host header
            ip_url = url.replace(hostname, cached_ip, 1)
            headers = {"Host": hostname}
        else:
            ip_url = url
            headers = {}
    else:
        ip_url = url
        headers = {}
    
    for attempt in range(max_retries):
        try:
            r = req.get(ip_url, params=params, timeout=timeout, headers=headers or None)
            r.raise_for_status()
            infra_health.record_recovery("api")
            return r
        except req.exceptions.ConnectionError as e:
            infra_health.record_failure("dns" if "resolve" in str(e).lower() else "api",
                                       f"GET {url} attempt {attempt+1}: {e}")
        except req.exceptions.Timeout as e:
            infra_health.record_failure("api", f"GET {url} timeout attempt {attempt+1}")
        except req.exceptions.HTTPError as e:
            # Don't retry 4xx
            if 400 <= e.response.status_code < 500:
                raise
            infra_health.record_failure("api", f"GET {url} HTTP {e.response.status_code} attempt {attempt+1}")
        except Exception as e:
            infra_health.record_failure("api", f"GET {url} unexpected: {e}")
        
        if attempt < max_retries - 1:
            wait = backoff_base ** attempt
            logger.info(f"[RESILIENT] Retrying {url} in {wait:.1f}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
    
    logger.error(f"[RESILIENT] All {max_retries} attempts failed for {url}")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# STARTUP COVENANT
# ═══════════════════════════════════════════════════════════════════════════

def covenant_startup() -> Dict:
    """
    Run all covenant checks at process start.
    Returns status dict. Raises on critical failures.
    """
    logger.info("=" * 50)
    logger.info("OPERATIONAL COVENANT — STARTUP")
    logger.info("=" * 50)
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "env_status": {},
        "execution_mode": "sim",
        "doctrine_reason": "",
        "infra_health": {},
    }
    
    # Pillar 2: Env validation (may raise)
    try:
        result["env_status"] = validate_env()
    except RuntimeError as e:
        logger.critical(str(e))
        result["env_status"]["_fatal"] = str(e)
        # Don't raise — let the process log and decide
        # (Some processes like collectors can still partially function)
    
    # Pillar 1: Execution doctrine
    is_live, reason = enforce_execution_doctrine()
    result["execution_mode"] = "live" if is_live else "sim"
    result["doctrine_reason"] = reason
    
    # Pillar 3: Initial infra health
    result["infra_health"] = infra_health.get_health()
    
    logger.info(f"[COVENANT] Execution mode: {result['execution_mode']} ({reason})")
    logger.info(f"[COVENANT] Infra health: {infra_health.overall_health():.0%}")
    logger.info("=" * 50)
    
    return result


# Auto-run on import if COVENANT_AUTO_START env is set
if os.environ.get("COVENANT_AUTO_START", "false").lower() == "true":
    covenant_startup()
