# Frontend Integration Guide

## Overview

The trading bot can be controlled from your frontend website through a JSON configuration file (`trading_config.json`). This allows your frontend to dynamically update trading parameters without restarting the bot.

## Configuration File

Location: `/Users/bryanlew/Document/AlgoCrypto/Backend/Connection/trading_config.json`

### Structure

```json
{
  "timeframe": "1h",
  "strategy": "Bollinger_Bands",
  "symbol": "BTC/USDT",
  "check_interval": 60,
  "enabled": true,
  "last_updated": "2025-01-16T10:30:00"
}
```

### Parameters

- **`timeframe`**: OHLCV timeframe for trading signals
  - Options: `"1m"`, `"5m"`, `"15m"`, `"30m"`, `"1h"`, `"4h"`, `"1d"`, `"1w"`
  - Default: `"1h"`

- **`strategy`**: Trading strategy to use
  - Options: `"Bollinger_Bands"`, `"Moving_Average"`, `"RSI"`
  - Default: `"Bollinger_Bands"`

- **`symbol`**: Trading pair
  - Examples: `"BTC/USDT"`, `"ETH/USDT"`, `"BNB/USDT"`
  - Default: `"BTC/USDT"`

- **`check_interval`**: How often to check for signals (in seconds)
  - Recommended: 30-300 seconds
  - Default: `60`

- **`enabled`**: Enable/disable trading
  - `true`: Bot will trade normally
  - `false`: Bot will wait (no trades executed)
  - Default: `true`

- **`last_updated`**: Timestamp of last update (auto-set by bot)
  - Format: ISO 8601 (`"2025-01-16T10:30:00"`)

## Frontend Implementation

### Option 1: Direct File Write (Simple)

Your frontend can directly write to the JSON file:

```javascript
// Example: Update timeframe from frontend
async function updateTimeframe(newTimeframe) {
  const config = {
    timeframe: newTimeframe,
    strategy: "Bollinger_Bands",
    symbol: "BTC/USDT",
    check_interval: 60,
    enabled: true
  };
  
  // Send to your backend API endpoint
  await fetch('/api/trading-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
}
```

### Option 2: Backend API Endpoint (Recommended)

Create a backend API endpoint that updates the config file:

```python
# Example Flask/FastAPI endpoint
from Connection import config
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/trading-config', methods=['GET', 'POST'])
def trading_config():
    if request.method == 'GET':
        # Return current config
        return jsonify(config.load_trading_config())
    
    elif request.method == 'POST':
        # Update config
        new_config = request.json
        updated = config.update_trading_config(**new_config)
        return jsonify(updated)
```

### Option 3: REST API with Python

```python
# Example using Python requests library
import requests
import json

# Update timeframe
response = requests.post('http://your-backend/api/trading-config', json={
    'timeframe': '15m',
    'strategy': 'Moving_Average',
    'symbol': 'ETH/USDT'
})

print(response.json())
```

## How It Works

1. **Frontend Updates Config**: Your frontend writes to `trading_config.json`
2. **Bot Reloads Config**: The bot automatically reloads the config every 30 seconds
3. **Settings Applied**: New settings take effect on the next iteration
4. **No Restart Required**: The bot continues running with new settings

## Example Frontend UI

```html
<!-- Timeframe Selector -->
<select id="timeframe-selector" onchange="updateTimeframe(this.value)">
  <option value="1m">1 Minute</option>
  <option value="5m">5 Minutes</option>
  <option value="15m">15 Minutes</option>
  <option value="1h" selected>1 Hour</option>
  <option value="4h">4 Hours</option>
  <option value="1d">1 Day</option>
</select>

<!-- Strategy Selector -->
<select id="strategy-selector" onchange="updateStrategy(this.value)">
  <option value="Bollinger_Bands" selected>Bollinger Bands</option>
  <option value="Moving_Average">Moving Average</option>
  <option value="RSI">RSI</option>
</select>

<!-- Enable/Disable Toggle -->
<button onclick="toggleTrading()">Enable/Disable Trading</button>
```

## Safety Features

1. **Config Validation**: Invalid values fall back to defaults
2. **Graceful Updates**: Bot continues running during config updates
3. **Enable/Disable**: Can pause trading without stopping the bot
4. **Logging**: All config changes are logged

## Best Practices

1. **Validate Input**: Check timeframe and strategy values before updating
2. **User Feedback**: Show confirmation when settings are updated
3. **Error Handling**: Handle file write errors gracefully
4. **Read-Only Access**: Consider read-only access for some users
5. **Backup Config**: Keep backups of working configurations

## Testing

1. Start the bot:
   ```bash
   python trading_implementation.py --live
   ```

2. Update config file manually:
   ```bash
   # Edit trading_config.json
   # Change timeframe to "15m"
   ```

3. Watch bot logs - you should see:
   ```
   🔄 Timeframe updated from config: 1h → 15m
   ```

## Next Steps

1. Create your backend API endpoint
2. Implement frontend UI controls
3. Add authentication/authorization
4. Add real-time status updates
5. Implement config history/versioning

