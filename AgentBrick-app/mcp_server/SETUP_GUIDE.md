# Weather MCP Server - Complete Setup Guide

Step-by-step guide to deploy your weather MCP server and connect it to an Agent Bricks agent.

## Prerequisites

- Databricks workspace with Agent Bricks enabled
- Databricks CLI installed and configured
- OpenWeatherMap API account (free tier)

---

## Step 1: Get OpenWeatherMap API Key

1. **Create Account**
   - Go to https://openweathermap.org/api
   - Click "Sign Up" and create a free account
   - Verify your email

2. **Generate API Key**
   - Log in to your account
   - Go to "My API Keys" in your profile
   - Copy your default API key (or create a new one)
   - **Save this key** - you'll need it in the next step
   
   ⚠️ **Note**: New API keys can take up to 2 hours to activate!

3. **Verify API Key** (optional but recommended)
   ```bash
   curl "https://api.openweathermap.org/data/2.5/weather?q=London&appid=YOUR_API_KEY"
   ```
   
   If you get weather data back, your key is active!

---

## Step 2: Store API Key as Databricks Secret

1. **Create Secret Scope**
   ```bash
   databricks secrets create-scope weather
   ```
   
   If the scope already exists, that's fine - you'll get an error but can continue.

2. **Store API Key (Base64 Encoded)**
   ```bash
   # Linux/Mac
   echo -n "YOUR_API_KEY_HERE" | base64 | databricks secrets put-secret weather openweather-api-key
   
   # Windows PowerShell
   $bytes = [System.Text.Encoding]::UTF8.GetBytes("YOUR_API_KEY_HERE")
   $base64 = [Convert]::ToBase64String($bytes)
   databricks secrets put-secret weather openweather-api-key --string-value $base64
   ```
   
   **Replace `YOUR_API_KEY_HERE` with your actual API key!**

3. **Verify Secret**
   ```bash
   databricks secrets list-secrets weather
   ```
   
   You should see `openweather-api-key` in the list.

---

## Step 3: Test Locally (Optional)

Before deploying, test that everything works:

1. **Navigate to the mcp_server directory**
   ```bash
   cd homework\ 3/mcp_server
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run test script**
   ```bash
   python test_weather.py
   ```
   
   You should see:
   - ✓ Current weather for multiple locations
   - ✓ 3-day forecast
   - ✓ Umbrella prediction

4. **Run server locally** (optional)
   ```bash
   python weather_mcp_server.py
   ```
   
   The MCP server will start on http://localhost:8000

---

## Step 4: Deploy as Databricks App

1. **Navigate to mcp_server directory**
   ```bash
   cd "homework 3/mcp_server"
   ```

2. **Create the Databricks App**
   ```bash
   databricks apps create weather-mcp-server
   ```
   
   This creates an empty app named "weather-mcp-server".

3. **Deploy the app**
   ```bash
   databricks apps deploy weather-mcp-server --source-code-path .
   ```
   
   This will:
   - Upload all files (weather_mcp_server.py, weather_broker.py, requirements.txt, app.yaml)
   - Install dependencies
   - Start the server
   
   ⏳ This takes 2-5 minutes on first deploy.

4. **Get the app URL**
   ```bash
   databricks apps get weather-mcp-server
   ```
   
   Look for the `url` field in the output. It will be something like:
   ```
   https://<workspace-url>/apps/weather-mcp-server
   ```
   
   **Copy this URL** - you'll need it for the next step!

5. **Check app status**
   ```bash
   databricks apps list
   ```
   
   Status should show "RUNNING". If it shows "FAILED", check logs:
   ```bash
   databricks apps logs weather-mcp-server
   ```

---

## Step 5: Register as External MCP Server

1. **Open Databricks Workspace**
   - Navigate to your Databricks workspace in a browser

2. **Go to Agent Bricks**
   - Click on "Machine Learning" in the left sidebar
   - Select "Agent Bricks" (or "AI Playground")

3. **Add External MCP Server**
   - Go to "External Tools" or "MCP Servers" section
   - Click "Add MCP Server" or "+" button

4. **Configure MCP Server**
   - **Name**: `Weather Service`
   - **URL**: `https://<workspace-url>/apps/weather-mcp-server`
   - **Type**: `HTTP/SSE` or `Streamable HTTP`
   - **Description**: "Weather information and forecasts"

5. **Test Connection**
   - Click "Test Connection" or "Verify"
   - Should see ✓ Connected
   - Should show 3 available tools:
     - get_current_weather
     - get_forecast
     - predict_umbrella_needed

---

## Step 6: Create Agent Bricks Agent

1. **Create New Agent**
   - In Agent Bricks UI, click "Create Agent" or "New Agent"
   - Name: `Weather Assistant`

