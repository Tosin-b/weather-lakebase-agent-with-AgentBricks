"""Test script for weather MCP server tools.

Run this to verify the weather broker is working before deploying as an app.

Usage:
    python test_weather.py
"""

import sys
from datetime import datetime, timedelta

try:
    import weather_broker
    print("✓ weather_broker module imported successfully\n")
except ImportError as e:
    print(f"✗ Failed to import weather_broker: {e}")
    sys.exit(1)


def test_current_weather():
    """Test get_current_weather function."""
    print("=" * 60)
    print("TEST 1: Get Current Weather")
    print("=" * 60)
    
    test_locations = [
        "San Francisco",
        "London,UK",
        "37.7749,-122.4194",  # SF coordinates
    ]
    
    for location in test_locations:
        try:
            print(f"\nTesting location: {location}")
            result = weather_broker.get_current_weather(location)
            print(f"  Location: {result['location']}")
            print(f"  Temperature: {result['temperature']}°F (feels like {result['feels_like']}°F)")
            print(f"  Conditions: {result['conditions']}")
            print(f"  Humidity: {result['humidity']}%")
            print(f"  Wind: {result['wind_speed']} mph")
            print(f"  ✓ SUCCESS")
        except Exception as e:
            print(f"  ✗ FAILED: {e}")


def test_forecast():
    """Test get_forecast function."""
    print("\n" + "=" * 60)
    print("TEST 2: Get Weather Forecast")
    print("=" * 60)
    
    try:
        location = "Chicago"
        days = 3
        print(f"\nTesting {days}-day forecast for: {location}")
        result = weather_broker.get_forecast(location, days)
        print(f"  Location: {result['location']}")
        print(f"  Forecast days: {result['forecast_days']}\n")
        
        for day in result['forecasts']:
            print(f"  Date: {day['date']}")
            print(f"    High: {day['temp_high']}°F, Low: {day['temp_low']}°F")
            print(f"    Conditions: {day['conditions']}")
            print(f"    Precipitation chance: {day['precipitation_chance']}%")
            print(f"    Humidity: {day['humidity_avg']}%")
            print()
        
        print(f"  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")


def test_umbrella_prediction():
    """Test umbrella prediction via the full MCP server tools."""
    print("\n" + "=" * 60)
    print("TEST 3: Umbrella Prediction Logic")
    print("=" * 60)
    
    try:
        # Import the MCP server module to test the tool
        from weather_mcp_server import predict_umbrella_needed
        
        location = "Seattle"
        # Test tomorrow
        tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
        
        print(f"\nTesting umbrella prediction for: {location} on {tomorrow}")
        result = predict_umbrella_needed(location, tomorrow)
        
        if 'status' in result and result['status'] == 'error':
            print(f"  ✗ FAILED: {result['message']}")
        else:
            print(f"  Location: {result['location']}")
            print(f"  Date: {result['date']}")
            print(f"  Umbrella needed: {result['umbrella_needed']}")
            print(f"  Confidence: {result['confidence']}")
            print(f"  Precipitation chance: {result['precipitation_chance']}%")
            print(f"  Conditions: {result['conditions']}")
            print(f"  Temperature range: {result['temp_low']}°F - {result['temp_high']}°F")
            print(f"\n  Reasoning: {result['reasoning']}")
            print(f"\n  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")


def main():
    print("\n" + "*" * 60)
    print(" Weather MCP Server - Test Suite")
    print("*" * 60 + "\n")
    
    # Check if secrets are configured
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        # Try to access the secret (this will fail if not configured)
        import weather_broker
        print("Checking secret configuration...")
        try:
            api_key = weather_broker._get_api_key()
            if api_key:
                print("✓ OpenWeatherMap API key found in secrets\n")
            else:
                print("✗ API key is empty\n")
        except Exception as e:
            print(f"✗ Failed to retrieve API key from secrets: {e}")
            print("  Make sure to run: databricks secrets put-secret weather openweather-api-key\n")
            return
    except Exception as e:
        print(f"✗ Databricks SDK initialization failed: {e}\n")
        return
    
    # Run tests
    test_current_weather()
    test_forecast()
    test_umbrella_prediction()
    
    print("\n" + "*" * 60)
    print(" Test Suite Complete")
    print("*" * 60 + "\n")


if __name__ == "__main__":
    main()
