#!/usr/bin/env python3
"""
Get recent orders/trades from Bybit
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

def get_recent_orders(limit=50):
    """
    Get recent orders from Bybit
    
    Args:
        limit: Number of recent orders to fetch (default: 50)
    
    Returns:
        dict with success status and orders list
    """
    try:
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        
        # Build query string - increase limit to get more orders
        query_string = f"category=linear&limit={limit}"
        
        # Signature for GET: timestamp + api_key + recv_window + query_string
        sign_string = timestamp + config.API_KEY + recv_window + query_string
        signature = hmac.new(
            config.API_SECRET.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
        url = f"{base_url}/v5/order/history"
        
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
            # Note: Bybit API doesn't support filtering by orderStatus in the request
            # We'll filter filled orders in the code below
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('retCode') == 0:
                result = data.get('result', {})
                orders = result.get('list', [])
                
                # Load trade log to get strategy for each order
                trade_log_path = Path(__file__).parent / 'trade_log.json'
                trade_log = {'trades': []}
                strategy_map_by_order = {}  # orderId -> strategy
                
                try:
                    if trade_log_path.exists():
                        with open(trade_log_path, 'r') as f:
                            trade_log = json.load(f)
                        # Create mapping from orderId to strategy
                        for log_entry in trade_log.get('trades', []):
                            order_id = log_entry.get('orderId', '')
                            if order_id:
                                strategy_map_by_order[order_id] = log_entry.get('strategy', 'Unknown')
                except Exception as e:
                    # If trade log doesn't exist or can't be read, fall back to current config
                    pass
                
                # Format orders for frontend
                formatted_orders = []
                all_order_statuses = set()  # Debug: track all order statuses
                
                # Debug: print raw orders to help diagnose
                if not orders:
                    return {
                        'success': True,
                        'orders': [],
                        'debug': {
                            'total_orders': 0,
                            'message': 'No orders found in API response. Have you placed any orders yet?'
                        }
                    }
                
                for order in orders:
                    order_status = order.get('orderStatus', '')
                    all_order_statuses.add(order_status)  # Track status for debugging
                    
                    # Include filled orders (opened positions) - these are the successful orders
                    # Check for various possible status values
                    # Bybit API might use: 'Filled', 'PartiallyFilled', 'Filled', 'Done', etc.
                    if order_status in ['Filled', 'PartiallyFilled', 'Done', 'FullyFilled']:
                        order_id = order.get('orderId', '')
                        
                        # Get strategy from trade log (historical) or fall back to current config
                        strategy_backend = 'Unknown'
                        if order_id and order_id in strategy_map_by_order:
                            # Use strategy from trade log (when order was placed)
                            strategy_backend = strategy_map_by_order[order_id]
                        else:
                            # Fallback to current strategy from config (for orders not in log)
                            try:
                                config_path = Path(__file__).parent.parent / 'Connection' / 'trading_config.json'
                                if config_path.exists():
                                    with open(config_path, 'r') as f:
                                        trading_config = json.load(f)
                                        strategy_backend = trading_config.get('strategy', 'Unknown')
                            except:
                                strategy_backend = 'Unknown'
                        
                        # Map backend strategy names to frontend names
                        strategy_name_map = {
                            'Bollinger_Bands': 'Bollinger Bands',
                            'RSI': 'RSI',
                            'Moving_Average': 'Moving Average'
                        }
                        strategy_display = strategy_name_map.get(strategy_backend, strategy_backend)
                        
                        formatted_orders.append({
                            'orderId': order_id,
                            'symbol': order.get('symbol', ''),
                            'side': order.get('side', ''),  # 'Buy' or 'Sell'
                            'orderType': order.get('orderType', ''),
                            'qty': str(order.get('qty', '0') or '0'),
                            'price': str(order.get('price', '0') or '0'),
                            'avgPrice': str(order.get('avgPrice', '0') or '0'),
                            'orderStatus': order_status,
                            'cumExecQty': str(order.get('cumExecQty', '0') or '0'),
                            'cumExecValue': str(order.get('cumExecValue', '0') or '0'),
                            'createTime': str(order.get('createTime', '') or ''),
                            'updateTime': str(order.get('updateTime', '') or ''),
                            'strategy': strategy_display  # Add strategy name
                        })
                
                # Sort by updateTime (most recent first)
                # Handle empty strings and None values safely
                def safe_int(value, default=0):
                    """Safely convert value to int, handling empty strings and None"""
                    if value is None or value == '':
                        return default
                    try:
                        return int(float(str(value).strip()))
                    except (ValueError, TypeError):
                        return default
                
                formatted_orders.sort(key=lambda x: safe_int(x.get('updateTime', 0)), reverse=True)
                
                result = {
                    'success': True,
                    'orders': formatted_orders[:limit]
                }
                
                # Add debug info if no filled orders but other orders exist
                if not formatted_orders and orders:
                    result['debug'] = {
                        'total_orders': len(orders),
                        'order_statuses': list(all_order_statuses),
                        'message': f'Found {len(orders)} orders but none are Filled. Statuses found: {list(all_order_statuses)}'
                    }
                
                return result
            else:
                return {
                    'success': False,
                    'error': data.get('retMsg', 'Unknown error'),
                    'orders': []
                }
        else:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}',
                'orders': []
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'orders': []
        }

if __name__ == '__main__':
    try:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else 50
    except (ValueError, IndexError):
        limit = 50  # Default to 50 if invalid or missing
    
    result = get_recent_orders(limit)
    print(json.dumps(result))