2. **Add MCP Server as Tool**
   - In the "Tools" section, click "Add Tool"
   - Select "Weather Service" from the list
   - All 3 tools should be added automatically

3. **Set System Prompt**
   
   Copy and paste this prompt:
   
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

4. **Save Agent**
   - Click "Save" or "Create"

---

## Step 7: Test Your Agent

1. **Open Chat Interface**
   - Click "Test" or "Chat" in your agent

2. **Try These Test Queries**
   
   ```
   What's the weather like in San Francisco?
   ```
   
   Expected: Current weather with temperature, conditions, humidity, wind
   
   ```
   Give me a 5-day forecast for Chicago
   ```
   
   Expected: 5-day forecast with daily highs/lows, precipitation chances
   
   ```
   Should I bring an umbrella in Seattle tomorrow?
   ```
   
   Expected: Yes/No recommendation with reasoning and precipitation chance
   
   ```
   Compare the weather in London and Tokyo
   ```
   
   Expected: Two get_current_weather calls and comparison

3. **Verify Tool Usage**
   - In the chat response, you should see:
     - Tool calls being made (e.g., "Calling get_current_weather")
     - Actual API responses
     - Agent's interpretation and response

---

## Troubleshooting

### Issue: "Could not resolve location"

**Solution**: 
- Check spelling
- Try adding country code (e.g., "Paris,FR")
- Use coordinates if city name is ambiguous

### Issue: "API Key Invalid" or 401 errors

**Solution**:
1. Verify your OpenWeatherMap API key is active (check on their website)
2. Check the secret was base64 encoded:
   ```bash
   echo -n "YOUR_KEY" | base64
   ```
3. Verify secret exists:
   ```bash
   databricks secrets list-secrets weather
   ```
4. Redeploy the app:
   ```bash
   databricks apps deploy weather-mcp-server --source-code-path .
   ```

### Issue: App shows "FAILED" status

**Solution**:
1. Check logs:
   ```bash
   databricks apps logs weather-mcp-server
   ```
2. Common causes:
   - Missing dependencies in requirements.txt
   - Syntax error in Python files
   - Secret scope not accessible
3. Fix the issue and redeploy

### Issue: Agent can't find tools

**Solution**:
1. Verify app is running:
   ```bash
   databricks apps get weather-mcp-server
   ```
2. Re-test MCP server connection in Agent Bricks UI
3. Check the app URL is correct
4. Restart the agent

### Issue: "Forecast not available for date"

**Solution**:
- OpenWeatherMap only provides 5-day forecasts
- Ask for dates within the next 5 days
- Agent should handle this gracefully with the system prompt

---

## Verification Checklist

Before marking complete, verify:

- [ ] OpenWeatherMap API key obtained and active
- [ ] Secret stored in Databricks (scope: `weather`, key: `openweather-api-key`)
- [ ] App deployed and status is "RUNNING"
- [ ] MCP server registered in Agent Bricks UI
- [ ] Agent created with system prompt
- [ ] All 3 tools (get_current_weather, get_forecast, predict_umbrella_needed) visible
- [ ] Tested at least 3 different queries successfully
- [ ] Agent provides reasoning for umbrella predictions
- [ ] Agent handles location errors gracefully

---

## Next Steps

1. **Customize System Prompt**
   - Add personality to your agent
   - Add specific use cases (travel planning, event planning, etc.)
   - Add guardrails for your specific needs

2. **Extend Functionality**
   - Add `get_travel_recommendation` tool
   - Add `compare_locations` tool
   - Add `get_severe_weather_alerts` tool

3. **Production Considerations**
   - Set up monitoring for API rate limits
   - Add caching to reduce API calls
   - Implement retry logic for transient failures
   - Add structured logging

4. **Share Your Agent**
   - Share with team members
   - Create demo notebook
   - Document common use cases

---

## Quick Reference Commands

```bash
# Deploy/Update app
databricks apps deploy weather-mcp-server --source-code-path .

# Check app status
databricks apps get weather-mcp-server

# View app logs
databricks apps logs weather-mcp-server

# List all apps
databricks apps list

# Delete app (if needed)
databricks apps delete weather-mcp-server

# Manage secrets
databricks secrets list-scopes
databricks secrets list-secrets weather
databricks secrets delete-secret weather openweather-api-key
```

---

## Support

If you run into issues:
1. Check the troubleshooting section above
2. Review the README.md for detailed API documentation
3. Run test_weather.py to verify broker functionality
4. Check Databricks app logs for errors
5. Verify OpenWeatherMap API key status on their website

---

**Congratulations!** 🎉 Your Weather MCP Server is now live!
