# Weather Alerts Collection System - Project Summary

## What We Built

A production-ready weather alerts data pipeline that:

✅ **Fetches weather alerts** from the National Weather Service API for all 50 US states + territories  
✅ **Normalizes the data** into a consistent schema with stable IDs for deduplication  
✅ **Stores in Lakebase** (Databricks-managed Postgres) in the `dataexpert_student` database  
✅ **Follows the massive_client.py pattern** for scalable, maintainable API client architecture  
✅ **Uses psycopg2 + RealDictCursor** for efficient database access as specified  

## Complete File Structure

```
homework 3/
├── weather_alerts_client.py       # NWS API client (modeled after massive_client.py)
├── sync_weather_alerts.py         # Main sync script
├── lakebase.py                    # Lakebase connection helper
├── Weather Alerts Demo.ipynb      # Demo notebook with queries
├── requirements.txt               # Python dependencies
├── README.md                      # Complete documentation
├── PROJECT_SUMMARY.md             # This file
├── .env.example                   # Environment template
├── .gitignore                     # Git ignore rules
│
├── app.py                         # (Optional) Flask web app
├── weather_handler.py             # (Optional) Weather handler
├── app.yaml                       # (Optional) Databricks App config
└── templates/
    └── index.html                 # (Optional) Web UI
```

## Key Components

### 1. weather_alerts_client.py

**Purpose**: Reusable client for fetching weather alerts from the NWS API

**Features**:
- Session management with proper User-Agent headers
- `get_alerts_for_state(state_code)` - Fetch alerts for a single state
- `get_all_alerts()` - Fetch alerts for all 56 states/territories
- Automatic normalization into database schema
- Error handling for individual state failures

**Pattern**: Follows `massive_client.py` structure with:
- Class-based client with configurable timeout
- Session reuse for connection pooling
- Clear separation between API calls and data transformation

### 2. sync_weather_alerts.py

**Purpose**: Main orchestration script that runs the data pipeline

**Steps**:
1. `ensure_database()` - Creates `dataexpert_student` database if needed
2. `ensure_table()` - Creates `weather_information` table with proper schema
3. `sync_alerts()` - Fetches alerts and stores them with deduplication

**Features**:
- Uses `ON CONFLICT (id) DO UPDATE` for upserts
- Logging at each step for observability
- Transaction management for data consistency
- Returns count of synced alerts

### 3. lakebase.py

**Purpose**: Connection helper for Lakebase (Postgres)

**Key Enhancement**: Added `database` parameter to `get_connection()`
```python
with lakebase.get_connection(database="dataexpert_student") as conn:
    # Work in the dataexpert_student database
    ...
```

**Features**:
- Fetches connection URL from Databricks Secrets
- RealDictCursor factory for dict-based results
- Context manager for automatic connection cleanup
- URL parsing to override database name

### 4. Weather Alerts Demo.ipynb

**Purpose**: Interactive demonstration and testing notebook

**Cells**:
1. Introduction and architecture overview
2. Run the sync script
3. Query total count and event types
4. Sample recent alerts
5. Analyze alerts by state
6. View full alert details with narrative text

## Database Schema

```sql
CREATE TABLE weather_information (
    id TEXT PRIMARY KEY,                    -- NWS alert ID (stable dedup key)
    location TEXT NOT NULL,                 -- "Los Angeles County, CA"
    source_type TEXT NOT NULL,              -- "alert" (or "forecast" future)
    headline TEXT,                          -- Alert headline
    event TEXT NOT NULL,                    -- "Flash Flood Warning"
    narrative_text TEXT,                    -- Description + instructions
    issued_at TIMESTAMPTZ,                  -- When issued
    effective_at TIMESTAMPTZ,               -- When effective
    expires_at TIMESTAMPTZ,                 -- When expires
    payload JSONB NOT NULL,                 -- Raw JSON for provenance
    synced_at TIMESTAMPTZ NOT NULL          -- When we fetched it
);
```

## Data Flow

```
NWS API (api.weather.gov)
    ↓
    ↓ GET /alerts/active/area/{state} for each state
    ↓
WeatherAlertsClient
    ↓
    ↓ Normalize GeoJSON features into schema
    ↓
Sync Script
    ↓
    ↓ INSERT ... ON CONFLICT (id) DO UPDATE
    ↓
Lakebase (dataexpert_student.weather_information)
    ↓
    ↓ Query for analytics
    ↓
Databricks Notebooks / SQL Queries
```

## How to Run

### Setup (One-time)

1. **Create Lakebase Instance**:
   - Go to Catalog > Lakebase
   - Create instance with native password auth
   - Copy connection URL

2. **Store Connection URL in Secrets**:
   ```python
   from databricks.sdk import WorkspaceClient
   import base64
   
   w = WorkspaceClient()
   w.secrets.create_scope(scope="database")
   
   url = "postgresql://role:pass@host:5432/databricks_postgres?sslmode=require"
   encoded = base64.b64encode(url.encode()).decode()
   w.secrets.put_secret(scope="database", key="lakebase-url", string_value=encoded)
   ```

### Running the Sync

**Option 1: From a Notebook**
```python
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

from sync_weather_alerts import main
main()
```

**Option 2: Open the Demo Notebook**
- Open `Weather Alerts Demo.ipynb`
- Run Cell 2 ("Run Weather Alerts Sync")
- View results in subsequent cells

**Option 3: Schedule as a Job**
- Create a Databricks Job
- Point to `sync_weather_alerts.py`
- Schedule to run hourly or daily

## Example Queries

### Count by Event Type
```python
import lakebase

results = lakebase.run_query("""
    SELECT event, COUNT(*) as count
    FROM weather_information
    GROUP BY event
    ORDER BY count DESC
""")
```

### Recent Alerts
```python
results = lakebase.run_query("""
    SELECT location, event, headline, issued_at
    FROM weather_information
    ORDER BY issued_at DESC
    LIMIT 10
""")
```

### Active Alerts (not expired)
```python
results = lakebase.run_query("""
    SELECT *
    FROM weather_information
    WHERE expires_at > NOW()
    ORDER BY issued_at DESC
""")
```

## Next Steps

1. **Scheduling**: Set up a Databricks Job to run `sync_weather_alerts.py` every hour
2. **Analytics**: Create dashboards to visualize alert trends by state/event type
3. **Alerts**: Build notification system for critical weather events
4. **Historical Analysis**: Query trends over time (most active states, seasonal patterns)
5. **Integration**: Connect to downstream ML models or reporting systems

## Success Criteria ✅

- [x] Fetches data from NWS API for all states
- [x] Normalizes data into specified schema with all required fields
- [x] Stores in Lakebase database `dataexpert_student`
- [x] Creates table `weather_information`
- [x] Uses `get_connection()` context manager
- [x] Uses psycopg2 + RealDictCursor
- [x] Follows massive_client.py architectural pattern
- [x] Handles deduplication with stable IDs
- [x] Includes comprehensive documentation
- [x] Provides demo notebook for testing