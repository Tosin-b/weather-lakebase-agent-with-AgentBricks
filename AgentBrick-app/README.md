# Weather Alerts Collection System - Databricks Lakehouse

A comprehensive weather alerts collection and storage system built with Databricks that:
- Fetches active weather alerts from the National Weather Service API for all US states
- Normalizes and stores weather alert data in Lakebase (Databricks-managed Postgres)
- Provides a scalable, production-ready data pipeline following the massive_client.py pattern
- Enables real-time weather alert monitoring and analytics
- (Optional) Flask web interface for displaying weather data

## Files

### Core Weather Alerts System
- **`weather_alerts_client.py`** - Client for fetching weather alerts from NWS API (modeled after massive_client.py)
- **`sync_weather_alerts.py`** - Main sync script that orchestrates the data pipeline
- **`lakebase.py`** - Lakebase (Postgres) connection helper with database override support
- **`Weather Alerts Demo.ipynb`** - Notebook demonstrating the complete workflow

### Optional Flask Web App
- `app.py` - Main Flask application with weather API endpoints
- `weather_handler.py` - MVC Controller for weather data operations
- `templates/index.html` - Frontend web interface
- `app.yaml` - Databricks App deployment configuration

### Configuration
- `requirements.txt` - Python dependencies
- `.env.example` - Environment variables template
- `.gitignore` - Git ignore rules

## Weather Alerts Data Pipeline

### Overview

The system fetches active weather alerts from the **National Weather Service (NWS) API** for all 50 US states plus territories. It normalizes the data into a consistent schema and stores it in a Lakebase Postgres database for analytics.

**API Endpoint**: `https://api.weather.gov/alerts/active/area/{state}` (no API key required - public government API)

### Data Schema

The `weather_information` table in the `dataexpert_student` database contains:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (PK) | Stable dedup key (NWS alert ID) |
| `location` | TEXT | City/state or area description |
| `source_type` | TEXT | "alert" (or "forecast" for future use) |
| `headline` | TEXT | Alert headline |
| `event` | TEXT | Event type (e.g., "Flash Flood Warning") |
| `narrative_text` | TEXT | Full description and instructions |
| `issued_at` | TIMESTAMPTZ | When the alert was issued |
| `effective_at` | TIMESTAMPTZ | When the alert becomes effective |
| `expires_at` | TIMESTAMPTZ | When the alert expires |
| `payload` | JSONB | Raw JSON for provenance |
| `synced_at` | TIMESTAMPTZ | Timestamp when we fetched it |

### Architecture (Following massive_client.py Pattern)

1. **`WeatherAlertsClient`** - Reusable client class with:
   - Session management for efficient HTTP requests
   - User-Agent header required by NWS API
   - `get_alerts_for_state(state_code)` - Fetch alerts for one state
   - `get_all_alerts()` - Fetch and normalize alerts for all states
   - Error handling and retry logic

2. **Normalization** - Extracts key fields from GeoJSON features:
   - Stable alert IDs for deduplication
   - Location from areaDesc field
   - Combines description + instruction into narrative_text
   - Parses ISO 8601 timestamps

3. **Storage** - Uses Lakebase (Postgres) with:
   - `get_connection(database="dataexpert_student")` - Connect to specific database
   - `ON CONFLICT (id) DO UPDATE` - Handle duplicate alerts
   - RealDictCursor for dict-based results

### Running the Sync

```python
# In a Databricks notebook
import sys
sys.path.insert(0, '/Workspace/Users/tosynbiala@gmail.com/homework 3')

from sync_weather_alerts import main
main()  # Fetches alerts for all states and stores in Lakebase
```

Or open the **Weather Alerts Demo** notebook for a complete walkthrough.

## Setup

### 1. Get a Weather API Key

Sign up for a free API key from one of these providers:
- [OpenWeatherMap](https://openweathermap.org/api) (recommended)
- [WeatherAPI](https://www.weatherapi.com/)
- [Visual Crossing](https://www.visualcrossing.com/)

### 2. Create a Lakebase Instance (Optional for data storage)

1. In Databricks, go to **Catalog** > **Lakebase**
2. Click **Create Lakebase instance**
3. Enable **Native password authentication**
4. Create a new role with password authentication
5. Copy the connection URL

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and add your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:
- `WEATHER_API_KEY` - Your weather API key
- `LAKEBASE_URL` - Your Lakebase connection URL (optional)

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Run Locally

```bash
python app.py
```

The app will be available at `http://localhost:8080`

### 6. Deploy to Databricks Apps

1. **Create a Git folder** in Databricks workspace
2. **Create a Databricks App**:
   - Go to **Compute** > **Apps**
   - Click **Create app**
   - Point to your Git folder
3. **Deploy** the app

## API Endpoints

- `GET /` - Main weather app interface
- `GET /api/weather?city=<city>` - Get current weather for a city
- `GET /api/forecast?city=<city>&days=<days>` - Get weather forecast

## Features

- 🌤️ Current weather data (temperature, condition, humidity, wind speed)
- 📊 Multi-day weather forecast
- 💾 Optional Lakebase storage for historical weather data
- 📱 Responsive design that works on mobile and desktop
- 🎨 Beautiful gradient UI with smooth animations

## MVC Architecture

- **Model**: Weather data structures and Lakebase integration
- **View**: HTML templates with CSS and JavaScript
- **Controller**: `weather_handler.py` manages business logic

## Next Steps

1. Implement real weather API integration in `weather_handler.py`
2. Add Lakebase storage for historical weather data
3. Create dashboards in Unity Catalog for weather analytics
4. Add user authentication and personalized weather tracking
5. Implement weather alerts and notifications