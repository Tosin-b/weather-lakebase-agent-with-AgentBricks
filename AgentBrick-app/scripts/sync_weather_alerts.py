"""
Sync weather alerts from the National Weather Service API into Lakebase.

This script:
1. Fetches active weather alerts for all US states
2. Normalizes the data into a consistent schema
3. Stores it in the weather_information table in Lakebase
4. Uses ON CONFLICT (id) DO UPDATE for deduplication

Run this script periodically (e.g., every hour) to keep weather alerts up to date.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import lakebase
from weather_alerts_client import WeatherAlertsClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLE_NAME = "weather_information"
DATABASE_NAME = "dataexpert_student"


def ensure_database():
    """Create the dataexpert_student database if it doesn't exist."""
    logger.info(f"Ensuring database {DATABASE_NAME} exists...")
    # Connect to default database (likely 'postgres' or 'databricks_postgres')
    with lakebase.get_connection() as conn:
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


def ensure_table():
    """Create the weather_information table if it doesn't exist."""
    logger.info(f"Ensuring table {TABLE_NAME} exists...")
    
    # Connect to dataexpert_student database
    with lakebase.get_connection(database=DATABASE_NAME) as conn:
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
    # Connect to dataexpert_student database
    with lakebase.get_connection(database=DATABASE_NAME) as conn:
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


def main():
    """Main entry point for the sync script."""
    try:
        # Step 1: Ensure database exists
        ensure_database()
        
        # Step 2: Ensure table exists
        ensure_table()
        
        # Step 3: Sync alerts
        count = sync_alerts()
        
        logger.info(f"Sync complete! Total alerts: {count}")
        
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise


if __name__ == "__main__":
    main()