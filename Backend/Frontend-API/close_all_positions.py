#!/usr/bin/env python3
"""
Close all open positions on Bybit
"""
import sys
import os
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Connection import config

def close_all_positions():
    """
    Close all open positions on Bybit
    
    Returns:
        dict with success status and number of positions closed
    """
    try:
        import requests
        import hmac
        import hashlib
        import time
        
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
        
        # Get open positions
        response = requests.get(url, headers=headers, params={'category': 'linear', 'settleCoin': 'USDT'}, timeout=10)
        
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
        
        if not positions:
            return {
                'success': True,
                'message': 'No open positions to close',
                'closed': 0
            }
        
        # Close each position
        closed_count = 0
        errors = []
        
        for position in positions:
            symbol = position.get('symbol', '')
            side = position.get('side', '')  # 'Buy' (long) or 'Sell' (short)
            size = position.get('size', '0')
            
            if float(size) == 0:
                continue  # Skip positions with zero size
            
            # Determine close side (opposite of position side)
            close_side = 'Sell' if side == 'Buy' else 'Buy'
            
            # Get position index
            position_idx = position.get('positionIdx', '0')
            
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
        
        return {
            'success': True,
            'closed': closed_count,
            'total': len([p for p in positions if float(p.get('size', '0')) > 0]),
            'errors': errors if errors else None
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'closed': 0
        }

if __name__ == '__main__':
    result = close_all_positions()
    print(json.dumps(result, indent=2))

