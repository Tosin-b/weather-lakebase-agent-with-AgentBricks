# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Weather Alerts Sync - Demo
# MAGIC %md
# MAGIC # Weather Alerts Collection System
# MAGIC
# MAGIC This notebook demonstrates how to:
# MAGIC 1. Fetch active weather alerts from the National Weather Service API for all US states
# MAGIC 2. Normalize the data into a consistent schema
# MAGIC 3. Store it in the `weather_information` table in Lakebase (Postgres)
# MAGIC
# MAGIC ## Architecture
# MAGIC
# MAGIC * **`weather_alerts_client.py`** - Client that fetches alerts from NWS API (modeled after `massive_client.py`)
# MAGIC * **`lakebase.py`** - Connection helper for Lakebase (Databricks-managed Postgres)
# MAGIC * **`sync_weather_alerts.py`** - Main sync script that orchestrates the data pipeline
# MAGIC
# MAGIC ## Data Schema
# MAGIC
# MAGIC The `weather_information` table has the following columns:
# MAGIC * `id` - Stable dedup key (NWS alert ID)
# MAGIC * `location` - City/state or area description
# MAGIC * `source_type` - "alert" (or "forecast" for future use)
# MAGIC * `headline` - Alert headline
# MAGIC * `event` - Event type (e.g., "Flash Flood Warning", "Winter Storm Watch")
# MAGIC * `narrative_text` - Full description and instructions
# MAGIC * `issued_at` - When the alert was issued
# MAGIC * `effective_at` - When the alert becomes effective
# MAGIC * `expires_at` - When the alert expires
# MAGIC * `payload` - Raw JSON for provenance
# MAGIC * `synced_at` - Timestamp when we fetched it

# COMMAND ----------

# DBTITLE 1,Run Weather Alerts Sync
# Run the sync script to fetch and store weather alerts
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

from sync_weather_alerts import main

# This will:
# 1. Create the dataexpert_student database if needed
# 2. Create the weather_information table if needed
# 3. Fetch alerts for all 50 US states + territories
# 4. Store them in Lakebase with deduplication

main()

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# MAGIC %pip install psycopg2-binary requests databricks-sdk --quiet

# COMMAND ----------

# DBTITLE 1,Query Weather Alerts
# Query the weather alerts from Lakebase
import lakebase

# Get total count of alerts
result = lakebase.run_query(
    "SELECT COUNT(*) as total FROM weather_information"
)
print(f"Total alerts in database: {result[0]['total']}")

# Get count by event type
result = lakebase.run_query(
    """
    SELECT event, COUNT(*) as count
    FROM weather_information
    GROUP BY event
    ORDER BY count DESC
    LIMIT 10
    """
)
print("\nTop 10 event types:")
for row in result:
    print(f"  {row['event']}: {row['count']}")

# COMMAND ----------

# DBTITLE 1,Sample Weather Alerts
# View sample weather alerts
import lakebase
import json

result = lakebase.run_query(
    """
    SELECT id, location, event, headline, issued_at, expires_at
    FROM weather_information
    ORDER BY issued_at DESC
    LIMIT 5
    """
)

print("Recent Weather Alerts:")
print("=" * 80)
for alert in result:
    print(f"\nEvent: {alert['event']}")
    print(f"Location: {alert['location']}")
    print(f"Headline: {alert['headline']}")
    print(f"Issued: {alert['issued_at']}")
    print(f"Expires: {alert['expires_at']}")
    print("-" * 80)

# COMMAND ----------

# DBTITLE 1,Alerts by State
# Analyze alerts by state
import lakebase
import re

result = lakebase.run_query(
    """
    SELECT location, COUNT(*) as alert_count
    FROM weather_information
    GROUP BY location
    ORDER BY alert_count DESC
    LIMIT 20
    """
)

print("Top 20 Locations with Most Active Alerts:")
print("=" * 60)
for row in result:
    print(f"{row['location']}: {row['alert_count']} alerts")

# COMMAND ----------

# DBTITLE 1,Full Alert Details
# View full details of a specific alert including narrative text
import lakebase

result = lakebase.run_query(
    """
    SELECT id, location, event, headline, narrative_text, 
           issued_at, effective_at, expires_at
    FROM weather_information
    WHERE narrative_text IS NOT NULL
    ORDER BY issued_at DESC
    LIMIT 1
    """
)

if result:
    alert = result[0]
    print("DETAILED WEATHER ALERT")
    print("=" * 80)
    print(f"ID: {alert['id']}")
    print(f"Event: {alert['event']}")
    print(f"Location: {alert['location']}")
    print(f"Headline: {alert['headline']}")
    print(f"\nIssued: {alert['issued_at']}")
    print(f"Effective: {alert['effective_at']}")
    print(f"Expires: {alert['expires_at']}")
    print(f"\nNARRATIVE:")
    print(alert['narrative_text'])
else:
    print("No alerts with narrative text found")

# COMMAND ----------

