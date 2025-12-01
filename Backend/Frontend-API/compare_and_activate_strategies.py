#!/usr/bin/env python3
"""
Compare activated strategies and update trading_config.json with the best one
"""
import sys
import json
import os
from pathlib import Path

# Set matplotlib to non-interactive backend BEFORE importing analyzer
# This prevents plots from being displayed
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Connection.analyzer import compare_strategies, load_data

def get_data_file_path():
    """
    Get the default data file path for comparison
    Uses 4h data as default
    """
    possible_paths = [
        os.path.join('Backend', 'Data', 'bybit_btc_4h_20210101_20241231.csv'),
        os.path.join('..', 'Data', 'bybit_btc_4h_20210101_20241231.csv'),
        os.path.join('Data', 'bybit_btc_4h_20210101_20241231.csv'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'bybit_btc_4h_20210101_20241231.csv')
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None

def compare_and_activate(activated_strategies):
    """
    Compare activated strategies and return the best one
    
    Args:
        activated_strategies: List of strategy backend keys (e.g., ['Bollinger_Bands', 'RSI'])
    
    Returns:
        dict with success status and best strategy info
    """
    try:
        # Get data file
        data_path = get_data_file_path()
        if not data_path:
            return {
                'success': False,
                'error': 'Data file not found for strategy comparison'
            }
        
        # Run comparison for all strategies
        # Suppress plot display
        import io
        import contextlib
        import matplotlib.pyplot as plt
        
        # Capture print statements and suppress plot display
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            results = compare_strategies(data_path)
            # Close any open figures to prevent display
            plt.close('all')
        
        if not results or 'results' not in results:
            return {
                'success': False,
                'error': 'Failed to run strategy comparison'
            }
        
        # Filter to only activated strategies
        activated_results = {}
        for strategy_key in activated_strategies:
            # Map frontend keys to backend keys
            key_mapping = {
                'Bollinger_Bands': 'Bollinger_Bands',
                'RSI': 'RSI',
                'Moving_Average': 'Moving_Average'
            }
            backend_key = key_mapping.get(strategy_key, strategy_key)
            
            if backend_key in results['results']:
                activated_results[backend_key] = results['results'][backend_key]
        
        if not activated_results:
            return {
                'success': False,
                'error': 'No activated strategies found in comparison results'
            }
        
        # Calculate weighted scores for activated strategies only
        scores = {}
        for name, metrics in activated_results.items():
            # Normalize metrics (higher is better, except drawdown)
            roi_values = [r['roi'] for r in activated_results.values()]
            sharpe_values = [r['sharpe_ratio'] for r in activated_results.values()]
            pf_values = [r['profit_factor'] for r in activated_results.values()]
            dd_values = [r['max_drawdown'] for r in activated_results.values()]
            
            roi_score = (metrics['roi'] - min(roi_values)) / (max(roi_values) - min(roi_values) + 1e-10)
            sharpe_score = (metrics['sharpe_ratio'] - min(sharpe_values)) / (max(sharpe_values) - min(sharpe_values) + 1e-10)
            pf_score = (metrics['profit_factor'] - min(pf_values)) / (max(pf_values) - min(pf_values) + 1e-10)
            
            # Drawdown (lower is better, so invert)
            dd_max = max(dd_values)
            dd_min = min(dd_values)
            dd_score = 1 - ((metrics['max_drawdown'] - dd_min) / (dd_max - dd_min + 1e-10))
            
            # Weighted combination (same as analyzer.py)
            total_score = (
                0.30 * roi_score +
                0.30 * sharpe_score +
                0.20 * pf_score +
                0.20 * dd_score
            )
            
            scores[name] = {
                'strategy': metrics['strategy_name'],
                'total_score': total_score,
                'roi': metrics['roi'],
                'sharpe_ratio': metrics['sharpe_ratio'],
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown']
            }
        
        # Find best strategy
        if not scores:
            return {
                'success': False,
                'error': 'Could not calculate scores for activated strategies'
            }
        
        best_strategy_key = max(scores.items(), key=lambda x: x[1]['total_score'])[0]
        best_strategy_info = scores[best_strategy_key]
        
        # Update trading_config.json
        config_path = Path(__file__).parent.parent / 'Connection' / 'trading_config.json'
        if not config_path.exists():
            return {
                'success': False,
                'error': f'trading_config.json not found at {config_path}'
            }
        
        # Read current config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Update strategy
        config['strategy'] = best_strategy_key
        config['last_updated'] = __import__('datetime').datetime.now().isoformat()
        
        # Write updated config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return {
            'success': True,
            'bestStrategy': best_strategy_info['strategy'],
            'bestStrategyKey': best_strategy_key,
            'scores': {k: {
                'strategy': v['strategy'],
                'total_score': round(v['total_score'], 4),
                'roi': round(v['roi'] * 100, 2),
                'sharpe_ratio': round(v['sharpe_ratio'], 4)
            } for k, v in scores.items()}
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
    if len(sys.argv) < 2:
        print(json.dumps({
            'success': False,
            'error': 'Usage: python compare_and_activate_strategies.py <strategy1> <strategy2> ...'
        }))
        sys.exit(1)
    
    activated_strategies = sys.argv[1:]
    
    # Run comparison and activation
    result = compare_and_activate(activated_strategies)
    
    # Output as JSON
    print(json.dumps(result, indent=2))

