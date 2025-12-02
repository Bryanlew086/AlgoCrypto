#!/usr/bin/env python3
"""
Get closed trade history from Bybit (for Performance page)
"""
import sys
import os
import json
from pathlib import Path
import requests
import hmac
import hashlib
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Connection import config

def get_trade_history(limit=50):
    """
    Get closed trade history from Bybit
    
    Args:
        limit: Number of trades to fetch (default: 50)
    
    Returns:
        dict with success status and trades list
    """
    try:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query_string = f"category=linear&limit={limit}"
        
        sign_string = timestamp + config.API_KEY + recv_window + query_string
        signature = hmac.new(
            config.API_SECRET.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
        url = f"{base_url}/v5/position/closed-pnl"
        
        headers = {
            'X-BAPI-API-KEY': config.API_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-SIGN-TYPE': '2',
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window,
        }
        
        params = {
            'category': 'linear',
            'limit': limit
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('retCode') == 0:
                result = data.get('result', {})
                trades = result.get('list', [])
                
                # Load trade log to get strategy for each trade
                trade_log_path = Path(__file__).parent / 'trade_log.json'
                trade_log = {'trades': []}
                strategy_map = {}  # orderId -> strategy
                
                try:
                    if trade_log_path.exists():
                        with open(trade_log_path, 'r') as f:
                            trade_log = json.load(f)
                        # Create mapping from orderId to strategy
                        for log_entry in trade_log.get('trades', []):
                            order_id = log_entry.get('orderId', '')
                            if order_id:
                                strategy_map[order_id] = log_entry.get('strategy', 'Unknown')
                except Exception as e:
                    # If trade log doesn't exist or can't be read, fall back to current config
                    pass
                
                # Format trades for frontend
                formatted_trades = []
                for trade in trades:
                    order_id = trade.get('orderId', '')
                    
                    # Get strategy from trade log (historical) or fall back to current config
                    strategy = 'Unknown'
                    if order_id and order_id in strategy_map:
                        # Use strategy from trade log (when trade was executed)
                        strategy_backend = strategy_map[order_id]
                    else:
                        # Fallback to current strategy from config (for trades not in log)
                        try:
                            config_path = Path(__file__).parent.parent / 'Connection' / 'trading_config.json'
                            if config_path.exists():
                                with open(config_path, 'r') as f:
                                    trading_config = json.load(f)
                                    strategy_backend = trading_config.get('strategy', 'Unknown')
                            else:
                                strategy_backend = 'Unknown'
                        except:
                            strategy_backend = 'Unknown'
                    
                    # Map backend strategy names to frontend names
                    strategy_name_map = {
                        'Bollinger_Bands': 'Bollinger Bands',
                        'RSI': 'RSI',
                        'Moving_Average': 'Moving Average'
                    }
                    strategy = strategy_name_map.get(strategy_backend, strategy_backend)
                    
                    formatted_trades.append({
                        'id': order_id,
                        'symbol': trade.get('symbol', ''),
                        'side': trade.get('side', ''),  # 'Buy' or 'Sell'
                        'qty': trade.get('qty', '0'),
                        'entryPrice': trade.get('avgEntryPrice', '0'),
                        'exitPrice': trade.get('avgExitPrice', '0'),
                        'closedPnl': trade.get('closedPnl', '0'),
                        'createdTime': trade.get('createdTime', ''),
                        'updatedTime': trade.get('updatedTime', ''),
                        'strategy': strategy
                    })
                
                # Sort by updateTime (most recent first)
                formatted_trades.sort(key=lambda x: int(x.get('updatedTime', 0)), reverse=True)
                
                return {
                    'success': True,
                    'trades': formatted_trades[:limit]
                }
            else:
                return {
                    'success': False,
                    'error': data.get('retMsg', 'Unknown error'),
                    'trades': []
                }
        else:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}',
                'trades': []
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'trades': []
        }

if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    result = get_trade_history(limit)
    print(json.dumps(result))

