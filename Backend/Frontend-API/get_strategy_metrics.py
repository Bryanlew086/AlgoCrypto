#!/usr/bin/env python3
"""
Get strategy metrics from backtest results
Returns JSON with ROI and Sharpe Ratio for each strategy
"""
import sys
import json
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Connection.analyzer import compare_strategies, load_data

def get_strategy_metrics(data_path=None):
    """
    Get metrics for all strategies
    
    Args:
        data_path: Optional path to data file. If None, uses default.
    
    Returns:
        dict with strategy metrics
    """
    try:
        # Use default data path if not provided
        if data_path is None:
            # Try to find default data file (4h timeframe)
            default_paths = [
                os.path.join('Backend', 'Data', 'bybit_btc_4h_20210101_20241231.csv'),
                os.path.join('..', 'Data', 'bybit_btc_4h_20210101_20241231.csv'),
                os.path.join('Data', 'bybit_btc_4h_20210101_20241231.csv'),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'bybit_btc_4h_20210101_20241231.csv')
            ]
            data_path = None
            for path in default_paths:
                if os.path.exists(path):
                    data_path = path
                    break
            
            if data_path is None:
                return {
                    'error': 'No data file found. Please provide data_path argument.'
                }
        
        # Load data and run strategies
        df = load_data(data_path)
        results = {}
        
        # Import strategy functions
        from Connection.analyzer import run_bb_strategy, run_ma_strategy, run_rsi_strategy
        
        # Run each strategy
        bb_metrics, _ = run_bb_strategy(df)
        if bb_metrics:
            results['Bollinger_Bands'] = {
                'roi': float(bb_metrics['roi']),
                'sharpe_ratio': float(bb_metrics['sharpe_ratio'])
            }
        
        ma_metrics, _ = run_ma_strategy(df)
        if ma_metrics:
            results['Moving_Average'] = {
                'roi': float(ma_metrics['roi']),
                'sharpe_ratio': float(ma_metrics['sharpe_ratio'])
            }
        
        rsi_metrics, _ = run_rsi_strategy(df)
        if rsi_metrics:
            results['RSI'] = {
                'roi': float(rsi_metrics['roi']),
                'sharpe_ratio': float(rsi_metrics['sharpe_ratio'])
            }
        
        return {
            'success': True,
            'results': results
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == '__main__':
    # Get data path from command line argument if provided
    data_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Get metrics
    result = get_strategy_metrics(data_path)
    
    # Output as JSON
    print(json.dumps(result, indent=2))

