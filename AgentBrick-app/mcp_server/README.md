# Weather MCP Server

A Model Context Protocol (MCP) server that provides weather information tools for Databricks Agent Bricks agents.

## Features

This MCP server exposes three weather-related tools:

1. **get_current_weather(location)** - Get current weather conditions including:
   - Temperature (Fahrenheit)
   - Feels-like temperature
   - Weather conditions description
   - Humidity percentage
   - Wind speed
   - Atmospheric pressure
   - Visibility

2. **get_forecast(location, days)** - Get multi-day weather forecast with:
   - Daily high/low temperatures
   - Average temperature
   - Precipitation chance (0-100%)
   - Weather conditions
   - Average humidity

3. **predict_umbrella_needed(location, date)** - Smart recommendation engine that:
   - Analyzes forecast data
   - Uses 40% precipitation threshold
   - Provides confidence level (high/medium/low)
   - Includes detailed reasoning
   - Checks for rain/storm keywords in conditions

## Architecture

```
weather_mcp_server.py    # FastMCP server with @mcp.tool decorators
weather_broker.py        # HTTP adapter for OpenWeatherMap API
app.yaml                 # Databricks App configuration
requirements.txt         # Python dependencies
```

Follows the clean separation pattern:
- **MCP Server**: Tool definitions and business logic
- **Broker**: All HTTP calls and API interactions
- **No raw requests in tools**: All API calls centralized in broker

## Setup

### 1. Get OpenWeatherMap API Key

1. Sign up for a free account at [OpenWeatherMap](https://openweathermap.org/api)
2. Generate an API key from your account dashboard
3. Note: Free tier includes:
   - Current weather data
   - 5-day forecast (3-hour intervals)
   - 60 calls/minute rate limit

### 2. Store API Key as Databricks Secret

```bash
# Create secret scope (if it doesn't exist)
databricks secrets create-scope weather

# Store the API key (base64 encoded)
echo -n "YOUR_OPENWEATHER_API_KEY" | base64 | databricks secrets put-secret weather openweather-api-key
```

**Important**: Never hardcode the API key or commit it to the repo!

### 3. Deploy as Databricks App

From the `mcp_server` directory:

```bash
# Create the app
databricks apps create weather-mcp-server

# Deploy the app
databricks apps deploy weather-mcp-server \
  --source-code-path .

# Get the app URL
databricks apps get weather-mcp-server
```

The app URL will be in format:
```
https://<workspace-url>/apps/<app-name>
```

### 4. Register as External MCP Server

1. Go to the Databricks Agent Bricks UI
2. Navigate to "External Tools" → "MCP Servers"
3. Click "Add MCP Server"
4. Enter:
   - **Name**: Weather Service
   - **URL**: `https://<workspace-url>/apps/weather-mcp-server`
   - **Type**: HTTP/SSE
5. Test the connection

### 5. Create Agent Bricks Agent

1. Create a new Agent Bricks agent
2. In the "Tools" section, add the Weather Service MCP server
3. Set the system prompt (see below)
4. Save and test

## System Prompt

Here's a recommended system prompt for your agent:

```
You are a helpful weather assistant that provides accurate weather information 
and actionable recommendations.

You have access to three weather tools:
1. get_current_weather(location) - For real-time weather data
2. get_forecast(location, days) - For multi-day forecasts (up to 5 days)
3. predict_umbrella_needed(location, date) - For umbrella recommendations

Guidelines:
- Always validate locations before making API calls
- If a location cannot be resolved, ask for clarification
- For umbrella predictions, always explain the reasoning
- When API calls fail, acknowledge the failure and don't guess
- Temperature is in Fahrenheit
- Precipitation chance above 40% suggests bringing an umbrella
- Consider both precipitation chance AND conditions text
- For multi-day questions, use get_forecast with appropriate days parameter
- Be conversational but precise
- If asked about dates beyond 5 days, explain the API limitation

Location formats supported:
- City name: "London", "New York"
- City with country: "London,UK", "Tokyo,JP"
- US zip code: "10001,US"
- Latitude/longitude: "51.5074,-0.1278"

Example interactions:
- "What's the weather in Seattle?" → Use get_current_weather
- "Will it rain in Boston this week?" → Use get_forecast(Boston, 5)
- "Should I bring an umbrella tomorrow?" → Use predict_umbrella_needed
```

## Testing the Tools

Test the tools directly:

```python
import weather_broker

# Current weather
print(weather_broker.get_current_weather("San Francisco"))

# 3-day forecast
print(weather_broker.get_forecast("Chicago", 3))

# Test the full server locally
# python weather_mcp_server.py
```

## API Response Examples

### get_current_weather

```json
{
  "location": "San Francisco",
  "coordinates": {"lat": 37.7749, "lon": -122.4194},
  "temperature": 62.5,
  "feels_like": 60.8,
  "conditions": "partly cloudy",
  "humidity": 72,
  "wind_speed": 8.5,
  "pressure": 1013,
  "visibility": 10000,
  "timestamp": "2024-03-15T14:30:00"
}
```

### get_forecast

```json
{
  "location": "Chicago",
  "coordinates": {"lat": 41.8781, "lon": -87.6298},
  "forecast_days": 3,
  "forecasts": [
    {
      "date": "2024-03-16",
      "temp_high": 55.2,
      "temp_low": 38.6,
      "temp_avg": 46.9,
      "conditions": "light rain",
      "precipitation_chance": 65.0,
      "humidity_avg": 78.5
    }
  ]
}
```

### predict_umbrella_needed

```json
{
  "location": "Seattle",
  "date": "2024-03-16",
  "umbrella_needed": true,
  "confidence": "high",
  "reasoning": "Strong recommendation to bring an umbrella. There's a 75.0% chance of precipitation with light rain. It's very likely to rain. Note: Conditions explicitly mention 'light rain' - definitely bring an umbrella.",
  "precipitation_chance": 75.0,
  "conditions": "light rain",
  "temp_high": 52.3,
  "temp_low": 44.1,
  "humidity_avg": 82.5
}
```

## Troubleshooting

### "Could not resolve location"
- Check spelling of city name
- Try adding country code (e.g., "Paris,FR")
- Verify lat/lon format is correct

### "API Key Invalid"
- Verify the secret is base64 encoded: `echo -n "key" | base64`
- Check secret scope and key names match app.yaml
- Ensure OpenWeatherMap API key is activated (can take a few hours)

### "Forecast not available for date"
- OpenWeatherMap API only provides 5-day forecasts
- Request a date within the next 5 days

### App Deployment Issues
- Ensure all files are in the same directory
- Check requirements.txt includes all dependencies
- Verify app.yaml command points to correct entry file

## Extension Ideas

1. **get_travel_recommendation(location, date)** - Comprehensive travel advice
   - Best time to visit
   - Clothing recommendations
   - Activity suggestions based on weather

2. **compare_locations(location1, location2)** - Compare weather between cities
   - Temperature differences
   - Which has better weather
   - Travel recommendations

3. **get_severe_weather_alerts(location)** - Check for weather warnings
   - Storms, floods, extreme temps
   - Safety recommendations

4. **get_historical_weather(location, date)** - Past weather data
   - Requires OpenWeatherMap History API (paid)

## License

MIT License - Educational purposes

## Credits

Weather data provided by [OpenWeatherMap](https://openweathermap.org/)