# DBTITLE 1,Test Import Weather Client
# Quick test to verify imports work
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

from weather_alerts_client import WeatherAlertsClient, US_STATES

print("✓ WeatherAlertsClient imported successfully!")
print(f"✓ Will fetch alerts from {len(US_STATES)} states/territories")

# COMMAND ----------

# DBTITLE 1,Test Fetch Alerts for Alaska
# Test fetching alerts for a single state (Alaska)
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

from weather_alerts_client import WeatherAlertsClient

client = WeatherAlertsClient()
print("Fetching alerts for Alaska...")

raw_data = client.get_alerts_for_state("AK")
features = raw_data.get("features", [])

print(f"\n✓ Found {len(features)} active alerts in Alaska")

if features:
    # Show first alert
    alert = features[0]
    props = alert.get("properties", {})
    print(f"\nFirst Alert:")
    print(f"  Event: {props.get('event')}")
    print(f"  Location: {props.get('areaDesc')}")
    print(f"  Headline: {props.get('headline')}")
else:
    print("\nNo active alerts in Alaska at this time")

# COMMAND ----------

# DBTITLE 1,Test Normalization for Sample States
# Test normalization on a small sample of states
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

from weather_alerts_client import WeatherAlertsClient
import json

client = WeatherAlertsClient()

# Test with just 3 states to keep it fast
test_states = ["AK", "CA", "TX"]
all_alerts = []

for state in test_states:
    print(f"Fetching alerts for {state}...")
    try:
        raw_data = client.get_alerts_for_state(state)
        features = raw_data.get("features", [])
        
        for feature in features:
            normalized = client._normalize_alert(feature, state)
            if normalized:
                all_alerts.append(normalized)
                
        print(f"  ✓ Found {len(features)} alerts")
    except Exception as e:
        print(f"  ✗ Error: {e}")

print(f"\n✓ Total normalized alerts: {len(all_alerts)}")

# Show first normalized alert
if all_alerts:
    print("\nFirst Normalized Alert:")
    alert = all_alerts[0]
    for key, value in alert.items():
        if key == 'payload':
            print(f"  {key}: <JSON data {len(value)} chars>")
        elif key == 'narrative_text' and value and len(value) > 100:
            print(f"  {key}: {value[:100]}...")
        else:
            print(f"  {key}: {value}")

# COMMAND ----------

# DBTITLE 1,Test Lakebase Connection
# Test Lakebase connection with credentials from 'database' scope
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

print("Step 1: Testing imports...")
try:
    import base64
    from databricks.sdk import WorkspaceClient
    print("  ✓ Imported databricks.sdk")
except Exception as e:
    print(f"  ✗ Failed to import databricks.sdk: {e}")
    raise

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("  ✓ Imported psycopg2")
except Exception as e:
    print(f"  ✗ Failed to import psycopg2: {e}")
    raise

print("\nStep 2: Fetching Lakebase URL from secrets...")
try:
    w = WorkspaceClient()
    secret = w.secrets.get_secret(scope="database", key="lakebase-url")
    url = base64.b64decode(secret.value).decode("utf-8")
    # Mask password for display
    masked_url = url.split('@')[0].split(':')[0:2]
    print(f"  ✓ Retrieved secret from scope='database', key='lakebase-url'")
    print(f"  ✓ URL format: {masked_url[0]}://***@...")
except Exception as e:
    print(f"  ✗ Failed to get secret: {e}")
    print("\nMake sure you have:")
    print("  1. Created a Lakebase instance with native password auth")
    print("  2. Stored the connection URL: w.secrets.put_secret(scope='database', key='lakebase-url', string_value=<base64_encoded_url>)")
    raise

print("\nStep 3: Testing database connection...")
try:
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    print("  ✓ Connected to Lakebase!")
    
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        result = cur.fetchone()
        version = result['version'][:60]
        print(f"  ✓ Postgres version: {version}...")
        
    conn.close()
    print("\n✅ SUCCESS! Lakebase connection works perfectly!")
    print("Ready to sync weather alerts to the database.")
    
except Exception as e:
    print(f"  ✗ Connection failed: {e}")
    print("\nPlease verify:")
    print("  1. Lakebase instance is running")
    print("  2. Connection URL is correct")
    print("  3. Network access is allowed")
    raise

# COMMAND ----------

# DBTITLE 1,✅ RUN SYNC - Works on Serverless!
# ✅ SERVERLESS-SAFE SYNC - Uses dbutils instead of WorkspaceClient
import os
import sys

# Get LAKEBASE_URL from secrets (stored in scope='database', key='lakebase-url')
lakebase_url = dbutils.secrets.get(scope="database", key="lakebase-url")
os.environ["LAKEBASE_URL"] = lakebase_url

print("✅ Fetched credentials from secrets")

# Run the standalone sync (no Databricks SDK)
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 2')
from run_sync_standalone import main

print("\n" + "="*60)
print("Starting Weather Alerts Sync...")
print("="*60 + "\n")

main()