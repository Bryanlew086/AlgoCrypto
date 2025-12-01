# Trading Implementation Guide

This guide explains how to use the strategy analyzer and trading implementation to compare strategies and execute trades.

## Overview

1. **analyzer.py** - Compares all 3 strategies (Bollinger Bands, Moving Average, RSI) and shows which performs best
2. **trading_implementation.py** - Executes trades based on strategy signals

## Files Created

### 1. `analyzer.py`
Complete strategy performance analyzer that:
- Loads historical data
- Runs all 3 strategies (BB, MA, RSI)
- Calculates performance metrics (ROI, Sharpe, Sortino, Calmar, Profit Factor, Max Drawdown, Trade Count)
- Compares strategies side-by-side
- Identifies the best performing strategy
- Generates visualizations

### 2. `trading_implementation.py`
Trading bot that:
- Executes trades based on strategy signals
- Manages positions and risk
- Supports both demo and live trading
- Includes stop loss and take profit
- Can run in test mode (simulation) or live mode

### 3. `Strategy/bb_strategy.py`
Extracted Bollinger Bands strategy functions from the notebook for use in analyzer

## Usage

### Step 1: Compare Strategies

Run the analyzer to see which strategy performs best:

```bash
cd /Users/bryanlew/Document/AlgoCrypto/Backend/Connection
python analyzer.py
```

Or specify a data file:

```bash
python analyzer.py /path/to/your/data.csv
```

**Output:**
- Strategy comparison table
- Best strategy by different metrics (ROI, Sharpe, Profit Factor, etc.)
- Overall ranking with weighted scores
- Visualizations saved to `Backend/Results/strategy_comparison.png`

### Step 2: Test Trading Implementation

Test the trading bot in simulation mode (no real orders):

```bash
python trading_implementation.py Bollinger_Bands
```

Available strategies:
- `Bollinger_Bands`
- `Moving_Average`
- `RSI`

**Output:**
- Trading simulation results
- Initial vs final balance
- Total return
- Trade log

### Step 3: Live Trading (USE WITH CAUTION!)

⚠️ **WARNING: Live trading uses real money!**

1. Make sure your `.env` file is configured correctly:
   ```bash
   BYBIT_ENVIRONMENT=DEMO  # or LIVE for real trading
   BYBIT_API_KEY_DEMO=your_key
   BYBIT_API_SECRET_DEMO=your_secret
   ```

2. Edit `trading_implementation.py` and set `test_mode=False`:
   ```python
   results = run_strategy_trading(
       strategy_name=strategy_name,
       data_path=default_data_path,
       symbol='BTC/USDT',
       use_demo=True,  # Set to False for live trading
       test_mode=False  # ⚠️ Set to False for real orders
   )
   ```

3. Run the script:
   ```bash
   python trading_implementation.py Bollinger_Bands
   ```

## Strategy Comparison Metrics

The analyzer compares strategies using:

1. **ROI (%)** - Total return on investment
2. **Sharpe Ratio** - Risk-adjusted return
3. **Sortino Ratio** - Downside risk-adjusted return
4. **Calmar Ratio** - Return vs max drawdown
5. **Profit Factor** - Gross profit / gross loss
6. **Max Drawdown (%)** - Largest peak-to-trough decline
7. **Total Trades** - Number of trades executed
8. **Avg Return** - Average return per trade
9. **Std Dev** - Volatility of returns

## Best Strategy Selection

The analyzer uses a weighted scoring system:
- 30% ROI
- 30% Sharpe Ratio
- 20% Profit Factor
- 20% Max Drawdown (lower is better)

The strategy with the highest total score is recommended.

## Risk Management

The trading bot includes:
- **Position Sizing**: Maximum 10% of balance per trade
- **Stop Loss**: 2% default
- **Take Profit**: 4% default

You can adjust these in `TradingBot.__init__()`:
```python
self.max_position_size = 0.1  # 10% of balance
self.stop_loss_pct = 0.02     # 2% stop loss
self.take_profit_pct = 0.04   # 4% take profit
```

## Example Workflow

1. **Analyze Strategies**:
   ```bash
   python analyzer.py
   ```
   Output: "🏆 RECOMMENDED STRATEGY: Bollinger Bands"

2. **Test the Recommended Strategy**:
   ```bash
   python trading_implementation.py Bollinger_Bands
   ```
   Review the simulation results

3. **If satisfied, go live** (with caution):
   - Set `test_mode=False` in the script
   - Set `use_demo=True` for demo account first
   - Monitor closely
   - Start with small amounts

## Troubleshooting

### Import Errors
If you get import errors, make sure you're running from the correct directory:
```bash
cd /Users/bryanlew/Document/AlgoCrypto/Backend/Connection
```

### Data File Not Found
Make sure your data file exists at:
```
/Users/bryanlew/Document/AlgoCrypto/Backend/Data/bybit_btc_1h_20210101_20241231.csv
```

Or specify a different path:
```bash
python analyzer.py /path/to/your/data.csv
```

### Strategy Not Found
Available strategy names:
- `Bollinger_Bands` (or `Bollinger Bands`)
- `Moving_Average` (or `Moving Average`)
- `RSI`

## Next Steps

1. ✅ Compare all strategies using `analyzer.py`
2. ✅ Test trading implementation in simulation mode
3. ✅ Review results and adjust risk parameters if needed
4. ⚠️ Test with demo account before going live
5. ⚠️ Start with small amounts when going live
6. 📊 Monitor performance and adjust as needed

## Files Structure

```
Backend/
├── Connection/
│   ├── analyzer.py              # Strategy comparison tool
│   ├── trading_implementation.py # Trading bot
│   ├── config.py                 # API configuration
│   └── TRADING_GUIDE.md          # This file
├── Strategy/
│   ├── bb_strategy.py           # Bollinger Bands functions
│   ├── MA.py                     # Moving Average strategy
│   └── rsi.ipynb                 # RSI strategy (notebook)
└── Results/
    └── strategy_comparison.png   # Generated visualizations
```

## Support

If you encounter issues:
1. Check the logs for error messages
2. Verify your `.env` file is configured correctly
3. Make sure data files exist and are in the correct format
4. Test with demo account first before going live

