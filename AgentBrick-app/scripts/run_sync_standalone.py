#!/usr/bin/env python3
"""
Standalone Weather Alerts Sync Script

This script fetches weather alerts and stores them in Lakebase WITHOUT using
the Databricks SDK (which crashes on Serverless compute).

Usage:
    1. Set LAKEBASE_URL environment variable:
       export LAKEBASE_URL="postgresql://user:pass@host:5432/database?sslmode=require"
    
    2. Run the script:
       python run_sync_standalone.py

Or run directly with Databricks Jobs by passing the LAKEBASE_URL in job parameters.
"""

import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from weather_alerts_client import WeatherAlertsClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TABLE_NAME = "weather_information"
DATABASE_NAME = "dataexpert_student"


@contextmanager
def get_connection(database: str | None = None):
    """
    Get a Lakebase connection using LAKEBASE_URL from environment.
    
    Args:
        database: Optional database name to override the default
    """
    url = os.environ.get("LAKEBASE_URL")
    if not url:
        raise ValueError(
            "LAKEBASE_URL environment variable not set.\n"
            "Set it to your Lakebase connection URL:\n"
            "export LAKEBASE_URL='postgresql://user:pass@host:5432/db?sslmode=require'"
        )
    
    # Override database if requested
    if database:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        new_path = f"/{database}"
        url = urlunparse(parsed._replace(path=new_path))
    
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def ensure_database():
    """Create the dataexpert_student database if it doesn't exist."""
    logger.info(f"Ensuring database {DATABASE_NAME} exists...")
    
    try:
        with get_connection() as conn:
            conn.set_session(autocommit=True)
            with conn.cursor() as cur:
                # Check if database exists
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (DATABASE_NAME,)
                )
                if not cur.fetchone():
                    logger.info(f"Creating database {DATABASE_NAME}...")
                    cur.execute(f"CREATE DATABASE {DATABASE_NAME}")
                else:
                    logger.info(f"Database {DATABASE_NAME} already exists")
    except Exception as e:
        logger.error(f"Failed to ensure database: {e}")
        raise


def ensure_table():
    """Create the weather_information table if it doesn't exist."""
    logger.info(f"Ensuring table {TABLE_NAME} exists...")
    
    try:
        with get_connection(database=DATABASE_NAME) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                        id TEXT PRIMARY KEY,
                        location TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        headline TEXT,
                        event TEXT NOT NULL,
                        narrative_text TEXT,
                        issued_at TIMESTAMPTZ,
                        effective_at TIMESTAMPTZ,
                        expires_at TIMESTAMPTZ,
                        payload JSONB NOT NULL,
                        synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.commit()
                logger.info(f"Table {TABLE_NAME} is ready")
    except Exception as e:
        logger.error(f"Failed to ensure table: {e}")
        raise


def sync_alerts() -> int:
    """
    Fetch weather alerts from NWS API and sync them to Lakebase.
    
    Returns:
        Number of alerts synced
    """
    logger.info("Starting weather alerts sync...")
    
    # Fetch alerts from NWS API
    client = WeatherAlertsClient()
    alerts = client.get_all_alerts()
    
    logger.info(f"Fetched {len(alerts)} weather alerts")
    
    if not alerts:
        logger.info("No alerts to sync")
        return 0
    
    # Sync to Lakebase
    count = 0
    try:
        with get_connection(database=DATABASE_NAME) as conn:
            with conn.cursor() as cur:
                for alert in alerts:
                    try:
                        cur.execute(
                            f"""
                            INSERT INTO {TABLE_NAME} (
                                id, location, source_type, headline, event,
                                narrative_text, issued_at, effective_at, expires_at,
                                payload, synced_at
                            )
                            VALUES (
                                %(id)s, %(location)s, %(source_type)s, %(headline)s, %(event)s,
                                %(narrative_text)s, %(issued_at)s, %(effective_at)s, %(expires_at)s,
                                %(payload)s, %(synced_at)s
                            )
                            ON CONFLICT (id) DO UPDATE
                                SET location = EXCLUDED.location,
                                    source_type = EXCLUDED.source_type,
                                    headline = EXCLUDED.headline,
                                    event = EXCLUDED.event,
                                    narrative_text = EXCLUDED.narrative_text,
                                    issued_at = EXCLUDED.issued_at,
                                    effective_at = EXCLUDED.effective_at,
                                    expires_at = EXCLUDED.expires_at,
                                    payload = EXCLUDED.payload,
                                    synced_at = EXCLUDED.synced_at
                            """,
                            alert
                        )
                        count += 1
                    except Exception as e:
                        logger.error(f"Error syncing alert {alert.get('id')}: {e}")
                        continue
                
                conn.commit()
        
        logger.info(f"Successfully synced {count} alerts to {TABLE_NAME}")
        return count
    except Exception as e:
        logger.error(f"Failed to sync alerts: {e}")
        raise


def main():
    """Main entry point for the sync script."""
    try:
        logger.info("Weather Alerts Sync - Starting")
        logger.info("=" * 60)
        
        # Step 1: Ensure database exists
        ensure_database()
        
        # Step 2: Ensure table exists
        ensure_table()
        
        # Step 3: Sync alerts
        count = sync_alerts()
        
        logger.info("=" * 60)
        logger.info(f"✓ Sync complete! Total alerts: {count}")
        
    except Exception as e:
        logger.error(f"✗ Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()