# Frontend-API Python Scripts

This folder contains all Python scripts that are called directly from the Next.js frontend API routes.

## Files

1. **test_bybit_connection.py**
   - Called by: `nextjs-frontend/src/app/api/exchange/connect/route.ts`
   - Purpose: Tests Bybit API connection with provided credentials
   - Usage: `python3 test_bybit_connection.py <api_key> <api_secret> <environment>`

2. **get_strategy_metrics.py**
   - Called by: `nextjs-frontend/src/app/api/strategies/metrics/route.ts`
   - Purpose: Gets ROI and Sharpe Ratio for all strategies from latest backtest
   - Usage: `python3 get_strategy_metrics.py [data_path]`

3. **run_backtest.py**
   - Called by: `nextjs-frontend/src/app/api/strategies/backtest/route.ts`
   - Purpose: Runs backtest for a specific strategy and timeframe
   - Usage: `python3 run_backtest.py <strategy_name> <timeframe>`

## Note

These scripts import from `Connection.analyzer` and other backend modules, so they must be run from the Backend directory or have the Backend directory in the Python path.

