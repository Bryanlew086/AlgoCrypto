#!/usr/bin/env python3
"""
Close all open positions and stop trading
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

def close_all_positions():
    """
    Close all open positions via Bybit API
    
    Returns:
        dict with success status and number of positions closed
    """
    try:
        # First, get all open positions
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query_string = "category=linear&settleCoin=USDT"
        
        sign_string = timestamp + config.API_KEY + recv_window + query_string
        signature = hmac.new(
            config.API_SECRET.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
        url = f"{base_url}/v5/position/list"
        
        headers = {
            'X-BAPI-API-KEY': config.API_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-SIGN-TYPE': '2',
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window,
        }
        
        params = {
            'category': 'linear',
            'settleCoin': 'USDT'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': f'Failed to fetch positions: HTTP {response.status_code}',
                'closed': 0
            }
        
        data = response.json()
        if data.get('retCode') != 0:
            return {
                'success': False,
                'error': data.get('retMsg', 'Failed to fetch positions'),
                'closed': 0
            }
        
        result = data.get('result', {})
        positions = result.get('list', [])
        
        # Filter to only positions with size > 0
        open_positions = [p for p in positions if float(p.get('size', 0)) > 0]
        
        if not open_positions:
            return {
                'success': True,
                'message': 'No open positions to close',
                'closed': 0
            }
        
        # Close each position
        closed_count = 0
        errors = []
        
        for position in open_positions:
            symbol = position.get('symbol', '')
            side = position.get('side', '')  # 'Buy' (long) or 'Sell' (short)
            size = position.get('size', '0')
            position_idx = position.get('positionIdx', '0')  # 0=one-way, 1=long hedge, 2=short hedge
            
            if float(size) == 0:
                continue
            
            # Determine close side (opposite of position side)
            close_side = 'Sell' if side == 'Buy' else 'Buy'
            
            # Place market order to close position
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            
            order_params = {
                'category': 'linear',
                'symbol': symbol,
                'side': close_side,
                'orderType': 'Market',
                'qty': size,
                'positionIdx': position_idx,
                'reduceOnly': True  # Important: This ensures we're closing, not opening
            }
            
            import json as json_lib
            json_body = json_lib.dumps(order_params, separators=(',', ':'))
            
            sign_string = timestamp + config.API_KEY + recv_window + json_body
            signature = hmac.new(
                config.API_SECRET.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            url = f"{base_url}/v5/order/create"
            headers = {
                'X-BAPI-API-KEY': config.API_KEY,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window,
                'Content-Type': 'application/json'
            }
            
            close_response = requests.post(url, headers=headers, data=json_body, timeout=10)
            
            if close_response.status_code == 200:
                close_data = close_response.json()
                if close_data.get('retCode') == 0:
                    closed_count += 1
                else:
                    errors.append(f"{symbol}: {close_data.get('retMsg', 'Unknown error')}")
            else:
                errors.append(f"{symbol}: HTTP {close_response.status_code}")
        
        # Also update trading_config.json to disable trading
        try:
            config_path = Path(__file__).parent.parent / 'Connection' / 'trading_config.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    trading_config = json.load(f)
                trading_config['enabled'] = False
                trading_config['last_updated'] = time.strftime('%Y-%m-%dT%H:%M:%S')
                with open(config_path, 'w') as f:
                    json.dump(trading_config, f, indent=2)
        except Exception as e:
            # Non-critical error
            pass
        
        if errors:
            return {
                'success': closed_count > 0,
                'message': f'Closed {closed_count} position(s). Some errors: {"; ".join(errors[:3])}',
                'closed': closed_count,
                'errors': errors
            }
        
        return {
            'success': True,
            'message': f'Successfully closed {closed_count} position(s)',
            'closed': closed_count
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'closed': 0
        }

if __name__ == '__main__':
    result = close_all_positions()
    print(json.dumps(result))

