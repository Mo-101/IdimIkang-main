#!/usr/bin/env python3
"""
Neo4j MindGraph Writer for Grid Contract Compliance
Writes Idim Ikang events to the Grid MindGraph cognitive substrate.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("neo4j_writer")

# Neo4j connection config
NEO4J_BOLT_URL = os.environ.get("NEO4J_BOLT_URL", "bolt://127.0.0.1:47687")
NEO4J_HTTP_URL = os.environ.get("NEO4J_HTTP_URL", "http://127.0.0.1:47474")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# Source identifier for all nodes
SOURCE = "idim-ikang"

_driver = None


def get_driver():
    """Get or create Neo4j driver instance"""
    global _driver
    if _driver is None:
        try:
            from neo4j import GraphDatabase
            _driver = GraphDatabase.driver(NEO4J_BOLT_URL, auth=("neo4j", NEO4J_PASSWORD))
            logger.info(f"Neo4j driver initialized: {NEO4J_BOLT_URL}")
        except ImportError:
            logger.warning("neo4j package not installed - Neo4j writing disabled")
            _driver = None
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")
            _driver = None
    return _driver


def _get_timestamp() -> str:
    """Get current ISO8601 timestamp"""
    return datetime.now(timezone.utc).isoformat()


def write_candidate(candidate_data: Dict[str, Any]) -> bool:
    """Write a training candidate to Neo4j as :Candidate node"""
    driver = get_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            query = """
            MERGE (c:Candidate {id: $id})
            SET c += $props
            """
            props = {
                "source": SOURCE,
                "timestamp": _get_timestamp(),
                **candidate_data
            }
            session.run(query, id=candidate_data.get("id"), props=props)
            logger.debug(f"Wrote candidate: {candidate_data.get('symbol')}")
            return True
    except Exception as e:
        logger.error(f"Failed to write candidate: {e}")
        return False


def write_signal(signal_data: Dict[str, Any]) -> bool:
    """Write an emitted signal to Neo4j as :Signal node"""
    driver = get_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            query = """
            MERGE (s:Signal {signal_id: $signal_id})
            SET s += $props
            """
            props = {
                "source": SOURCE,
                "timestamp": _get_timestamp(),
                **signal_data
            }
            session.run(query, signal_id=signal_data.get("signal_id"), props=props)
            logger.debug(f"Wrote signal: {signal_data.get('pair')}")
            return True
    except Exception as e:
        logger.error(f"Failed to write signal: {e}")
        return False


def write_shadow_signal(candidate_data: Dict[str, Any]) -> bool:
    """Write a would_have_passed_live candidate as :ShadowSignal node"""
    driver = get_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            query = """
            MERGE (s:ShadowSignal {id: $id})
            SET s += $props
            """
            props = {
                "source": SOURCE,
                "timestamp": _get_timestamp(),
                **candidate_data
            }
            session.run(query, id=candidate_data.get("id"), props=props)
            logger.debug(f"Wrote shadow signal: {candidate_data.get('symbol')}")
            return True
    except Exception as e:
        logger.error(f"Failed to write shadow signal: {e}")
        return False


def write_outcome(outcome_data: Dict[str, Any], signal_id: str) -> bool:
    """Write an outcome to Neo4j and link to Signal"""
    driver = get_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            query = """
            MERGE (s:Signal {signal_id: $signal_id})
            MERGE (o:Outcome {signal_id: $signal_id})
            SET o += $props
            MERGE (s)-[:HAS_OUTCOME]->(o)
            """
            props = {
                "source": SOURCE,
                "timestamp": _get_timestamp(),
                **outcome_data
            }
            session.run(query, signal_id=signal_id, props=props)
            logger.debug(f"Wrote outcome for signal: {signal_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to write outcome: {e}")
        return False


def write_service_heartbeat(service_name: str, status: str = "alive") -> bool:
    """Write a service heartbeat to Neo4j as :ServiceHeartbeat node"""
    driver = get_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            query = """
            CREATE (h:ServiceHeartbeat)
            SET h += $props
            """
            props = {
                "source": SOURCE,
                "timestamp": _get_timestamp(),
                "service_name": service_name,
                "status": status
            }
            session.run(query, props=props)
            logger.debug(f"Wrote heartbeat: {service_name}")
            return True
    except Exception as e:
        logger.error(f"Failed to write heartbeat: {e}")
        return False


def close():
    """Close Neo4j driver connection"""
    global _driver
    if _driver:
        try:
            _driver.close()
            _driver = None
            logger.info("Neo4j driver closed")
        except Exception as e:
            logger.error(f"Failed to close Neo4j driver: {e}")
