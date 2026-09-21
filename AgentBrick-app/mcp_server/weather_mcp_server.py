"""Weather MCP Server.

Exposes weather tools over MCP (Model Context Protocol) so a Databricks
Agent Bricks agent can call them:
    - get_current_weather(location) - Current conditions, temp, humidity, wind
    - get_forecast(location, days) - Multi-day forecast with highs/lows
    - predict_umbrella_needed(location, date) - Umbrella recommendation based on forecast + embeddings
    - search_weather_news(weather_condition, max_results) - Search news articles by weather condition

These tools are backed by Open-Meteo API and Lakebase vector search (see weather_broker.py).

Deploy this as a Databricks App with app.yaml, following the FastMCP pattern.

Run locally:
    python weather_mcp_server.py
"""

import logging
import os
from datetime import datetime

from fastmcp import FastMCP

import weather_broker
import tracing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp-server")

mcp = FastMCP("weather-service")

# Generate a unique session ID for this MCP server process.
# All tool calls within this process are grouped under the same session.
# For per-conversation sessions, call tracing.create_session() per request.
SESSION_ID = tracing.create_session(agent_name="weather-mcp-server")
logger.info(f"MCP server session: {SESSION_ID}")


@mcp.tool
def get_current_weather(location: str) -> dict:
    """
    Get current weather conditions for a location.
    
    This tool provides real-time weather data including temperature,
    conditions, humidity, wind speed, and more.
    
    Args:
        location: Location to check. Can be:
                 - City name (e.g., "London", "New York")
                 - City with country (e.g., "London,UK", "Tokyo,JP")
                 - US zip code (e.g., "10001,US")
                 - Latitude/longitude (e.g., "51.5074,-0.1278")
    
    Returns:
        Dict containing:
        - location: Resolved location name
        - coordinates: {lat, lon}
        - temperature: Current temp in Fahrenheit
        - feels_like: Feels-like temp in Fahrenheit
        - conditions: Weather description (e.g., "clear sky", "light rain")
        - humidity: Humidity percentage
        - wind_speed: Wind speed in mph
        - pressure: Atmospheric pressure in hPa
        - visibility: Visibility in meters
        - timestamp: ISO timestamp of observation
    
    Example:
        get_current_weather("San Francisco")
        get_current_weather("37.7749,-122.4194")
    """
    try:
        logger.info(f"Getting current weather for: {location}")
        result = tracing.traced_call(
            session_id=SESSION_ID,
            tool_name="get_current_weather",
            mcp_server="weather-service",
            agent_name="weather-mcp-server",
            input_args={"location": location},
            tool_fn=weather_broker.get_current_weather,
            location=location,
        )
        logger.info(f"Successfully retrieved weather for {result['location']}")
        return result
    except Exception as e:
        logger.exception(f"Failed to get current weather for {location}")
        return {
            "status": "error",
            "message": f"Failed to get current weather: {str(e)}",
            "location": location
        }


@mcp.tool
def get_forecast(location: str, days: int = 3) -> dict:
    """
    Get multi-day weather forecast for a location.
    
    This tool provides a forecast with daily high/low temperatures,
    precipitation chances, and general conditions for the next N days.
    
    Args:
        location: Location to check. Can be:
                 - City name (e.g., "London", "New York")
                 - City with country (e.g., "London,UK", "Tokyo,JP")
                 - US zip code (e.g., "10001,US")
                 - Latitude/longitude (e.g., "51.5074,-0.1278")
        days: Number of days to forecast (1-16, default 3)
    
    Returns:
        Dict containing:
        - location: Resolved location name
        - coordinates: {lat, lon}
        - forecast_days: Number of days in forecast
        - forecasts: List of daily forecasts, each with:
            - date: ISO date string
            - temp_high: High temp in Fahrenheit
            - temp_low: Low temp in Fahrenheit
            - conditions: Weather description
            - precipitation_probability: Probability of precipitation (0-100%)
            - precipitation_sum: Total precipitation in inches
    
    Example:
        get_forecast("Chicago", 5)
        get_forecast("40.7128,-74.0060", 3)
    """
    try:
        # Validate days parameter
        if days < 1:
            days = 1
        elif days > 16:
            days = 16
        
        logger.info(f"Getting {days}-day forecast for: {location}")
        result = tracing.traced_call(
            session_id=SESSION_ID,
            tool_name="get_forecast",
            mcp_server="weather-service",
            agent_name="weather-mcp-server",
            input_args={"location": location, "days": days},
            tool_fn=weather_broker.get_forecast,
            location=location,
            days=days,
        )
        logger.info(f"Successfully retrieved {days}-day forecast for {result['location']}")
        return result
    except Exception as e:
        logger.exception(f"Failed to get forecast for {location}")
        return {
            "status": "error",
            "message": f"Failed to get forecast: {str(e)}",
            "location": location
        }


