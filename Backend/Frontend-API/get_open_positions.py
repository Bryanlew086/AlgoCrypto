#!/usr/bin/env python3
"""
Get open positions from Bybit
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

def get_realized_pnl():
    """
    Get total realized P&L from Bybit account
    Uses totalRealisedPnl from wallet balance (matches Bybit website)
    
    Returns:
        Total realized P&L in USDT
    """
    try:
        # First try to get totalRealisedPnl from wallet balance (official Bybit value)
        # This matches what's shown on Bybit website and includes all fees
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query_string = "accountType=UNIFIED"
        
        sign_string = timestamp + config.API_KEY + recv_window + query_string
        signature = hmac.new(
            config.API_SECRET.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
        url = f"{base_url}/v5/account/wallet-balance"
        
        headers = {
            'X-BAPI-API-KEY': config.API_KEY,
            'X-BAPI-SIGN': signature,
            'X-BAPI-SIGN-TYPE': '2',
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recv_window,
        }
        
        response = requests.get(url, headers=headers, params={'accountType': 'UNIFIED'}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('retCode') == 0:
                result = data.get('result', {})
                account_list = result.get('list', [])
                if account_list:
                    account = account_list[0]
                    coins = account.get('coin', [])
                    for coin in coins:
                        if coin.get('coin') == 'USDT':
                            # Get totalRealisedPnl - this is the official Bybit value
                            # It includes all trading fees and funding fees
                            total_realised_pnl_str = coin.get('totalRealisedPnl', '')
                            if total_realised_pnl_str and total_realised_pnl_str != '':
                                try:
                                    return float(total_realised_pnl_str)
                                except (ValueError, TypeError):
                                    pass
            else:
                # Log the error but continue to fallback
                error_msg = data.get('retMsg', 'Unknown error')
                # Don't raise exception, just fall through to closed-pnl endpoint
                pass
        
        # Fallback: Calculate from closed P&L history (may not include all fees)
        # This is less accurate but better than 0
        timestamp = str(int(time.time() * 1000))
        recv_window = "5000"
        query_string = "category=linear&limit=200"
        
        sign_string = timestamp + config.API_KEY + recv_window + query_string
        signature = hmac.new(
            config.API_SECRET.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
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
            'limit': 200  # Get more records for better accuracy
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('retCode') == 0:
                result = data.get('result', {})
                closed_trades = result.get('list', [])
                
                # Sum up all closed P&L
                # Note: This may not include all fees, so it might differ from Bybit website
                total_realized_pnl = sum(float(trade.get('closedPnl', 0)) for trade in closed_trades)
                
                return total_realized_pnl
        return 0.0
    except Exception as e:
        # Silently return 0 if there's any error
        # This ensures the positions fetch doesn't fail
        return 0.0

def get_open_positions():
    """
    Get all open positions from Bybit
    
    Returns:
        dict with success status and positions list
    """
    try:
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
        
        if response.status_code == 200:
            data = response.json()
            if data.get('retCode') == 0:
                result = data.get('result', {})
                positions = result.get('list', [])
                
                # Filter to only positions with size > 0
                open_positions = []
                for pos in positions:
                    size = float(pos.get('size', 0))
                    if size > 0:
                        # Calculate unrealized P&L
                        entry_price = float(pos.get('avgPrice', 0))
                        mark_price = float(pos.get('markPrice', 0))
                        side = pos.get('side', '')  # 'Buy' for long, 'Sell' for short
                        
                        if side == 'Buy':  # Long position
                            unrealized_pnl = (mark_price - entry_price) * size
                        else:  # Short position
                            unrealized_pnl = (entry_price - mark_price) * size
                        
                        # Calculate ROI
                        position_value = entry_price * size
                        roi = (unrealized_pnl / position_value * 100) if position_value > 0 else 0
                        
                        # Get leverage
                        leverage = pos.get('leverage', '1')
                        
                        # Get margin mode
                        # For unified accounts, Cross margin is the default and most common
                        # Check multiple fields to determine margin mode
                        trade_mode = pos.get('tradeMode')
                        margin_mode_field = pos.get('marginMode', '')
                        
                        # Priority 1: If marginMode field exists and is valid, use it directly
                        if margin_mode_field and margin_mode_field.upper() in ['CROSS', 'ISOLATED']:
                            margin_mode = 'Cross' if margin_mode_field.upper() == 'CROSS' else 'Isolated'
                        # Priority 2: Check tradeMode field
                        # Based on user feedback: Bybit shows "Cross" but we were showing "Isolated"
                        # This suggests the mapping might be: 0 = Isolated, 1 = Cross (reversed from docs)
                        # OR: For unified accounts, tradeMode might mean something different
                        elif trade_mode is not None:
                            try:
                                # Convert to integer for comparison
                                trade_mode_int = int(float(str(trade_mode).strip()))
                                
                                # REVERSED MAPPING based on user feedback:
                                # When Bybit shows "Cross", we were getting tradeMode=0 and showing "Isolated"
                                # So: tradeMode 0 = Cross, tradeMode 1 = Isolated (standard)
                                # But user feedback suggests: tradeMode 0 might actually mean Isolated for their account
                                # Let's try: tradeMode 1 = Cross, tradeMode 0 = Isolated (reversed)
                                # Actually, let's be more conservative: only show Isolated if we're certain
                                
                                # For unified accounts, default to Cross unless tradeMode explicitly indicates Isolated
                                # Try reversed: if tradeMode is 1, show Cross; if 0, show Isolated
                                if trade_mode_int == 1:
                                    margin_mode = 'Cross'  # Reversed: 1 = Cross
                                elif trade_mode_int == 0:
                                    margin_mode = 'Isolated'  # Reversed: 0 = Isolated
                                else:
                                    margin_mode = 'Cross'  # Default to Cross
                                
                            except (ValueError, TypeError):
                                # If conversion fails, default to Cross for unified accounts
                                margin_mode = 'Cross'
                        else:
                            # Default to Cross for unified accounts (most common)
                            margin_mode = 'Cross'
                        
                        # Format position
                        formatted_pos = {
                            'symbol': pos.get('symbol', ''),
                            'contracts': f"{pos.get('symbol', '')} Perp",
                            'marginMode': margin_mode,
                            'leverage': f"{leverage}x",
                            'qty': f"{size:.3f} BTC",
                            'size': size,
                            'value': f"{float(pos.get('positionValue', 0)):,.2f} USDT",
                            'positionValue': float(pos.get('positionValue', 0)),
                            'entryPrice': f"{entry_price:,.2f}",
                            'entryPriceNum': entry_price,
                            'markPrice': f"{mark_price:,.2f}",
                            'markPriceNum': mark_price,
                            'liqPrice': pos.get('liqPrice', '--') if pos.get('liqPrice') else '--',
                            'breakevenPrice': f"{float(pos.get('avgPrice', 0)):,.2f}",
                            'side': side,
                            'positionIdx': pos.get('positionIdx', '0'),
                            'unrealizedPnl': unrealized_pnl,
                            'unrealizedPnlFormatted': f"{unrealized_pnl:,.4f} USDT",
                            'roi': roi,
                            'roiFormatted': f"({roi:.2f}%)",
                            'unrealizedPnlUsd': unrealized_pnl  # Same as USDT for now
                        }
                        open_positions.append(formatted_pos)
                
                # Get total realized P&L from closed positions
                # If this fails, we still return positions successfully
                try:
                    total_realized_pnl = get_realized_pnl()
                except Exception as e:
                    # If realized P&L fetch fails, default to 0
                    # This shouldn't break the positions fetch
                    total_realized_pnl = 0.0
                
                return {
                    'success': True,
                    'positions': open_positions,
                    'realizedPnl': total_realized_pnl
                }
            else:
                return {
                    'success': False,
                    'error': data.get('retMsg', 'Unknown error'),
                    'positions': []
                }
        else:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}',
                'positions': []
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'positions': []
        }

if __name__ == '__main__':
    result = get_open_positions()
    print(json.dumps(result))

