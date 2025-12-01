# Live Trading Bot Guide

## Quick Start

### Step 1: Check Connection

First, verify your Bybit connection is working:

```bash
cd /Users/bryanlew/Document/AlgoCrypto/Backend/Connection
python Bybit_connection_test.py
```

**Expected Output:**
```
✅ SUCCESS: Connection to Bybit Demo Account is stable.
✅ Connection test PASSED - API keys are valid!
```

### Step 2: Start the Live Trading Bot

Once connection is verified, start the bot:

```bash
python trading_implementation.py --live
```

Or with custom parameters:

```bash
python trading_implementation.py --live Bollinger_Bands BTC/USDT 60
```

**Parameters:**
- `strategy_name`: Strategy to use (Bollinger_Bands, Moving_Average, RSI)
- `symbol`: Trading pair (default: BTC/USDT)
- `check_interval`: How often to check for signals in seconds (default: 60)

## What the Bot Does

1. **Connects to Bybit** - Tests connection and verifies API keys
2. **Fetches Market Data** - Gets latest OHLCV data every check interval
3. **Analyzes Strategy** - Runs your selected strategy on the data
4. **Monitors Signals** - Checks for entry/exit signals
5. **Executes Trades** - Automatically places orders when signals are detected
6. **Risk Management** - Enforces stop loss, take profit, and drawdown limits
7. **Logs Everything** - Shows all activity in real-time

## Bot Output Example

```
================================================================================
STARTING LIVE TRADING BOT
================================================================================
Press Ctrl+C to stop
================================================================================

[2025-11-16 17:30:00] Iteration #1
--------------------------------------------------------------------------------
📊 Portfolio Value: $99,960.50
📥 Fetching latest market data...
✓ Loaded 500 data points
🔍 Analyzing Bollinger_Bands strategy...
📊 Current Signal: 🟢 LONG (1)
💰 Current Price: $54,771.00
📈 Active Positions: 0/5
🎯 Executing signal: 🟢 LONG
✅ Trade executed successfully!
⏳ Waiting 60 seconds until next check...
```

## Features

### Connection Monitoring
- Tests connection on startup
- Shows balance, price, and positions
- Verifies API access

### Signal Monitoring
- Fetches latest market data every check interval
- Runs strategy analysis
- Detects signal changes
- Shows current signal status (LONG/SHORT/HOLD)

### Trade Execution
- Automatically executes trades when signals change
- Respects max concurrent trades limit
- Uses config.py risk management rules
- Monitors stop loss and take profit

### Risk Management
- Global drawdown limit (kill switch)
- Position sizing based on risk per trade
- Stop loss and take profit enforcement
- Max concurrent trades limit

## Stopping the Bot

Press `Ctrl+C` to stop the bot. You'll be asked if you want to close all open positions.

## Configuration

All risk management settings come from `config.py`:
- `TOTAL_PORTFOLIO_CAPITAL_USD` - Total capital
- `RISK_PER_TRADE_PERCENT` - Risk per trade (1%)
- `MAX_CONCURRENT_TRADES` - Max positions (5)
- `GLOBAL_DRAWDOWN_LIMIT_PERCENT` - Drawdown limit (20%)

## Troubleshooting

### Connection Failed
1. Check your `.env` file has correct API keys
2. Verify `BYBIT_ENVIRONMENT` is set correctly
3. Check API key permissions
4. Verify IP whitelist (if enabled)

### No Signals
- Strategy may not be generating signals
- Check that you have enough historical data
- Verify strategy parameters are correct

### Trades Not Executing
- Check if max concurrent trades limit reached
- Verify you have sufficient balance
- Check if global drawdown limit triggered
- Review logs for specific error messages

## Safety Features

1. **Test Mode First** - Always test with demo account first
2. **Kill Switch** - Stops all trading if drawdown exceeds limit
3. **Position Limits** - Maximum 5 concurrent trades
4. **Risk Per Trade** - Only 1% of capital at risk per trade
5. **Stop Loss** - Automatic stop loss on all positions
6. **Take Profit** - Automatic take profit targets

## Example Workflow

1. **Check Connection:**
   ```bash
   python Bybit_connection_test.py
   ```

2. **Start Bot (Demo):**
   ```bash
   python trading_implementation.py --live Bollinger_Bands BTC/USDT 60
   ```

3. **Monitor Output:**
   - Watch for connection status
   - Monitor signals and trades
   - Check portfolio value

4. **Stop Bot:**
   - Press `Ctrl+C`
   - Choose to close positions if needed

## Next Steps

1. ✅ Test connection with `Bybit_connection_test.py`
2. ✅ Start bot in demo mode
3. ✅ Monitor for a few hours/days
4. ✅ Review performance
5. ⚠️ Only then consider live trading (with caution!)