@mcp.tool
def search_weather_news(weather_condition: str, max_results: int = 5) -> dict:
    """
    Search for weather news articles by weather condition across all locations.
    
    This tool uses vector similarity search on historical weather alert embeddings
    to find news articles matching your weather condition query. Results show:
    - Top affected locations/areas
    - Relevant weather events and alerts
    - Article excerpts with similarity scores
    
    Use this to discover:
    - Where a specific weather condition occurred historically
    - News coverage of floods, hurricanes, heatwaves, etc.
    - Top locations affected by specific weather patterns
    
    Args:
        weather_condition: Weather condition to search for. Can be:
                          - Specific events: "flooding", "tornado", "hurricane"
                          - General conditions: "heavy rain", "extreme heat", "winter storm"
                          - Natural language: "severe thunderstorms with hail"
        max_results: Maximum number of articles to return (1-50, default 5)
    
    Returns:
        Dict containing:
        - query: The weather condition searched
        - found: Number of matching articles
        - articles: List of relevant articles (top 5 by default), each with:
            - rank: Position in results (1-based)
            - location: Where the weather occurred
            - event: Type of weather event (e.g., "Flash Flood Warning")
            - excerpt: First 300 characters of the article
            - similarity_score: How similar to your query (0-1)
            - full_text: Complete article text
            - search_link: Clickable Google News search URL to find the full article
            - link_title: Descriptive title for the link (e.g., "Read about Flash Flood Warning in Miami, FL")
        - top_locations: Top 5 locations by article count
        - message: Summary of search results
    
    Example:
        search_weather_news("flooding")  # Returns top 5 flooding articles with links
        search_weather_news("severe thunderstorms", 5)  # Returns top 5 articles
        search_weather_news("hurricane")  # Returns top 5 hurricane articles
    """
    try:
        # Validate max_results
        if max_results < 1:
            max_results = 1
        elif max_results > 50:
            max_results = 50
        
        logger.info(f"Searching weather news for: {weather_condition}")
        result = tracing.traced_call(
            session_id=SESSION_ID,
            tool_name="search_weather_news",
            mcp_server="weather-service",
            agent_name="weather-mcp-server",
            input_args={"weather_condition": weather_condition, "max_results": max_results},
            tool_fn=weather_broker.search_weather_news,
            weather_condition=weather_condition,
            max_results=max_results,
        )
        logger.info(f"Found {result['found']} articles about '{weather_condition}'")
        return result
    except Exception as e:
        logger.exception(f"Failed to search weather news for: {weather_condition}")
        return {
            "status": "error",
            "message": f"Failed to search weather news: {str(e)}",
            "query": weather_condition
        }


@mcp.tool
def predict_umbrella_needed(location: str, date: str = None) -> dict:
    """
    Predict whether an umbrella will be needed at a location on a given date.
    
    This tool uses vector search on historical weather alert embeddings to provide
    data-driven recommendations. It combines:
    - Real-time weather forecast from Open-Meteo
    - Vector similarity search on weather_alert_embeddings table
    - 40% precipitation threshold
    - Historical pattern analysis from similar weather events
    
    Args:
        location: Location to check. Can be:
                 - City name (e.g., "London", "New York", "Chicago", "Atlanta")
                 - City with country (e.g., "London,UK", "Tokyo,JP")
                 - US zip code (e.g., "10001,US")
                 - Latitude/longitude (e.g., "51.5074,-0.1278")
        date: Target date in ISO format (YYYY-MM-DD). If None, uses tomorrow.
    
    Returns:
        Dict containing:
        - location: Resolved location name
        - date: Target date checked
        - umbrella_needed: Boolean recommendation
        - confidence: Confidence level ("high", "medium", "low")
        - reasoning: Detailed explanation with historical context
        - precipitation_probability: Forecast precipitation percentage
        - precipitation_sum: Expected precipitation amount
        - conditions: Expected weather conditions
        - temp_high: High temperature in Fahrenheit
        - temp_low: Low temperature in Fahrenheit
        - similar_patterns: Analysis of historical weather patterns
        - top_influencing_articles: Top 3 weather alerts/articles that influenced the decision
          (each with rank, location, event, excerpt, similarity_score)
    
    Example:
        predict_umbrella_needed("Seattle")
        predict_umbrella_needed("Chicago", "2024-07-15")
        predict_umbrella_needed("Atlanta")
    """
    try:
        logger.info(f"Predicting umbrella need for {location}")
        
        # Use vector search-enhanced prediction (date parsing handled in broker)
        result = tracing.traced_call(
            session_id=SESSION_ID,
            tool_name="predict_umbrella_needed",
            mcp_server="weather-service",
            agent_name="weather-mcp-server",
            input_args={"location": location, "date": date},
            tool_fn=weather_broker.predict_umbrella_with_vector_search,
            location=location,
            date=date,
        )
        logger.info(f"Umbrella prediction for {result['location']} on {result['date']}: {result['umbrella_needed']}")
        return result
        

    except Exception as e:
        logger.exception(f"Failed to predict umbrella need for {location} on {date}")
        return {
            "status": "error",
            "message": f"Failed to predict umbrella need: {str(e)}",
            "location": location,
            "date": date or "tomorrow"
        }


if __name__ == "__main__":
    # Run the MCP server with HTTP transport for Databricks Apps
    # Databricks Apps sets the PORT environment variable
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )
