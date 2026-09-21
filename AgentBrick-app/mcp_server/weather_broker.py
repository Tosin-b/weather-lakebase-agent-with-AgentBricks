"""Weather API broker module for the Weather MCP server.

This module handles all HTTP interactions with the Open-Meteo API.
No raw requests calls should be made inside @mcp.tool functions - all
API calls are centralized here.

API Documentation: https://open-meteo.com/en/docs

Note: Open-Meteo is free and does not require an API key.
"""

from datetime import datetime, timedelta
from typing import Optional
import sys
import os

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

# Open-Meteo API base URLs
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Initialize embedding model (384 dimensions to match your table)
_embedding_model = None

def _get_embedding_model():
    """Lazy load the sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    return _embedding_model


def _resolve_location(location: str) -> dict:
    """Resolve a location string (city name, zip, or lat/lon) to coordinates.
    
    Args:
        location: City name (e.g., "London"), zip code (e.g., "10001,US"),
                 or lat/lon (e.g., "51.5074,-0.1278")
    
    Returns:
        Dict with 'lat', 'lon', and 'name' keys
    """
    # Check if it's lat/lon format (comma-separated numbers)
    if ',' in location:
        parts = location.split(',')
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return {'lat': lat, 'lon': lon, 'name': f"{lat},{lon}"}
        except ValueError:
            # Not lat/lon, treat as city name
            pass
    
    # Try geocoding API for city names
    params = {
        'name': location,
        'count': 1,
        'language': 'en',
        'format': 'json'
    }
    
    response = requests.get(_GEO_URL, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    if 'results' not in data or not data['results']:
        raise ValueError(f"Could not resolve location: {location}")
    
    result = data['results'][0]
    return {
        'lat': result['latitude'],
        'lon': result['longitude'],
        'name': result.get('name', location)
    }


def get_current_weather(location: str) -> dict:
    """Get current weather conditions for a location.
    
    Args:
        location: City name, zip code, or lat/lon coordinates
    
    Returns:
        Dict with temperature, conditions, humidity, wind speed, and location info
    """
    # Resolve location to coordinates
    loc = _resolve_location(location)
    
    # Call Open-Meteo forecast API for current weather
    params = {
        'latitude': loc['lat'],
        'longitude': loc['lon'],
        'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,pressure_msl,wind_speed_10m',
        'temperature_unit': 'fahrenheit',
        'wind_speed_unit': 'mph',
        'precipitation_unit': 'inch'
    }
    
    response = requests.get(_FORECAST_URL, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    current = data['current']
    
    # Map weather code to description
    weather_code = current.get('weather_code', 0)
    conditions = _weather_code_to_description(weather_code)
    
    return {
        'location': loc['name'],
        'coordinates': {'lat': loc['lat'], 'lon': loc['lon']},
        'temperature': round(current['temperature_2m'], 1),
        'feels_like': round(current['apparent_temperature'], 1),
        'conditions': conditions,
        'humidity': current['relative_humidity_2m'],
        'wind_speed': round(current['wind_speed_10m'], 1),
        'pressure': current['pressure_msl'],
        'precipitation': current.get('precipitation', 0),
        'timestamp': current['time']
    }


def _get_lakebase_connection():
    """Get Lakebase connection from environment or secrets.
    
    Tries LAKEBASE_URL env var first (for testing), then falls back to
    fetching from Databricks secrets.
    """
    # Try environment variable first (for local testing)
    lakebase_url = os.environ.get('LAKEBASE_URL')
    
    if not lakebase_url:
        # Fall back to Databricks secrets
        try:
            from databricks.sdk import WorkspaceClient
            import base64
            
            w = WorkspaceClient()
            secret_scope = os.environ.get('LAKEBASE_SECRET_SCOPE', 'database')
            secret_key = os.environ.get('LAKEBASE_SECRET_KEY', 'lakebase-url')
            
            secret = w.secrets.get_secret(scope=secret_scope, key=secret_key)
            lakebase_url = base64.b64decode(secret.value).decode('utf-8')
        except Exception as e:
            raise RuntimeError(f"Could not get Lakebase URL from secrets: {e}")
    
    # Parse connection URL
    from urllib.parse import urlparse
    parsed = urlparse(lakebase_url)
    
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname='dataexpert_student',  # Your embeddings database
        user=parsed.username,
        password=parsed.password,
        sslmode='require',
        cursor_factory=RealDictCursor
    )


def _generate_embedding(text: str) -> list:
    """Generate embedding vector from text using sentence-transformers."""
    model = _get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def _search_similar_weather_alerts(query_text: str, location: str = None, top_k: int = 5) -> list:
    """Search for similar weather alerts using vector similarity.
    
    Args:
        query_text: Text to search for (e.g., "moderate rain, 65% precipitation")
        location: Optional location filter
        top_k: Number of similar results to return
    
    Returns:
        List of similar weather alerts with their events and text
    """
    # Generate embedding for the query
    query_embedding = _generate_embedding(query_text)
    
    # Format embedding as PostgreSQL array string
    embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
    
    # Build query with optional location filter
    if location:
        sql = f"""
        SELECT 
            id,
            location,
            event,
            chunk_text,
            embedding <=> %s::vector AS distance
        FROM weather_alert_embeddings
        WHERE location ILIKE %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """
        params = (embedding_str, f'%{location}%', embedding_str, top_k)
    else:
        sql = f"""
        SELECT 
            id,
            location,
            event,
            chunk_text,
            embedding <=> %s::vector AS distance
        FROM weather_alert_embeddings
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """
        params = (embedding_str, embedding_str, top_k)
    
    try:
        conn = _get_lakebase_connection()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            results = cur.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"Vector search failed: {e}", file=sys.stderr)
        return []


def _is_rain_related_event(event: str) -> bool:
    """Check if a weather event type suggests rain/precipitation."""
    if not event:
        return False
    
    event_lower = event.lower()
    rain_keywords = [
        'rain', 'shower', 'flood', 'storm', 'thunderstorm',
        'drizzle', 'precipitation', 'downpour', 'wet'
    ]
    return any(keyword in event_lower for keyword in rain_keywords)


def _analyze_similar_weather_patterns(similar_alerts: list) -> dict:
    """Analyze similar weather alerts to provide context for umbrella decision.
    
    Args:
        similar_alerts: List of similar weather alerts from vector search
    
    Returns:
        Dict with rain_event_count, total_events, and rain_percentage
    """
    if not similar_alerts:
        return {'rain_event_count': 0, 'total_events': 0, 'rain_percentage': 0}
    
    rain_events = sum(1 for alert in similar_alerts if _is_rain_related_event(alert.get('event', '')))
    total = len(similar_alerts)
    rain_pct = (rain_events / total * 100) if total > 0 else 0
    
    return {
        'rain_event_count': rain_events,
        'total_events': total,
        'rain_percentage': round(rain_pct, 1)
    }


def _weather_code_to_description(code: int) -> str:
    """Convert Open-Meteo weather code to human-readable description.
    
    WMO Weather interpretation codes (WW):
    https://open-meteo.com/en/docs
    """
    weather_codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail"
    }
    return weather_codes.get(code, "Unknown")


def get_forecast(location: str, days: int = 5) -> dict:
    """Get multi-day weather forecast for a location.
    
    Args:
        location: City name, zip code, or lat/lon coordinates
        days: Number of days to forecast (max 5)
    
    Returns:
        Dict with daily forecasts including temp high/low, precipitation, conditions
    """
    if days > 16:
        days = 16  # Open-Meteo API limit
    
    # Resolve location to coordinates
    loc = _resolve_location(location)
    
    # Call Open-Meteo forecast API for daily forecasts
    params = {
        'latitude': loc['lat'],
        'longitude': loc['lon'],
        'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code',
        'temperature_unit': 'fahrenheit',
        'precipitation_unit': 'inch',
        'forecast_days': days
    }
    
    response = requests.get(_FORECAST_URL, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    daily_data = data['daily']
    
    # Build forecast list
    forecast_list = []
    for i in range(len(daily_data['time'])):
        weather_code = daily_data['weather_code'][i]
        forecast_list.append({
            'date': daily_data['time'][i],
            'temp_high': round(daily_data['temperature_2m_max'][i], 1),
            'temp_low': round(daily_data['temperature_2m_min'][i], 1),
            'conditions': _weather_code_to_description(weather_code),
            'precipitation_sum': round(daily_data['precipitation_sum'][i], 2),
            'precipitation_probability': daily_data['precipitation_probability_max'][i]
        })
    
    return {
        'location': loc['name'],
        'coordinates': {'lat': loc['lat'], 'lon': loc['lon']},
        'forecast_days': len(forecast_list),
        'forecasts': forecast_list
    }


def search_weather_news(weather_condition: str, max_results: int = 5) -> dict:
    """Search weather alert news articles by weather condition using vector similarity.
    
    This function:
    1. Takes a weather condition query (e.g., "flooding", "hurricane", "heatwave")
    2. Generates an embedding for the query
    3. Searches for similar weather alerts in the embeddings table
    4. Groups results by location to show top affected areas
    
    Args:
        weather_condition: Weather condition to search for (e.g., "rain", "flood", "tornado")
        max_results: Maximum number of articles to return (default 5)
    
    Returns:
        Dict with search results grouped by location
    """
    import sys
    
    # Search for similar weather alerts (function generates embedding internally)
    similar_alerts = _search_similar_weather_alerts(
        query_text=weather_condition,
        location=None,  # No location filter - search everywhere
        top_k=max_results
    )
    
    if not similar_alerts:
        return {
            'query': weather_condition,
            'found': 0,
            'articles': [],
            'top_locations': [],
            'message': 'No weather articles found matching this condition.'
        }
    
    # Format articles with details
    articles = []
    location_counts = {}
    
    for i, alert in enumerate(similar_alerts):
        location = alert.get('location', 'Unknown')
        event = alert.get('event', 'Unknown')
        chunk_text = alert.get('chunk_text', '')
        similarity_score = round(1 - alert.get('distance', 1.0), 3)
        
        # Excerpt: first 300 chars
        excerpt = chunk_text[:300] + '...' if len(chunk_text) > 300 else chunk_text
        
        # Generate a Google News search link for this article
        # URL encode the search query: "event" "location"
        import urllib.parse
        search_query = f'"{event}" "{location}"'
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}&tbm=nws"
        
        # Create a descriptive link title
        link_title = f"Read about {event} in {location}"
        
        articles.append({
            'rank': i + 1,
            'location': location,
            'event': event,
            'excerpt': excerpt,
            'similarity_score': similarity_score,
            'full_text': chunk_text,
            'search_link': search_url,
            'link_title': link_title
        })
        
        # Count articles per location
        location_counts[location] = location_counts.get(location, 0) + 1
    
    # Get top locations by article count
    top_locations = sorted(
        [{'location': loc, 'article_count': count} 
         for loc, count in location_counts.items()],
        key=lambda x: x['article_count'],
        reverse=True
    )[:5]  # Top 5 locations
    
    # Format a user-friendly message with embedded links
    message_parts = [f'Found {len(articles)} weather articles about "{weather_condition}":', '']
    message_parts.append('Top articles with links:')
    for article in articles:
        message_parts.append(
            f"{article['rank']}. [{article['location']} - {article['event']}]({article['search_link']})"
        )
    
    formatted_message = '\n'.join(message_parts)
    
    return {
        'query': weather_condition,
        'found': len(articles),
        'articles': articles,
        'top_locations': top_locations,
        'message': formatted_message
    }


def predict_umbrella_with_vector_search(location: str, date: str = None) -> dict:
    """Predict umbrella need using forecast + vector search on historical weather patterns.
    
    This function:
    1. Gets the weather forecast from Open-Meteo
    2. Generates an embedding from the forecast conditions
    3. Searches for similar weather alerts in your embeddings table
    4. Applies 40% precipitation threshold + historical pattern analysis
    
    Args:
        location: Location to check (city name, coordinates, etc.)
        date: Target date (YYYY-MM-DD). Defaults to tomorrow if None.
    
    Returns:
        Dict with umbrella_needed, confidence, reasoning, and supporting data
    """
    from datetime import datetime, timedelta
    
    # Determine target date
    if date is None:
        target_date = (datetime.now() + timedelta(days=1)).date().isoformat()
    else:
        try:
            datetime.fromisoformat(date)
            target_date = date
        except ValueError:
            raise ValueError(f"Invalid date format. Use YYYY-MM-DD, got: {date}")
    
    # Get forecast
    forecast_result = get_forecast(location, days=16)
    
    # Find target day in forecast
    target_forecast = None
    for day_forecast in forecast_result['forecasts']:
        if day_forecast['date'] == target_date:
            target_forecast = day_forecast
            break
    
    if target_forecast is None:
        raise ValueError(
            f"Forecast not available for {target_date}. Only next 16 days available."
        )
    
    # Extract forecast data
    precipitation_probability = target_forecast['precipitation_probability']
    conditions = target_forecast['conditions']
    temp_high = target_forecast['temp_high']
    temp_low = target_forecast['temp_low']
    
    # Build query text for vector search
    query_text = f"{conditions}, {precipitation_probability}% precipitation probability, high {temp_high}°F, low {temp_low}°F"
    
    # Search for similar weather patterns in your embeddings
    similar_alerts = _search_similar_weather_alerts(
        query_text=query_text,
        location=forecast_result['location'],
        top_k=5
    )
    
    # Analyze historical patterns
    pattern_analysis = _analyze_similar_weather_patterns(similar_alerts)
    
    # Decision logic: 40% threshold + historical pattern boost
    base_umbrella_needed = precipitation_probability > 40.0
    
    # If similar historical patterns show high rain events, boost confidence
    historical_rain_factor = pattern_analysis['rain_percentage'] / 100.0
    
    # Final decision: base threshold OR strong historical rain pattern
    umbrella_needed = base_umbrella_needed or (historical_rain_factor > 0.6)
    
    # Determine confidence
    if precipitation_probability >= 70:
        confidence = "high"
        reasoning = f"Strong recommendation to bring an umbrella. There's a {precipitation_probability}% chance of precipitation with {conditions}."
    elif precipitation_probability >= 40:
        confidence = "medium"
        reasoning = f"Moderate recommendation to bring an umbrella. There's a {precipitation_probability}% chance of precipitation with {conditions}."
    elif precipitation_probability >= 20:
        confidence = "medium"
        reasoning = f"Umbrella probably not needed, but consider: {precipitation_probability}% chance of precipitation with {conditions}."
    else:
        confidence = "high"
        reasoning = f"Umbrella not needed. Very low {precipitation_probability}% chance of precipitation with {conditions}."
    
    # Add historical context if we found similar patterns
    if similar_alerts:
        reasoning += f" Based on {pattern_analysis['total_events']} similar weather patterns, {pattern_analysis['rain_event_count']} ({pattern_analysis['rain_percentage']}%) involved rain-related events."
    else:
        # No historical data found - explain this clearly
        reasoning += "\n\n⚠️ Note: No similar historical weather alerts found in the database for this location. This recommendation is based solely on the current forecast."
    
    # Check conditions for rain keywords
    conditions_lower = conditions.lower()
    if any(word in conditions_lower for word in ['rain', 'shower', 'storm', 'drizzle']):
        reasoning += f" Note: Conditions explicitly mention '{conditions}' - definitely bring an umbrella."
        umbrella_needed = True
        confidence = "high"
    
    # Extract articles that influenced the decision (show as many as we have, up to 3)
    top_articles = []
    for i, alert in enumerate(similar_alerts[:3]):
        similarity_score = round(1 - alert.get('distance', 1.0), 3)
        excerpt = alert.get('chunk_text', '')[:200] + '...' if len(alert.get('chunk_text', '')) > 200 else alert.get('chunk_text', '')
        
        top_articles.append({
            'rank': i + 1,
            'location': alert.get('location', 'Unknown'),
            'event': alert.get('event', 'Unknown'),
            'excerpt': excerpt,
            'similarity_score': similarity_score
        })
    
    # Add articles to reasoning - show whatever we have (1, 2, or 3)
    if top_articles:
        article_count = len(top_articles)
        reasoning += f"\n\n📰 Supporting Evidence ({article_count} Similar Weather Alert{'s' if article_count != 1 else ''}):\n"
        for article in top_articles:
            reasoning += f"\n{article['rank']}. **{article['event']}** in {article['location']} (similarity: {article['similarity_score']:.1%})\n"
            reasoning += f"   \"{article['excerpt']}\"\n"
    
    return {
        'location': forecast_result['location'],
        'date': target_date,
        'umbrella_needed': umbrella_needed,
        'confidence': confidence,
        'reasoning': reasoning,
        'precipitation_probability': precipitation_probability,
        'precipitation_sum': target_forecast['precipitation_sum'],
        'conditions': conditions,
        'temp_high': temp_high,
        'temp_low': temp_low,
        'similar_patterns': {
            'found': len(similar_alerts),
            'rain_events': pattern_analysis['rain_event_count'],
            'rain_percentage': pattern_analysis['rain_percentage']
        },
        'top_influencing_articles': top_articles
    }
