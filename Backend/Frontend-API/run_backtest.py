#!/usr/bin/env python3
"""
Run backtest for a specific strategy and timeframe
Returns JSON with ROI and Sharpe Ratio
"""
import sys
import json
import os
import numpy as np
import math

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Connection.analyzer import load_data

def safe_float(value, default=0.0):
    """
    Convert value to float, handling NaN and None
    
    Args:
        value: Value to convert
        default: Default value if NaN or None
    
    Returns:
        float value or default
    """
    if value is None:
        return default
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except (ValueError, TypeError):
        return default

def get_data_file_path(timeframe):
    """
    Get the data file path based on timeframe
    
    Args:
        timeframe: '1h', '4h', or '1d'
    
    Returns:
        Path to the data file
    """
    # Map timeframe to data file
    timeframe_map = {
        '1h': 'bybit_btc_1h_20210101_20241231.csv',
        '4h': 'bybit_btc_4h_20210101_20241231.csv',
        '1d': 'bybit_btc_1d_20210101_20241231.csv'
    }
    
    filename = timeframe_map.get(timeframe)
    if not filename:
        return None
    
    # Try different paths
    possible_paths = [
        os.path.join('Backend', 'Data', filename),
        os.path.join('..', 'Data', filename),
        os.path.join('Data', filename),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', filename)
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None

def run_backtest(strategy_name, timeframe):
    """
    Run backtest for a specific strategy and timeframe
    
    Args:
        strategy_name: 'Bollinger_Bands', 'Moving_Average', or 'RSI'
        timeframe: '1h', '4h', or '1d'
    
    Returns:
        dict with backtest results
    """
    try:
        # Get data file path based on timeframe
        data_path = get_data_file_path(timeframe)
        
        if not data_path:
            return {
                'success': False,
                'error': f'Data file not found for timeframe: {timeframe}'
            }
        
        # Load data
        df = load_data(data_path)
        
        # Import strategy functions
        from Connection.analyzer import run_bb_strategy, run_ma_strategy, run_rsi_strategy
        
        # Map strategy name to function
        strategy_map = {
            'Bollinger_Bands': run_bb_strategy,
            'Moving_Average': run_ma_strategy,
            'RSI': run_rsi_strategy
        }
        
        strategy_func = strategy_map.get(strategy_name)
        if not strategy_func:
            return {
                'success': False,
                'error': f'Unknown strategy: {strategy_name}'
            }
        
        # Run strategy
        metrics, strategy_df = strategy_func(df)
        
        if not metrics:
            return {
                'success': False,
                'error': f'Failed to run strategy: {strategy_name}'
            }
        
        # Prepare visualization data (sample equity curve)
        equity_curve_data = []
        if 'cumulative_pnl' in metrics and metrics['cumulative_pnl'] is not None:
            cumu_pnl = metrics['cumulative_pnl']
            # Sample data points (take every Nth point to reduce data size)
            sample_rate = max(1, len(cumu_pnl) // 100)  # Max 100 points
            sampled_pnl = cumu_pnl.iloc[::sample_rate]
            
            # Convert to list of {date, value} objects
            for idx, value in sampled_pnl.items():
                safe_value = safe_float(value, 0.0)
                equity_curve_data.append({
                    'date': str(idx) if hasattr(idx, '__str__') else f'Point {len(equity_curve_data)}',
                    'value': safe_value * 100  # Convert to percentage
                })
        
        return {
            'success': True,
            'strategy': strategy_name,
            'timeframe': timeframe,
            'results': {
                'roi': safe_float(metrics.get('roi', 0), 0.0),
                'sharpe_ratio': safe_float(metrics.get('sharpe_ratio', 0), 0.0),
                'total_trades': int(metrics.get('total_trades', 0)),
                'max_drawdown': safe_float(metrics.get('max_drawdown', 0), 0.0),
                'profit_factor': safe_float(metrics.get('profit_factor', 0), 0.0),
                'sortino_ratio': safe_float(metrics.get('sortino_ratio', 0), 0.0),
                'calmar_ratio': safe_float(metrics.get('calmar_ratio', 0), 0.0)
            },
            'visualization': {
                'equity_curve': equity_curve_data
            }
        }
        
    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }

if __name__ == '__main__':
    # Get arguments from command line
    if len(sys.argv) < 3:
        print(json.dumps({
            'success': False,
            'error': 'Usage: python run_backtest.py <strategy_name> <timeframe>'
        }))
        sys.exit(1)
    
    strategy_name = sys.argv[1]
    timeframe = sys.argv[2]
    
    # Run backtest
    result = run_backtest(strategy_name, timeframe)
    
    # Custom JSON encoder to handle NaN and Infinity
    def clean_for_json(obj):
        """Recursively clean NaN and Infinity values from dict/list"""
        if isinstance(obj, dict):
            return {k: clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_for_json(item) for item in obj]
        elif isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return 0.0
            return obj
        elif isinstance(obj, (np.integer, np.floating)):
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return val
        return obj
    
    # Clean result before JSON encoding
    cleaned_result = clean_for_json(result)
    
    # Output as JSON
    print(json.dumps(cleaned_result, indent=2))

