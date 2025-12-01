"""
Trading Implementation
Complete trading system: executes trades, monitors signals, and runs live trading bot
Supports both simulation (backtesting) and live trading (demo/live)
"""
import ccxt
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from Connection import config
from Connection.analyzer import run_bb_strategy, run_ma_strategy, run_rsi_strategy
from Connection.Bybit_connection_test import test_demo_connection

log = logging.getLogger(__name__)

class TradingBot:
    """
    Trading bot that executes trades based on strategy signals
    """
    
    def __init__(self, exchange=None, symbol: str = 'BTC/USDT', use_demo: bool = True):
        """
        Initialize trading bot
        
        Args:
            exchange: CCXT exchange instance (if None, will create from config)
            symbol: Trading pair (e.g., 'BTC/USDT')
            use_demo: Use demo trading account
        """
        self.symbol = symbol
        self.use_demo = use_demo
        
        if exchange is None:
            # Initialize real Bybit exchange connection
            if config.ENVIRONMENT == 'DEMO':
                # Demo trading uses api-demo.bybit.com
                self.exchange = ccxt.bybit({
                    'apiKey': config.API_KEY,
                    'secret': config.API_SECRET,
                    'sandbox': False,
                    'options': {
                        'defaultType': 'linear',
                    },
                    'enableRateLimit': True,
                })
                # Override URLs to use demo domain
                self.exchange.urls = {
                    'api': {
                        'public': 'https://api-demo.bybit.com',
                        'private': 'https://api-demo.bybit.com',
                        'rest': 'https://api-demo.bybit.com',
                    },
                    'www': 'https://www.bybit.com',
                    'doc': ['https://bybit-exchange.github.io/docs/v5/demo'],
                }
            else:
                # Live trading uses regular api.bybit.com
                self.exchange = ccxt.bybit({
                    'apiKey': config.API_KEY,
                    'secret': config.API_SECRET,
                    'sandbox': False,
                    'options': {
                        'defaultType': 'linear',
                    },
                    'enableRateLimit': True,
                })
        else:
            self.exchange = exchange
        
        # Position tracking - supports hedge mode (both long and short simultaneously)
        # Structure: {symbol: {'long': position_dict or None, 'short': position_dict or None}}
        # In one-way mode: only one of 'long' or 'short' can be non-None
        # In hedge mode: both 'long' and 'short' can be non-None simultaneously
        self.positions = {}  # Track multiple positions with hedge mode support
        self.initial_portfolio_value = config.TOTAL_PORTFOLIO_CAPITAL_USD
        self.peak_portfolio_value = config.TOTAL_PORTFOLIO_CAPITAL_USD
        
        # Risk management from config.py
        self.total_capital = config.TOTAL_PORTFOLIO_CAPITAL_USD
        self.risk_per_trade = config.RISK_PER_TRADE_PERCENT
        self.max_concurrent_trades = config.MAX_CONCURRENT_TRADES
        self.global_drawdown_limit = config.GLOBAL_DRAWDOWN_LIMIT_PERCENT
        
        # Stop loss and take profit percentages (can be adjusted per strategy)
        self.stop_loss_pct = 0.02  # 2% stop loss (default)
        self.take_profit_pct = 0.04  # 4% take profit (default)
        
        log.info(f"✅ Trading bot initialized for {symbol}")
        log.info(f"   Mode: {'DEMO' if use_demo else 'LIVE'}")
        log.info(f"   Account Type: UNIFIED (Unified Trading Account)")
        log.info(f"   Market Type: USDT Perpetual (linear)")
        log.info(f"   Symbol Format: {symbol.replace('/', '')} (Unified Account format)")
        log.info(f"   Total Capital: ${self.total_capital:,.2f}")
        log.info(f"   Risk per Trade: {self.risk_per_trade*100:.2f}%")
        log.info(f"   Max Concurrent Trades: {self.max_concurrent_trades}")
        log.info(f"   Global Drawdown Limit: {self.global_drawdown_limit*100:.2f}%")
    
    def get_balance(self) -> Dict:
        """Get account balance"""
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            error_str = str(e)
            # Check if it's the demo trading error (10032)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                # Use direct API call for balance (for demo trading)
                balance = self._fetch_balance_direct_api()
                if balance is not None:
                    return balance
            log.error(f"❌ Error fetching balance: {e}")
            return None
    
    def _fetch_balance_direct_api(self) -> Optional[Dict]:
        """
        Fetch balance using direct Bybit API call (for demo trading compatibility)
        """
        def safe_float(value, default=0.0):
            """Safely convert value to float, handling empty strings and None"""
            if value is None or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        try:
            import requests
            import hmac
            import hashlib
            import time
            
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            query_string = "accountType=UNIFIED"
            sign_string = timestamp + config.API_KEY + recv_window + query_string
            signature = hmac.new(
                config.API_SECRET.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Use demo API endpoint
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
                    result = data.get('result', {}).get('list', [{}])
                    if not result:
                        log.warning("No account data in balance response")
                        return None
                    
                    account_data = result[0]
                    coin_list = account_data.get('coin', [])
                    
                    # Convert to CCXT format
                    balance_dict = {
                        'info': data,
                        'total': {},
                        'free': {},
                        'used': {}
                    }
                    
                    for coin in coin_list:
                        coin_name = coin.get('coin', '')
                        if not coin_name:
                            continue  # Skip coins without a name
                        
                        wallet_balance = safe_float(coin.get('walletBalance', 0), 0.0)
                        locked = safe_float(coin.get('locked', 0), 0.0)
                        
                        # For Unified Account, available balance for trading can be:
                        # 1. availableBalance (if present)
                        # 2. equity (account equity, available for trading)
                        # 3. walletBalance - locked (calculated available)
                        # 4. availableToWithdraw (fallback, but might be 0 for unified accounts)
                        available_balance = safe_float(coin.get('availableBalance', 0), 0.0)
                        if available_balance == 0:
                            # Try equity (for unified accounts, equity is often the available balance)
                            equity = safe_float(coin.get('equity', 0), 0.0)
                            if equity > 0:
                                available_balance = equity
                                log.info(f"   Using equity as available balance: {equity}")
                            else:
                                # Calculate: walletBalance - locked
                                available_balance = wallet_balance - locked
                                log.info(f"   Calculated available balance: {wallet_balance} - {locked} = {available_balance}")
                                if available_balance == 0:
                                    # Last resort: availableToWithdraw
                                    available_balance = safe_float(coin.get('availableToWithdraw', 0), 0.0)
                        
                        balance_dict['total'][coin_name] = wallet_balance
                        balance_dict['free'][coin_name] = available_balance
                        # For unified accounts, used balance = locked (not walletBalance - availableBalance)
                        balance_dict['used'][coin_name] = locked
                        
                        # Store equity value (total portfolio value including positions and unrealized P&L)
                        equity = safe_float(coin.get('equity', 0), 0.0)
                        if 'equity' not in balance_dict:
                            balance_dict['equity'] = {}
                        balance_dict['equity'][coin_name] = equity
                        
                        # Log detailed balance info for debugging
                        if coin_name == 'USDT':
                            log.info(f"   Balance details for {coin_name}:")
                            log.info(f"     walletBalance: {coin.get('walletBalance', 'N/A')}")
                            log.info(f"     availableBalance: {coin.get('availableBalance', 'N/A')}")
                            log.info(f"     availableToWithdraw: {coin.get('availableToWithdraw', 'N/A')}")
                            log.info(f"     equity: {coin.get('equity', 'N/A')} (Total Portfolio Value)")
                            log.info(f"     locked: {coin.get('locked', 'N/A')}")
                    
                    return balance_dict
                else:
                    log.error(f"Direct API balance error: {data.get('retMsg')}")
                    return None
            else:
                log.error(f"HTTP {response.status_code}")
                return None
                
        except Exception as e:
            log.error(f"Error in direct API balance call: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_available_balance(self) -> Optional[float]:
        """
        Get available balance (free balance that can be used for trading)
        
        Returns:
            Available USDT balance or None if error
        """
        try:
            balance = self.get_balance()
            if balance is None:
                return None
            
            # Get available balance (free)
            # Try different possible keys
            if isinstance(balance, dict):
                if 'USDT' in balance:
                    usdt_balance = balance['USDT']
                    if isinstance(usdt_balance, dict):
                        available = usdt_balance.get('free', 0) or usdt_balance.get('available', 0)
                    else:
                        available = usdt_balance
                elif 'free' in balance and 'USDT' in balance.get('free', {}):
                    available = balance['free']['USDT']
                else:
                    return None
            else:
                return None
            
            return float(available) if available else None
        except Exception as e:
            log.error(f"Error getting available balance: {e}")
            return None
    
    def get_current_price(self) -> Optional[float]:
        """Get current market price"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker['last']
        except Exception as e:
            error_str = str(e)
            # Check if it's the demo trading error (10032) or use public API for price
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                # Use direct API call for price (public endpoint works for market data)
                price = self._fetch_price_direct_api()
                if price is not None:
                    return price
            log.error(f"❌ Error fetching price: {e}")
            return None
    
    def _fetch_price_direct_api(self) -> Optional[float]:
        """
        Fetch current price using direct Bybit API call (public endpoint works for demo trading)
        """
        try:
            import requests
            
            # Convert symbol to Bybit format (BTC/USDT -> BTCUSDT)
            symbol_bybit = self.symbol.replace('/', '')
            
            # Use public API endpoint (works for both demo and live)
            url = "https://api.bybit.com/v5/market/tickers"
            params = {
                'category': 'linear',
                'symbol': symbol_bybit
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    ticker_list = result.get('list', [])
                    if ticker_list:
                        last_price = float(ticker_list[0].get('lastPrice', 0))
                        return last_price
                    else:
                        log.error("No ticker data in response")
                        return None
                else:
                    log.error(f"Direct API price error: {data.get('retMsg')}")
                    return None
            else:
                log.error(f"HTTP {response.status_code}")
                return None
                
        except Exception as e:
            log.error(f"Error in direct API price call: {e}")
            return None
    
    def calculate_position_size(self, entry_price: float, stop_loss_price: float) -> float:
        """
        Calculate position size using config.py risk management rules
        
        Args:
            entry_price: Entry price for the trade
            stop_loss_price: Stop loss price
            
        Returns:
            Position size in base currency (e.g., BTC)
        """
        # Use the position sizing function from config.py
        position_size = config.calculate_position_size(
            symbol=self.symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price
        )
        
        return position_size
    
    def check_global_drawdown(self, current_portfolio_value: float) -> bool:
        """
        Check if global drawdown limit has been exceeded (kill switch)
        
        Args:
            current_portfolio_value: Current total portfolio value
            
        Returns:
            True if drawdown limit exceeded (should stop trading)
        """
        # Update peak value
        if current_portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = current_portfolio_value
        
        # Calculate drawdown from peak
        drawdown = (self.peak_portfolio_value - current_portfolio_value) / self.peak_portfolio_value
        
        if drawdown >= self.global_drawdown_limit:
            log.error(f"🛑 GLOBAL DRAWDOWN LIMIT EXCEEDED!")
            log.error(f"   Current Value: ${current_portfolio_value:,.2f}")
            log.error(f"   Peak Value: ${self.peak_portfolio_value:,.2f}")
            log.error(f"   Drawdown: {drawdown*100:.2f}% (Limit: {self.global_drawdown_limit*100:.2f}%)")
            log.error(f"   ⚠️  ALL TRADING STOPPED - KILL SWITCH ACTIVATED")
            return True
        
        return False
    
    def can_open_new_position(self, hedge_mode: bool = False) -> bool:
        """
        Check if we can open a new position (respecting MAX_CONCURRENT_TRADES)
        
        Args:
            hedge_mode: If True, counts both long and short positions separately
            
        Returns:
            True if we can open a new position
        """
        if hedge_mode:
            # In hedge mode, count both long and short positions separately
            active_count = 0
            for symbol_positions in self.positions.values():
                if isinstance(symbol_positions, dict):
                    if symbol_positions.get('long') is not None:
                        active_count += 1
                    if symbol_positions.get('short') is not None:
                        active_count += 1
                elif symbol_positions is not None:
                    # Legacy format (one-way mode)
                    active_count += 1
        else:
            # One-way mode: count each symbol as one position
            active_count = len([p for p in self.positions.values() if p is not None])
        
        if active_count >= self.max_concurrent_trades:
            log.warning(f"⚠️  Cannot open new position: {active_count}/{self.max_concurrent_trades} positions already open")
            return False
        
        return True
    
    def place_market_order(self, side: str, amount: float, params: Dict = None, position_idx: str = None) -> Optional[Dict]:
        """
        Place a market order
        
        Args:
            side: 'buy' or 'sell'
            amount: Amount in base currency
            params: Additional order parameters
            position_idx: Position index for hedge mode ('1' for long, '2' for short, '0' for one-way)
            
        Returns:
            Order result or None if failed
        """
        try:
            log.info(f"📝 Placing {side.upper()} order: {amount:.6f} {self.symbol}")
            
            # Add positionIdx to params if provided
            order_params = params or {}
            if position_idx is not None:
                order_params['positionIdx'] = position_idx
            
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=amount,
                params=order_params
            )
            
            log.info(f"✅ Order placed: {order.get('id', 'N/A')}")
            log.info(f"   Status: {order.get('status', 'N/A')}")
            log.info(f"   Filled: {order.get('filled', 0)}")
            
            return order
            
        except Exception as e:
            error_str = str(e)
            # Check if it's the demo trading error (10032)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                log.info(f"ℹ️  CCXT create_market_order doesn't work with demo trading, using direct API call...")
                # Use direct API call for placing orders (for demo trading)
                order = self._place_order_direct_api(side, amount, params, position_idx=position_idx)
                if order is not None:
                    return order
            log.error(f"❌ Error placing order: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _set_leverage(self, symbol_bybit: str, leverage: int) -> bool:
        """
        Set leverage for a symbol (required for unified accounts before placing orders)
        
        Args:
            symbol_bybit: Symbol in Bybit format (e.g., 'BTCUSDT')
            leverage: Leverage value (e.g., 10 for 10x)
            
        Returns:
            True if leverage set successfully, False otherwise
        """
        try:
            import requests
            import hmac
            import hashlib
            import time
            import json
            
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            
            # Build request parameters
            leverage_params = {
                'category': 'linear',
                'symbol': symbol_bybit,
                'buyLeverage': str(leverage),
                'sellLeverage': str(leverage)
            }
            
            json_body = json.dumps(leverage_params, separators=(',', ':'))
            
            # Signature for POST: timestamp + api_key + recv_window + json_body
            sign_string = timestamp + config.API_KEY + recv_window + json_body
            signature = hmac.new(
                config.API_SECRET.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
            url = f"{base_url}/v5/position/set-leverage"
            
            headers = {
                'X-BAPI-API-KEY': config.API_KEY,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window,
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, data=json_body, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    log.info(f"   ✅ Leverage set to {leverage}x for {symbol_bybit}")
                    return True
                else:
                    # Leverage might already be set, or there's an error
                    error_msg = data.get('retMsg', 'Unknown error')
                    ret_code = data.get('retCode')
                    if ret_code == 110043:  # Leverage not modified
                        log.info(f"   ℹ️  Leverage already set to {leverage}x for {symbol_bybit}")
                        return True
                    else:
                        log.warning(f"   ⚠️  Could not set leverage: {error_msg} (retCode: {ret_code})")
                        log.warning(f"   Proceeding with order placement anyway...")
                        return False
            else:
                log.warning(f"   ⚠️  HTTP {response.status_code} when setting leverage")
                log.warning(f"   Proceeding with order placement anyway...")
                return False
                
        except Exception as e:
            log.warning(f"   ⚠️  Error setting leverage: {e}")
            log.warning(f"   Proceeding with order placement anyway...")
            return False
    
    def _get_instrument_info(self, symbol_bybit: str) -> Optional[Dict]:
        """
        Fetch instrument info to get lotSizeFilter (qtyStep) and minOrderQty
        
        Args:
            symbol_bybit: Symbol in Bybit format (e.g., "BTCUSDT")
            
        Returns:
            Instrument info dict or None if failed
        """
        try:
            import requests
            
            base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
            url = f"{base_url}/v5/market/instruments-info"
            params = {
                'category': 'linear',
                'symbol': symbol_bybit
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    instruments = result.get('list', [])
                    if instruments:
                        return instruments[0]  # Return first (and usually only) instrument
            return None
            
        except Exception as e:
            log.warning(f"   Could not fetch instrument info: {e}")
            return None
    
    def _set_margin_mode(self, margin_mode: str = 'Cross') -> bool:
        """
        Set margin mode for unified account (Cross or Isolated)
        
        Args:
            margin_mode: 'Cross' or 'Isolated' (default: 'Cross')
            
        Returns:
            True if margin mode set successfully, False otherwise
        """
        try:
            import requests
            import hmac
            import hashlib
            import time
            import json
            
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            
            # Build request parameters
            margin_params = {
                'setMarginMode': margin_mode  # 'Cross' or 'Isolated'
            }
            
            json_body = json.dumps(margin_params, separators=(',', ':'))
            
            # Signature for POST: timestamp + api_key + recv_window + json_body
            sign_string = timestamp + config.API_KEY + recv_window + json_body
            signature = hmac.new(
                config.API_SECRET.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
            url = f"{base_url}/v5/account/set-margin-mode"
            
            headers = {
                'X-BAPI-API-KEY': config.API_KEY,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window,
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, data=json_body, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    log.info(f"   ✅ Margin mode set to {margin_mode} for unified account")
                    return True
                else:
                    # Margin mode might already be set, or there's an error
                    error_msg = data.get('retMsg', 'Unknown error')
                    ret_code = data.get('retCode')
                    if ret_code == 110043:  # Margin mode not modified
                        log.info(f"   ℹ️  Margin mode already set to {margin_mode}")
                        return True
                    else:
                        log.warning(f"   ⚠️  Could not set margin mode: {error_msg} (retCode: {ret_code})")
                        log.warning(f"   Proceeding with order placement anyway...")
                        return False
            else:
                log.warning(f"   ⚠️  HTTP {response.status_code} when setting margin mode")
                log.warning(f"   Proceeding with order placement anyway...")
                return False
                
        except Exception as e:
            log.warning(f"   ⚠️  Error setting margin mode: {e}")
            log.warning(f"   Proceeding with order placement anyway...")
            return False
    
    def _place_order_direct_api(self, side: str, amount: float, params: Dict = None, position_idx: str = None) -> Optional[Dict]:
        """
        Place order using direct Bybit API call (for demo trading compatibility)
        
        Args:
            side: 'buy' or 'sell'
            amount: Amount in base currency
            params: Additional order parameters
            position_idx: Position index for hedge mode ('1' for long, '2' for short, '0' for one-way)
                         If None, will determine from hedge mode setting
            
        Returns:
            Order result or None if failed
        """
        # Load hedge mode setting to determine positionIdx if not provided
        if position_idx is None:
            trading_config = config.load_trading_config()
            hedge_mode = trading_config.get('hedge_mode', False)
            if hedge_mode:
                # In hedge mode, determine positionIdx based on side
                # positionIdx: 1 = long position, 2 = short position
                position_idx = '1' if side.lower() == 'buy' else '2'
            else:
                # One-way mode
                position_idx = '0'
        try:
            import requests
            import hmac
            import hashlib
            import time
            
            # Convert symbol to Bybit format for Unified Account
            # BTC/USDT -> BTCUSDT (no slash, required for unified account)
            symbol_bybit = self.symbol.replace('/', '')
            
            log.info(f"   🔧 Symbol conversion: {self.symbol} -> {symbol_bybit} (Unified Account format)")
            
            # Map side to Bybit format
            bybit_side = 'Buy' if side.lower() == 'buy' else 'Sell'
            
            # Calculate quantity for linear contracts
            # For Bybit linear USDT perpetual contracts:
            # - qty parameter should be the number of contracts (USD value)
            # - 1 contract = 1 USD worth of the underlying asset
            # - But we need to check if Bybit expects it in a different format
            try:
                current_price = self.get_current_price()
                if current_price is None:
                    log.error("Cannot get current price for quantity calculation")
                    return None
                
                # Convert amount (in base currency) to contracts (USD value)
                # For linear: quantity = amount_in_base_currency * price
                quantity_usd = amount * current_price
                
                log.info(f"   📊 Quantity Calculation:")
                log.info(f"     Amount (BTC): {amount:.8f}")
                log.info(f"     Current Price: ${current_price:,.2f}")
                log.info(f"     Quantity (USD): ${quantity_usd:,.2f}")
                
                # Check available balance before placing order
                available_balance = self.get_available_balance()
                if available_balance is not None and available_balance > 0:
                    log.info(f"   ✅ Available balance: ${available_balance:,.2f} USDT")
                    # For linear contracts with unified account, margin requirement is typically very low (0.5-2%)
                    # But we'll use a conservative 5% estimate for safety
                    required_margin = quantity_usd * 0.05  # 5% margin requirement estimate
                    if available_balance < required_margin:
                        log.warning(f"   ⚠️  Available balance (${available_balance:,.2f}) may be insufficient")
                        log.warning(f"   Estimated margin needed: ${required_margin:,.2f}")
                        log.warning(f"   Position value: ${quantity_usd:,.2f}")
                    else:
                        log.info(f"   ✅ Sufficient balance: ${available_balance:,.2f} >= ${required_margin:,.2f} (margin estimate)")
                else:
                    log.warning(f"   ⚠️  Could not fetch available balance or balance is 0")
                    log.warning(f"   Proceeding with order placement anyway (API will reject if insufficient)")
                    
                # Also fetch balance directly from API to double-check
                # Try to get the raw API response to see all available fields
                try:
                    import requests
                    import hmac
                    import hashlib
                    import time
                    
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
                            result = data.get('result', {}).get('list', [])
                            if result:
                                account = result[0]
                                coins = account.get('coin', [])
                                for coin in coins:
                                    if coin.get('coin') == 'USDT':
                                        log.info(f"   Raw API balance fields for USDT:")
                                        log.info(f"     walletBalance: {coin.get('walletBalance', 'N/A')}")
                                        log.info(f"     availableBalance: {coin.get('availableBalance', 'N/A')}")
                                        log.info(f"     availableToWithdraw: {coin.get('availableToWithdraw', 'N/A')}")
                                        log.info(f"     equity: {coin.get('equity', 'N/A')}")
                                        log.info(f"     usdValue: {coin.get('usdValue', 'N/A')}")
                                        log.info(f"     locked: {coin.get('locked', 'N/A')}")
                                        break
                except Exception as e:
                    log.warning(f"   Could not fetch detailed balance from direct API: {e}")
                
                # Bybit linear contracts: For USDT perpetuals, qty should be in base currency (BTC)
                # NOT in contracts! The qty parameter expects the BTC amount directly.
                # Based on user's manual trade: 0.01 BTC works, so we send BTC amount as string
                
                # Fetch instrument info to get lotSizeFilter (qtyStep) and minOrderQty
                instrument_info = self._get_instrument_info(symbol_bybit)
                qty_step = 0.001  # Default step size (0.001 BTC)
                min_qty = 0.001   # Default minimum (0.001 BTC)
                
                if instrument_info:
                    lot_size_filter = instrument_info.get('lotSizeFilter', {})
                    qty_step = float(lot_size_filter.get('qtyStep', '0.001'))
                    min_qty = float(lot_size_filter.get('minOrderQty', '0.001'))
                    log.info(f"   📏 Instrument Info:")
                    log.info(f"     Min Order Qty: {min_qty} BTC")
                    log.info(f"     Qty Step: {qty_step} BTC")
                
                # Round to nearest valid step size
                # For example, if qtyStep = 0.001, then 0.52447131 -> 0.524
                if qty_step > 0:
                    btc_amount_rounded = round(amount / qty_step) * qty_step
                else:
                    btc_amount_rounded = round(amount, 8)
                
                # Ensure it meets minimum order size
                if btc_amount_rounded < min_qty:
                    btc_amount_rounded = min_qty
                    log.warning(f"   ⚠️  Quantity below minimum, using minimum: {min_qty} BTC")
                
                # Format to appropriate decimal places based on qtyStep
                # If qtyStep = 0.001, format to 3 decimal places
                if qty_step >= 1:
                    decimal_places = 0
                elif qty_step >= 0.1:
                    decimal_places = 1
                elif qty_step >= 0.01:
                    decimal_places = 2
                elif qty_step >= 0.001:
                    decimal_places = 3
                else:
                    decimal_places = 8
                
                # Convert to string - Bybit V5 API expects qty as a string
                # Use appropriate decimal precision based on qtyStep
                quantity = f"{btc_amount_rounded:.{decimal_places}f}".rstrip('0').rstrip('.')  # Remove trailing zeros
                
                log.info(f"   📦 Quantity Format:")
                log.info(f"     Base Amount: {amount:.8f} {self.symbol.split('/')[0]}")
                log.info(f"     Position Value: ${quantity_usd:,.2f} USDT")
                log.info(f"     Quantity String: '{quantity}' (BTC amount)")
                
                # Validation: check if quantity is reasonable
                if amount > 10:  # More than 10 BTC is very large
                    log.warning(f"   ⚠️  Large quantity: {amount:.8f} BTC (${quantity_usd:,.0f} position)")
                    log.warning(f"   Consider reducing RISK_PER_TRADE_PERCENT in config.py")
                elif amount < 0.0001:  # Less than 0.0001 BTC is very small
                    log.warning(f"   ⚠️  Very small quantity: {amount:.8f} BTC")
                    log.warning(f"   This might be below minimum order size")
                elif amount <= 0:
                    log.error(f"   ❌ Invalid quantity: {amount:.8f} BTC")
                    return None
            except Exception as e:
                log.error(f"Error calculating quantity: {e}")
                return None
            
            # Set leverage and margin mode before placing order (required for unified accounts)
            # Get leverage from config.py
            leverage = config.get_leverage(self.symbol)
            self._set_leverage(symbol_bybit, leverage)
            
            # Set margin mode to Cross Margin (required for unified accounts)
            # Cross margin allows using all available balance as collateral
            self._set_margin_mode('Cross')
            
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            
            # Build query string for order placement
            # For Unified Account, use 'linear' category for USDT Perpetual contracts
            # Symbol format: BTCUSDT (no slash, for unified account)
            # IMPORTANT: qty should be a string representing the BTC amount (base currency)
            # positionIdx: 0 = one-way mode, 1 = long hedge, 2 = short hedge
            order_params = {
                'category': 'linear',  # USDT Perpetual contracts
                'symbol': symbol_bybit,  # BTCUSDT format for unified account
                'side': bybit_side,
                'orderType': 'Market',
                'qty': quantity,  # String format: BTC amount (e.g., "0.01" or "0.52384599")
                'positionIdx': position_idx  # 0 = one-way, 1 = long hedge, 2 = short hedge
            }
            
            position_idx_name = {
                '0': 'One-Way Mode',
                '1': 'Long Hedge Position',
                '2': 'Short Hedge Position'
            }.get(position_idx, f'Unknown ({position_idx})')
            
            log.info(f"   📋 Order Configuration:")
            log.info(f"     Category: linear (USDT Perpetual)")
            log.info(f"     Symbol: {symbol_bybit} (Unified Account format)")
            log.info(f"     Account Type: UNIFIED")
            log.info(f"     Side: {bybit_side}")
            log.info(f"     Quantity: {quantity} {self.symbol.split('/')[0]} (${quantity_usd:,.2f} position value)")
            log.info(f"     Position Index: {position_idx} ({position_idx_name})")
            log.info(f"     Leverage: {leverage}x")
            log.info(f"     Estimated Margin: ${quantity_usd / leverage:,.2f} USDT")
            
            # Add any additional params
            if params:
                order_params.update(params)
            
            # For POST requests with JSON body, Bybit V5 requires signature from JSON string
            import json
            # Use compact JSON with no spaces (required for signature)
            json_body = json.dumps(order_params, separators=(',', ':'))
            
            # Debug: Log the exact JSON being sent
            log.info(f"   🔍 JSON Body (exact format): {json_body}")
            
            log.info(f"   Order parameters: {order_params}")
            log.info(f"   JSON body: {json_body}")
            
            # Signature for POST: timestamp + api_key + recv_window + json_body
            sign_string = timestamp + config.API_KEY + recv_window + json_body
            signature = hmac.new(
                config.API_SECRET.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Use demo API endpoint
            base_url = "https://api-demo.bybit.com" if config.ENVIRONMENT == 'DEMO' else "https://api.bybit.com"
            url = f"{base_url}/v5/order/create"
            
            headers = {
                'X-BAPI-API-KEY': config.API_KEY,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window,
                'Content-Type': 'application/json'
            }
            
            log.info(f"   Sending POST request to: {url}")
            response = requests.post(url, headers=headers, data=json_body, timeout=10)
            
            log.info(f"   Response status: {response.status_code}")
            log.info(f"   Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    order_id = result.get('orderId', 'N/A')
                    
                    log.info(f"✅ Order placed via direct API: {order_id}")
                    log.info(f"   Side: {bybit_side}")
                    log.info(f"   Quantity: {quantity} {self.symbol.split('/')[0]}")
                    log.info(f"   Symbol: {symbol_bybit}")
                    
                    # Return in CCXT-like format
                    return {
                        'id': order_id,
                        'info': data,
                        'status': 'closed',  # Market orders are usually filled immediately
                        'filled': amount,
                        'amount': amount,
                        'side': side,
                        'symbol': self.symbol
                    }
                else:
                    error_msg = data.get('retMsg', 'Unknown error')
                    ret_code = data.get('retCode')
                    log.error(f"Direct API order error: {error_msg} (retCode: {ret_code})")
                    
                    # Handle specific error codes with helpful messages
                    if ret_code == 110007:
                        log.error("")
                        log.error("=" * 80)
                        log.error("❌ INSUFFICIENT BALANCE ERROR")
                        log.error("=" * 80)
                        log.error("   Error Code: 110007 - 'ab not enough for new order'")
                        log.error("   This means there's not enough available balance/margin")
                        log.error("   to open this position.")
                        log.error("")
                        log.error("   According to Bybit Demo Trading docs:")
                        log.error("   https://bybit-exchange.github.io/docs/v5/demo")
                        log.error("")
                        log.error("   Possible reasons:")
                        log.error("   1. Demo account might need funds requested via API")
                        log.error("      Use: POST /v5/account/demo-apply-money")
                        log.error("   2. Leverage not set (we tried to set it, check logs above)")
                        log.error("   3. Margin mode not configured (might need Cross/Isolated)")
                        log.error("   4. Demo account API restrictions (manual orders work, API might be limited)")
                        log.error("")
                        log.error("   Solutions:")
                        log.error("   - Try requesting demo funds via API if balance shows 0")
                        log.error("   - Check leverage was set successfully (see logs above)")
                        log.error("   - Reduce quantity_btc in trading_config.json to test")
                        log.error("   - Verify account settings on Bybit demo website")
                        log.error("=" * 80)
                        log.error("")
                    elif ret_code == 10001:
                        log.error("")
                        log.error("=" * 80)
                        log.error("❌ QUANTITY ERROR")
                        log.error("=" * 80)
                        log.error("   Error Code: 10001 - Quantity exceeds maximum limit")
                        log.error("   The position size is too large.")
                        log.error("")
                        log.error("   Details:")
                        log.error(f"   - Quantity sent: {quantity} {self.symbol.split('/')[0]}")
                        log.error(f"   - Amount (BTC): {amount:.8f}")
                        log.error(f"   - Current Price: ${current_price:,.2f}")
                        log.error(f"   - Position Value: ${quantity_usd:,.2f}")
                        log.error("")
                        log.error("   Solutions:")
                        log.error("   - Reduce quantity_btc in trading_config.json")
                        log.error("   - Try a much smaller quantity (e.g., 0.0001 BTC)")
                        log.error("   - Check if demo account has position size limits")
                        log.error("=" * 80)
                        log.error("")
                    
                    return None
            else:
                log.error(f"HTTP {response.status_code}: {response.text[:200]}")
                return None
                
        except Exception as e:
            log.error(f"Error in direct API order call: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def execute_signal(self, signal: int, current_price: float, balance: float = None) -> bool:
        """
        Execute trade based on strategy signal using config.py risk management
        Supports both one-way mode and hedge mode
        
        Args:
            signal: 1 for long, -1 for short, 0 for no action (exit signal)
            current_price: Current market price
            balance: Available balance (optional, for logging)
            
        Returns:
            True if order executed successfully or position closed
        """
        # Load hedge mode setting from config
        trading_config = config.load_trading_config()
        hedge_mode = trading_config.get('hedge_mode', False)
        
        if signal == 0:
            # Strategy exit signal: Close any existing position for this symbol
            if self.symbol in self.positions:
                symbol_positions = self.positions[self.symbol]
                if hedge_mode and isinstance(symbol_positions, dict):
                    # In hedge mode, close both long and short if they exist
                    closed_any = False
                    if symbol_positions.get('long') is not None:
                        if self.close_position(self.symbol, side='long'):
                            closed_any = True
                    if symbol_positions.get('short') is not None:
                        if self.close_position(self.symbol, side='short'):
                            closed_any = True
                    if closed_any:
                        log.info(f"✅ Position(s) closed due to strategy exit signal")
                        return True
                elif symbol_positions is not None:
                    # One-way mode
                    log.info(f"🔄 Strategy exit signal (HOLD) - closing {self.symbol} position")
                    if self.close_position(self.symbol):
                        log.info(f"✅ Position closed due to strategy exit signal")
                        return True
            log.info("⏸️  No signal - no position to close")
            return False
        
        # Check global drawdown limit (kill switch)
        if balance is not None:
            if self.check_global_drawdown(balance):
                return False  # Trading stopped due to drawdown
        
        # Track if we're doing a position reversal (closing opposite and opening new)
        is_reversal = False
        
        # Initialize position structure for this symbol if needed
        if self.symbol not in self.positions:
            if hedge_mode:
                self.positions[self.symbol] = {'long': None, 'short': None}
            else:
                self.positions[self.symbol] = None
        
        symbol_positions = self.positions[self.symbol]
        side_key = 'long' if signal == 1 else 'short'
        side_name = "LONG" if signal == 1 else "SHORT"
        
        if hedge_mode:
            # HEDGE MODE: Allow both long and short positions simultaneously
            if isinstance(symbol_positions, dict):
                existing_pos = symbol_positions.get(side_key)
                
                if existing_pos is not None:
                    # Already have a position in this direction
                    log.info(f"ℹ️  Already in {self.symbol} {side_name} position, skipping")
                    return False
                else:
                    # No position in this direction, can open new one
                    log.info(f"🔄 HEDGE MODE: Opening {side_name} position (may coexist with opposite position)")
            else:
                # Legacy format - convert to hedge mode structure
                if symbol_positions is not None:
                    # Migrate existing position to hedge mode structure
                    old_side = 'long' if symbol_positions['side'] == 1 else 'short'
                    self.positions[self.symbol] = {
                        'long': symbol_positions if old_side == 'long' else None,
                        'short': symbol_positions if old_side == 'short' else None
                    }
                    symbol_positions = self.positions[self.symbol]
                else:
                    self.positions[self.symbol] = {'long': None, 'short': None}
                    symbol_positions = self.positions[self.symbol]
        else:
            # ONE-WAY MODE: Close opposite position before opening new one
            if symbol_positions is not None:
                if isinstance(symbol_positions, dict):
                    # Convert from hedge mode to one-way mode
                    existing_long = symbol_positions.get('long')
                    existing_short = symbol_positions.get('short')
                    if existing_long is not None:
                        symbol_positions = existing_long
                    elif existing_short is not None:
                        symbol_positions = existing_short
                    else:
                        symbol_positions = None
                    self.positions[self.symbol] = symbol_positions
                
                if symbol_positions is not None:
                    existing_pos = symbol_positions
                    existing_side_name = "LONG" if existing_pos['side'] == 1 else "SHORT"
                    
                    # Close opposite position and open new one directly
                    if (signal == 1 and existing_pos['side'] == -1) or \
                       (signal == -1 and existing_pos['side'] == 1):
                        is_reversal = True
                        log.info("")
                        log.info("=" * 80)
                        log.info(f"🔄 POSITION REVERSAL DETECTED (One-Way Mode)")
                        log.info("=" * 80)
                        log.info(f"   Current Position: {existing_side_name} ({existing_pos['side']})")
                        log.info(f"   New Signal: {side_name} ({signal})")
                        log.info(f"   Action: Closing {existing_side_name} → Opening {side_name}")
                        log.info("=" * 80)
                        log.info("")
                        
                        # Close the existing opposite position
                        if self.close_position(self.symbol):
                            log.info(f"✅ {existing_side_name} position closed successfully")
                            # Small delay to ensure position is fully closed
                            time.sleep(0.5)
                        else:
                            log.warning(f"⚠️  Failed to close {existing_side_name} position, but continuing to open {side_name}")
                            # Clear the position tracking even if close failed
                            self.positions[self.symbol] = None
                        
                        log.info(f"🔄 Proceeding to open {side_name} position...")
                    elif signal == existing_pos['side']:
                        log.info(f"ℹ️  Already in {self.symbol} {existing_side_name} position with same signal, skipping")
                        return False
        
        # Check if we can open a new position (max concurrent trades)
        if not self.can_open_new_position(hedge_mode=hedge_mode):
            return False
        
        # Check if fixed BTC quantity is set in config
        trading_config = config.load_trading_config()
        fixed_quantity_btc = trading_config.get('quantity_btc')
        
        if fixed_quantity_btc is not None and fixed_quantity_btc > 0:
            # Use fixed BTC quantity from config
            position_size = float(fixed_quantity_btc)
            log.info(f"💰 Using fixed BTC quantity from config: {position_size:.6f} {self.symbol.split('/')[0]}")
        else:
            # Calculate position size using config.py risk management
            if signal == 1:  # Long position
                stop_loss_price = current_price * (1 - self.stop_loss_pct)
            else:  # Short position
                stop_loss_price = current_price * (1 + self.stop_loss_pct)
            
            position_size = self.calculate_position_size(current_price, stop_loss_price)
            
            if position_size <= 0:
                log.warning("⚠️  Position size too small or invalid, skipping trade")
                log.warning(f"   Calculated position size: {position_size}")
                return False
            
            log.info(f"💰 Position size calculated (risk-based): {position_size:.6f} {self.symbol.split('/')[0]}")
            log.info(f"   Entry price: ${current_price:,.2f}")
            log.info(f"   Stop loss: ${stop_loss_price:,.2f}")
        
        # Calculate stop loss price for position tracking (even if using fixed quantity)
        if signal == 1:  # Long position
            stop_loss_price = current_price * (1 - self.stop_loss_pct)
        else:  # Short position
            stop_loss_price = current_price * (1 + self.stop_loss_pct)
        
        # Place order
        side = 'buy' if signal == 1 else 'sell'
        side_name = "LONG" if signal == 1 else "SHORT"
        
        # Determine positionIdx for hedge mode
        position_idx = None
        if hedge_mode:
            # In hedge mode: 1 = long, 2 = short
            position_idx = '1' if signal == 1 else '2'
        else:
            # One-way mode: 0
            position_idx = '0'
        
        if is_reversal:
            log.info(f"🔄 Opening {side_name} position (after closing opposite position)...")
        else:
            log.info(f"🔄 Attempting to place {side.upper()} order...")
        
        order = self.place_market_order(side, position_size, position_idx=position_idx)
        
        if order:
            # Track position (support hedge mode)
            position_data = {
                'side': signal,
                'size': position_size,
                'entry_price': current_price,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': current_price * (1 + self.take_profit_pct) if signal == 1 else current_price * (1 - self.take_profit_pct)
            }
            
            if hedge_mode:
                # In hedge mode, store position in the side-specific key
                if not isinstance(self.positions[self.symbol], dict):
                    self.positions[self.symbol] = {'long': None, 'short': None}
                self.positions[self.symbol][side_key] = position_data
            else:
                # One-way mode: store directly
                self.positions[self.symbol] = position_data
            
            # Count active positions for logging
            if hedge_mode:
                active_count = sum(1 for sym_pos in self.positions.values() 
                                 if isinstance(sym_pos, dict) and (sym_pos.get('long') or sym_pos.get('short')))
            else:
                active_count = len([p for p in self.positions.values() if p is not None])
            
            log.info("")
            log.info("=" * 80)
            if hedge_mode:
                log.info(f"✅ HEDGE MODE: {side_name} position opened (can coexist with opposite position)")
            elif is_reversal:
                log.info(f"✅ POSITION REVERSAL COMPLETED: {side_name} opened")
            else:
                log.info("✅ POSITION OPENED SUCCESSFULLY")
            log.info("=" * 80)
            log.info(f"   Side: {side.upper()} ({side_name})")
            log.info(f"   Size: {position_size:.6f} {self.symbol.split('/')[0]}")
            log.info(f"   Entry: ${current_price:,.2f}")
            log.info(f"   Stop Loss: ${stop_loss_price:,.2f}")
            if hedge_mode:
                take_profit = self.positions[self.symbol][side_key]['take_profit_price']
            else:
                take_profit = self.positions[self.symbol]['take_profit_price']
            log.info(f"   Take Profit: ${take_profit:,.2f}")
            log.info(f"   Order ID: {order.get('id', 'N/A')}")
            log.info(f"   Active Positions: {active_count}/{self.max_concurrent_trades}")
            if hedge_mode:
                # Show both positions if they exist
                sym_pos = self.positions[self.symbol]
                if sym_pos.get('long') and sym_pos.get('short'):
                    log.info(f"   📊 HEDGE: Both LONG and SHORT positions active for {self.symbol}")
            log.info("=" * 80)
            log.info("")
            return True
        else:
            log.error("")
            log.error("=" * 80)
            log.error("❌ ORDER PLACEMENT FAILED")
            log.error("=" * 80)
            log.error("   Check the error messages above for details")
            log.error("   The order was not placed on the exchange")
            log.error("=" * 80)
            log.error("")
        
        return False
    
    def close_position(self, symbol: str = None, side: str = None) -> bool:
        """
        Close position for a specific symbol and side (supports hedge mode)
        
        Args:
            symbol: Symbol to close position for (defaults to self.symbol)
            side: 'long' or 'short' (for hedge mode). If None, closes any position (one-way mode)
            
        Returns:
            True if position closed successfully
        """
        if symbol is None:
            symbol = self.symbol
        
        if symbol not in self.positions:
            log.info(f"ℹ️  No {symbol} position to close")
            return False
        
        symbol_positions = self.positions[symbol]
        
        # Load hedge mode setting
        trading_config = config.load_trading_config()
        hedge_mode = trading_config.get('hedge_mode', False)
        
        if hedge_mode and isinstance(symbol_positions, dict):
            # HEDGE MODE: Close specific side
            if side is None:
                # Close both if side not specified
                closed_any = False
                if symbol_positions.get('long') is not None:
                    if self.close_position(symbol, side='long'):
                        closed_any = True
                if symbol_positions.get('short') is not None:
                    if self.close_position(symbol, side='short'):
                        closed_any = True
                return closed_any
            
            position = symbol_positions.get(side)
            if position is None:
                log.info(f"ℹ️  No {symbol} {side.upper()} position to close")
                return False
            
            try:
                close_side = 'sell' if position['side'] == 1 else 'buy'
                # Use correct positionIdx for closing in hedge mode
                position_idx = '1' if side == 'long' else '2'
                order = self.place_market_order(close_side, position['size'], position_idx=position_idx)
                
                if order:
                    log.info(f"✅ {symbol} {side.upper()} position closed: {close_side.upper()} {position['size']:.6f}")
                    symbol_positions[side] = None
                    # If both sides are None, clean up the structure
                    if symbol_positions.get('long') is None and symbol_positions.get('short') is None:
                        self.positions[symbol] = None
                    return True
                
                return False
                
            except Exception as e:
                log.error(f"❌ Error closing {symbol} {side} position: {e}")
                return False
        else:
            # ONE-WAY MODE: Close the single position
            if isinstance(symbol_positions, dict):
                # Convert from hedge mode structure
                if symbol_positions.get('long') is not None:
                    symbol_positions = symbol_positions['long']
                elif symbol_positions.get('short') is not None:
                    symbol_positions = symbol_positions['short']
                else:
                    symbol_positions = None
                self.positions[symbol] = symbol_positions
            
            if symbol_positions is None:
                log.info(f"ℹ️  No {symbol} position to close")
                return False
            
            position = symbol_positions
            
            try:
                close_side = 'sell' if position['side'] == 1 else 'buy'
                # One-way mode uses positionIdx='0'
                order = self.place_market_order(close_side, position['size'], position_idx='0')
                
                if order:
                    log.info(f"✅ {symbol} position closed: {close_side.upper()} {position['size']:.6f}")
                    self.positions[symbol] = None
                    return True
                
                return False
                
            except Exception as e:
                log.error(f"❌ Error closing {symbol} position: {e}")
                return False
    
    def close_all_positions(self) -> int:
        """
        Close all open positions (supports hedge mode)
        
        Returns:
            Number of positions closed
        """
        closed = 0
        trading_config = config.load_trading_config()
        hedge_mode = trading_config.get('hedge_mode', False)
        
        for symbol in list(self.positions.keys()):
            symbol_positions = self.positions[symbol]
            
            if hedge_mode and isinstance(symbol_positions, dict):
                # Close both long and short if they exist
                if symbol_positions.get('long') is not None:
                    if self.close_position(symbol, side='long'):
                        closed += 1
                if symbol_positions.get('short') is not None:
                    if self.close_position(symbol, side='short'):
                        closed += 1
            elif symbol_positions is not None:
                # One-way mode
                if self.close_position(symbol):
                    closed += 1
        return closed
    
    def check_stop_loss_take_profit(self, current_price: float) -> List[str]:
        """
        Check if stop loss or take profit should be triggered for any position (supports hedge mode)
        
        Args:
            current_price: Current market price
            
        Returns:
            List of symbols that had positions closed
        """
        closed_symbols = []
        trading_config = config.load_trading_config()
        hedge_mode = trading_config.get('hedge_mode', False)
        
        for symbol, symbol_positions in self.positions.items():
            if symbol_positions is None:
                continue
            
            if hedge_mode and isinstance(symbol_positions, dict):
                # HEDGE MODE: Check both long and short positions separately
                for side_key in ['long', 'short']:
                    position = symbol_positions.get(side_key)
                    if position is None:
                        continue
                    
                    entry = position['entry_price']
                    sl = position['stop_loss_price']
                    tp = position['take_profit_price']
                    side = position['side']
                    
                    # Check stop loss
                    if (side == 1 and current_price <= sl) or (side == -1 and current_price >= sl):
                        log.warning(f"🛑 Stop loss triggered for {symbol} {side_key.upper()}: ${current_price:.2f} {'<=' if side == 1 else '>='} ${sl:.2f}")
                        if self.close_position(symbol, side=side_key):
                            closed_symbols.append(f"{symbol}_{side_key}")
                        continue
                    
                    # Check take profit
                    if (side == 1 and current_price >= tp) or (side == -1 and current_price <= tp):
                        log.info(f"🎯 Take profit triggered for {symbol} {side_key.upper()}: ${current_price:.2f} {'>=' if side == 1 else '<='} ${tp:.2f}")
                        if self.close_position(symbol, side=side_key):
                            closed_symbols.append(f"{symbol}_{side_key}")
                        continue
            else:
                # ONE-WAY MODE: Check single position
                if isinstance(symbol_positions, dict):
                    # Convert from hedge mode structure
                    if symbol_positions.get('long') is not None:
                        position = symbol_positions['long']
                    elif symbol_positions.get('short') is not None:
                        position = symbol_positions['short']
                    else:
                        continue
                else:
                    position = symbol_positions
                
                entry = position['entry_price']
                sl = position['stop_loss_price']
                tp = position['take_profit_price']
                side = position['side']
                
                # Check stop loss
                if (side == 1 and current_price <= sl) or (side == -1 and current_price >= sl):
                    log.warning(f"🛑 Stop loss triggered for {symbol}: ${current_price:.2f} {'<=' if side == 1 else '>='} ${sl:.2f}")
                    if self.close_position(symbol):
                        closed_symbols.append(symbol)
                    continue
                
                # Check take profit
                if (side == 1 and current_price >= tp) or (side == -1 and current_price <= tp):
                    log.info(f"🎯 Take profit triggered for {symbol}: ${current_price:.2f} {'>=' if side == 1 else '<='} ${tp:.2f}")
                    if self.close_position(symbol):
                        closed_symbols.append(symbol)
                    continue
        
        return closed_symbols


class LiveTradingBot:
    """
    Live trading bot that monitors for signals and executes trades automatically
    Uses TradingBot for actual trade execution
    """
    
    def __init__(self, strategy_name: str = None, symbol: str = None, 
                 use_demo: bool = None, check_interval: int = None, timeframe: str = None):
        """
        Initialize live trading bot
        
        Args (all optional - will use trading_config.json if not provided):
            strategy_name: Strategy to use ('Bollinger_Bands', 'Moving_Average', 'RSI')
            symbol: Trading pair
            use_demo: Use demo trading account (None = auto-detect from config)
            check_interval: How often to check for signals (seconds)
            timeframe: Timeframe for OHLCV data (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
        """
        # Load configuration from trading_config.json (frontend-controlled)
        trading_config = config.load_trading_config()
        
        # Use provided values or fall back to config file, then defaults
        self.strategy_name = strategy_name or trading_config.get('strategy', 'Bollinger_Bands')
        self.symbol = symbol or trading_config.get('symbol', 'BTC/USDT')
        self.timeframe = timeframe or trading_config.get('timeframe', '1h')
        self.check_interval = check_interval or trading_config.get('check_interval', 60)
        
        # Default to DEMO trading (safe for testing)
        if use_demo is None:
            self.use_demo = (config.ENVIRONMENT == 'DEMO')
        else:
            self.use_demo = use_demo
        
        # Store config reload capability
        self.config_file = Path(__file__).parent / 'trading_config.json'
        self.config_reload_interval = 30  # Reload config every 30 seconds
        self.last_config_reload = 0
        
        # Load hedge mode setting
        hedge_mode = trading_config.get('hedge_mode', False)
        
        # Initialize exchange connection
        log.info("=" * 80)
        log.info("INITIALIZING TRADING BOT")
        log.info("=" * 80)
        log.info(f"📊 Strategy: {self.strategy_name}")
        log.info(f"💰 Symbol: {self.symbol}")
        log.info(f"⏰ Timeframe: {self.timeframe} ⭐ (Active)")
        log.info(f"🔒 Mode: {'DEMO TRADING (Safe for Testing)' if self.use_demo else '⚠️  LIVE TRADING (Real Money!)'}")
        log.info(f"⏱️  Check Interval: {self.check_interval} seconds")
        log.info(f"📁 Config Source: trading_config.json (auto-reloads every 30s)")
        if hedge_mode:
            log.info(f"🔄 HEDGE MODE: ENABLED (Both LONG and SHORT positions can coexist)")
            log.warning("⚠️  IMPORTANT: Make sure Hedge Mode is enabled on your Bybit account!")
            log.warning("   Go to Bybit website/app → Derivatives → Settings → Enable Hedge Mode")
            log.warning("   You cannot switch modes while holding positions or active orders")
        else:
            log.info(f"🔄 ONE-WAY MODE: Enabled (Opposite positions will be closed before opening new ones)")
        if self.use_demo:
            log.info("✅ Using Bybit Demo Trading - No real money at risk")
        else:
            log.warning("⚠️  WARNING: Using LIVE Trading - Real money will be used!")
        log.info("=" * 80)
        
        # Test connection using Bybit_connection_test.py
        log.info("Testing connection using Bybit_connection_test.py...")
        log.info("")
        try:
            # Run the comprehensive connection test
            test_demo_connection()
            log.info("")
            log.info("✅ Connection test completed successfully!")
            log.info("")
        except SystemExit as e:
            # test_demo_connection() calls sys.exit(1) on failure
            if e.code != 0:
                raise Exception("Connection test failed. Please check your API keys and connection. Run 'python Bybit_connection_test.py' for detailed diagnostics.")
        except Exception as e:
            log.error(f"❌ Connection test failed: {e}")
            raise Exception("Failed to connect to Bybit. Please check your API keys and connection.")
        
        # Initialize trading bot (use resolved values from config)
        self.trading_bot = TradingBot(symbol=self.symbol, use_demo=self.use_demo)
        
        # Strategy function mapping
        self.strategy_funcs = {
            'Bollinger_Bands': run_bb_strategy,
            'Moving_Average': run_ma_strategy,
            'RSI': run_rsi_strategy
        }
        
        # Check if resolved strategy name is valid (use self.strategy_name, not the parameter)
        if self.strategy_name not in self.strategy_funcs:
            raise ValueError(f"Unknown strategy: {self.strategy_name}. Available: {list(self.strategy_funcs.keys())}")
        
        log.info("✅ Trading bot initialized successfully!")
    
    def get_latest_data(self, limit: int = 500) -> Optional[pd.DataFrame]:
        """
        Fetch latest OHLCV data from exchange
        
        Args:
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with OHLCV data or None if failed
        """
        try:
            # Use the trading bot's exchange connection
            exchange = self.trading_bot.exchange
            
            # For demo trading, OHLCV data should use public API (market data)
            # Try CCXT first, but if it fails with 10032 error, use direct API call
            try:
                # Fetch OHLCV data using configured timeframe
                ohlcv = exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
            except Exception as ccxt_error:
                error_str = str(ccxt_error)
                # Check if it's the demo trading error (10032)
                if "10032" in error_str or "Demo trading are not supported" in error_str:
                    log.info(f"ℹ️  CCXT fetch_ohlcv doesn't work with demo trading, using direct API call for {self.timeframe} timeframe...")
                    # Use direct API call for OHLCV data (public endpoint should work)
                    ohlcv = self._fetch_ohlcv_direct_api(limit)
                    if ohlcv is None:
                        raise ccxt_error  # Re-raise if direct API also fails
                else:
                    raise  # Re-raise other errors
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['time'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.set_index('time')
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            # Normalize column names to lowercase
            df.columns = df.columns.str.lower()
            
            return df
            
        except Exception as e:
            log.error(f"❌ Error fetching data: {e}")
            return None
    
    def _fetch_ohlcv_direct_api(self, limit: int = 500) -> Optional[List]:
        """
        Fetch OHLCV data using direct Bybit API call (for demo trading compatibility)
        
        Args:
            limit: Number of candles to fetch
            
        Returns:
            List of OHLCV candles or None if failed
        """
        try:
            import requests
            
            # Map timeframe to Bybit interval
            timeframe_map = {
                '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
                '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
                '1d': 'D', '1w': 'W', '1M': 'M'
            }
            
            interval = timeframe_map.get(self.timeframe, '60')  # Default to 1h
            
            # Convert symbol to Bybit format (BTC/USDT -> BTCUSDT)
            symbol_bybit = self.symbol.replace('/', '')
            
            # Use public API endpoint (works for both demo and live)
            # For demo trading, we can still use the public market data endpoint
            base_url = "https://api.bybit.com"  # Public API works for market data
            if config.ENVIRONMENT == 'DEMO':
                # Try demo API first, but public market data usually works
                base_url = "https://api-demo.bybit.com"
            
            url = f"{base_url}/v5/market/kline"
            params = {
                'category': 'linear',
                'symbol': symbol_bybit,
                'interval': interval,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    klines = result.get('list', [])
                    
                    # Convert Bybit format to CCXT format
                    # Bybit returns: [startTime, open, high, low, close, volume, turnover]
                    # CCXT expects: [timestamp, open, high, low, close, volume]
                    ohlcv = []
                    for kline in reversed(klines):  # Reverse to get chronological order
                        timestamp = int(kline[0])  # startTime
                        open_price = float(kline[1])
                        high_price = float(kline[2])
                        low_price = float(kline[3])
                        close_price = float(kline[4])
                        volume = float(kline[5])
                        
                        ohlcv.append([timestamp, open_price, high_price, low_price, close_price, volume])
                    
                    log.info(f"✓ Fetched {len(ohlcv)} {self.timeframe} candles using direct API")
                    return ohlcv
                else:
                    # Try public API if demo API fails
                    if base_url == "https://api-demo.bybit.com":
                        log.info("   Trying public API endpoint...")
                        return self._fetch_ohlcv_direct_api_public(limit)
                    else:
                        log.error(f"Direct API error: {data.get('retMsg')}")
                        return None
            else:
                log.error(f"HTTP {response.status_code}: {response.text[:100]}")
                return None
                
        except Exception as e:
            log.error(f"Error in direct API call: {e}")
            return None
    
    def _fetch_ohlcv_direct_api_public(self, limit: int = 500) -> Optional[List]:
        """
        Fetch OHLCV using public API (always works for market data)
        """
        try:
            import requests
            
            timeframe_map = {
                '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
                '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
                '1d': 'D', '1w': 'W', '1M': 'M'
            }
            
            interval = timeframe_map.get(self.timeframe, '60')
            symbol_bybit = self.symbol.replace('/', '')
            
            # Public market data endpoint (works for both demo and live)
            url = "https://api.bybit.com/v5/market/kline"
            params = {
                'category': 'linear',
                'symbol': symbol_bybit,
                'interval': interval,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('retCode') == 0:
                    result = data.get('result', {})
                    klines = result.get('list', [])
                    
                    ohlcv = []
                    for kline in reversed(klines):
                        timestamp = int(kline[0])
                        open_price = float(kline[1])
                        high_price = float(kline[2])
                        low_price = float(kline[3])
                        close_price = float(kline[4])
                        volume = float(kline[5])
                        
                        ohlcv.append([timestamp, open_price, high_price, low_price, close_price, volume])
                    
                    log.info(f"✓ Fetched {len(ohlcv)} {self.timeframe} candles using public API")
                    return ohlcv
                else:
                    log.error(f"Public API error: {data.get('retMsg')}")
                    return None
            else:
                log.error(f"HTTP {response.status_code}")
                return None
                
        except Exception as e:
            log.error(f"Error in public API call: {e}")
            return None
    
    def get_current_signal(self, df: pd.DataFrame) -> Optional[int]:
        """
        Get current trading signal from strategy
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            Signal: 1 for long, -1 for short, 0 for no action, None if error
        """
        try:
            # Run strategy
            metrics, strategy_df = self.strategy_funcs[self.strategy_name](df)
            
            if strategy_df is None or 'Signal' not in strategy_df.columns:
                return None
            
            # Get the latest signal
            latest_signal = strategy_df['Signal'].iloc[-1]
            
            # Convert to int (handle NaN)
            if pd.isna(latest_signal):
                return 0
            
            return int(latest_signal)
            
        except Exception as e:
            log.error(f"❌ Error getting signal: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_portfolio_value(self) -> Optional[float]:
        """
        Get current total portfolio value (account equity)
        
        For Bybit Unified Accounts, the 'equity' value from the balance API
        already includes all positions, unrealized P&L, and margins.
        This is the correct portfolio value to use for drawdown calculations.
        
        Returns:
            Total portfolio value (equity) in USDT or None if error
        """
        try:
            balance = self.trading_bot.get_balance()
            if balance is None:
                return None
            
            # For Bybit Unified Accounts, use 'equity' value which already includes:
            # - Wallet balance
            # - All open positions (with unrealized P&L)
            # - All margins used
            # This is the accurate total portfolio value
            if isinstance(balance, dict):
                # Check if equity is stored in balance dict (from direct API call)
                if 'equity' in balance and 'USDT' in balance.get('equity', {}):
                    equity = balance['equity']['USDT']
                    if equity and equity > 0:
                        log.debug(f"   Using equity from balance API: ${equity:,.2f}")
                        return float(equity)
                
                # Fallback: Try to get equity from balance info if available
                if 'info' in balance:
                    info = balance['info']
                    result = info.get('result', {})
                    account_list = result.get('list', [])
                    if account_list:
                        account = account_list[0]
                        coins = account.get('coin', [])
                        for coin in coins:
                            if coin.get('coin') == 'USDT':
                                equity_str = coin.get('equity', '')
                                if equity_str and equity_str != 'N/A' and equity_str != '':
                                    try:
                                        equity = float(equity_str)
                                        log.debug(f"   Using equity from balance info: ${equity:,.2f}")
                                        return equity
                                    except (ValueError, TypeError):
                                        pass
            
            # Last resort: Use wallet balance (not ideal, but better than None)
            # This will underestimate portfolio value if there are open positions
            usdt_balance = balance.get('USDT', {}).get('total', 0) or balance.get('USDT', {}).get('free', 0)
            if usdt_balance:
                log.warning(f"   ⚠️  Using wallet balance instead of equity (may not include positions): ${usdt_balance:,.2f}")
                return float(usdt_balance)
            
            return None
            
        except Exception as e:
            log.error(f"❌ Error getting portfolio value: {e}")
            return None
    
    def run(self):
        """
        Main loop: Monitor for signals and execute trades
        """
        log.info("=" * 80)
        log.info("STARTING TRADING BOT")
        log.info("=" * 80)
        log.info(f"Mode: {'DEMO TRADING (Safe for Testing)' if self.use_demo else '⚠️  LIVE TRADING (Real Money!)'}")
        log.info(f"⏰ Active Timeframe: {self.timeframe}")
        log.info(f"📊 Strategy: {self.strategy_name}")
        log.info(f"💰 Symbol: {self.symbol}")
        log.info(f"⏱️  Check Interval: {self.check_interval} seconds")
        log.info("Press Ctrl+C to stop")
        log.info("=" * 80)
        log.info("")
        
        last_signal = None
        iteration = 0
        
        try:
            while True:
                iteration += 1
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Reload config from file periodically (allows frontend to update settings)
                if time.time() - self.last_config_reload >= self.config_reload_interval:
                    try:
                        trading_config = config.load_trading_config()
                        
                        # Update settings if changed in config file
                        if trading_config.get('timeframe') != self.timeframe:
                            old_timeframe = self.timeframe
                            self.timeframe = trading_config.get('timeframe', self.timeframe)
                            log.info("")
                            log.info("=" * 80)
                            log.info(f"🔄 TIMEFRAME UPDATED FROM CONFIG")
                            log.info(f"   Old Timeframe: {old_timeframe}")
                            log.info(f"   New Timeframe: {self.timeframe}")
                            log.info("=" * 80)
                            log.info("")
                        
                        if trading_config.get('strategy') != self.strategy_name:
                            old_strategy = self.strategy_name
                            self.strategy_name = trading_config.get('strategy', self.strategy_name)
                            log.info(f"🔄 Strategy updated from config: {old_strategy} → {self.strategy_name}")
                        
                        if trading_config.get('symbol') != self.symbol:
                            old_symbol = self.symbol
                            self.symbol = trading_config.get('symbol', self.symbol)
                            log.info(f"🔄 Symbol updated from config: {old_symbol} → {self.symbol}")
                        
                        if trading_config.get('check_interval') != self.check_interval:
                            old_interval = self.check_interval
                            self.check_interval = trading_config.get('check_interval', self.check_interval)
                            log.info(f"🔄 Check interval updated from config: {old_interval}s → {self.check_interval}s")
                        
                        # Check if trading is disabled
                        if not trading_config.get('enabled', True):
                            log.warning("⚠️  Trading is DISABLED in config file. Waiting...")
                            time.sleep(10)
                            continue
                        
                        self.last_config_reload = time.time()
                    except Exception as e:
                        log.warning(f"⚠️  Error reloading config: {e}")
                
                log.info(f"[{current_time}] Iteration #{iteration} | Timeframe: {self.timeframe} | Strategy: {self.strategy_name}")
                log.info("-" * 80)
                
                # 1. Check portfolio value and drawdown
                portfolio_value = self.get_portfolio_value()
                if portfolio_value:
                    log.info(f"📊 Portfolio Value: ${portfolio_value:,.2f}")
                    
                    # Check global drawdown
                    if self.trading_bot.check_global_drawdown(portfolio_value):
                        log.error("🛑 Trading stopped due to global drawdown limit!")
                        log.info("Waiting 60 seconds before checking again...")
                        time.sleep(60)
                        continue
                
                # 2. Fetch latest data
                log.info(f"📥 Fetching latest market data (Timeframe: {self.timeframe})...")
                df = self.get_latest_data()
                
                if df is None or len(df) == 0:
                    log.warning("⚠️  Failed to fetch data, retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                
                log.info(f"✓ Loaded {len(df)} data points from {self.timeframe} candles")
                
                # 3. Get current signal
                log.info(f"🔍 Analyzing {self.strategy_name} strategy on {self.timeframe} timeframe...")
                signal = self.get_current_signal(df)
                
                if signal is None:
                    log.warning("⚠️  Failed to get signal, retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                
                # 4. Display signal
                signal_names = {1: "🟢 LONG", -1: "🔴 SHORT", 0: "⚪ HOLD"}
                log.info(f"📊 Current Signal: {signal_names.get(signal, 'UNKNOWN')} ({signal})")
                
                # 5. Check if signal changed
                if signal != last_signal:
                    log.info(f"🔄 Signal changed: {signal_names.get(last_signal, 'None')} → {signal_names.get(signal, 'UNKNOWN')}")
                    last_signal = signal
                else:
                    log.info(f"ℹ️  Signal unchanged: {signal_names.get(signal, 'UNKNOWN')}")
                
                # 6. Get current price
                current_price = self.trading_bot.get_current_price()
                if current_price:
                    log.info(f"💰 Current Price: ${current_price:,.2f}")
                
                # 7. Check existing positions
                trading_config = config.load_trading_config()
                hedge_mode = trading_config.get('hedge_mode', False)
                
                if hedge_mode:
                    # Count both long and short positions separately in hedge mode
                    active_count = 0
                    for sym_pos in self.trading_bot.positions.values():
                        if isinstance(sym_pos, dict):
                            if sym_pos.get('long') is not None:
                                active_count += 1
                            if sym_pos.get('short') is not None:
                                active_count += 1
                        elif sym_pos is not None:
                            active_count += 1
                    active_positions = active_count
                else:
                    active_positions = len([p for p in self.trading_bot.positions.values() if p is not None])
                
                log.info(f"📈 Active Positions: {active_positions}/{config.MAX_CONCURRENT_TRADES}")
                if hedge_mode:
                    # Show detailed position breakdown
                    for symbol, sym_pos in self.trading_bot.positions.items():
                        if isinstance(sym_pos, dict):
                            long_pos = sym_pos.get('long')
                            short_pos = sym_pos.get('short')
                            if long_pos or short_pos:
                                pos_info = []
                                if long_pos:
                                    pos_info.append(f"LONG: {long_pos['size']:.6f} @ ${long_pos['entry_price']:,.2f}")
                                if short_pos:
                                    pos_info.append(f"SHORT: {short_pos['size']:.6f} @ ${short_pos['entry_price']:,.2f}")
                                if pos_info:
                                    log.info(f"   {symbol}: {', '.join(pos_info)}")
                
                # 8. Check stop loss / take profit for existing positions (always check, regardless of signal)
                if current_price:
                    closed = self.trading_bot.check_stop_loss_take_profit(current_price)
                    if closed:
                        log.info(f"✓ Closed {len(closed)} position(s) due to stop loss/take profit")
                
                # 8. Execute signal (including exit signal = 0)
                if signal == 0:
                    # Strategy exit signal: Close any existing position
                    log.info(f"🔄 Strategy exit signal (HOLD) detected")
                    if portfolio_value:
                        success = self.trading_bot.execute_signal(signal, current_price, portfolio_value)
                        if success:
                            log.info("✅ Position closed due to strategy exit signal")
                        else:
                            log.info("ℹ️  No position to close (or already closed)")
                    else:
                        # Try to close position even if portfolio value unavailable
                        success = self.trading_bot.execute_signal(signal, current_price, None)
                        if success:
                            log.info("✅ Position closed due to strategy exit signal")
                        else:
                            log.info("ℹ️  No position to close (or already closed)")
                elif signal != 0:
                    # Entry signal: Open new position
                    log.info(f"🎯 Executing signal: {signal_names.get(signal, 'UNKNOWN')}")
                    
                    # Execute new signal
                    if portfolio_value:
                        success = self.trading_bot.execute_signal(signal, current_price, portfolio_value)
                        if success:
                            log.info("✅ Trade executed successfully!")
                        else:
                            log.info("ℹ️  Trade not executed (may already be in position or other reason)")
                    else:
                        log.warning("⚠️  Cannot execute trade: Portfolio value unavailable (balance fetch failed)")
                        log.warning("   Attempting to execute trade anyway (using default portfolio value)...")
                        # Try to execute anyway with a default portfolio value for risk calculation
                        default_portfolio = config.TOTAL_PORTFOLIO_CAPITAL_USD
                        success = self.trading_bot.execute_signal(signal, current_price, default_portfolio)
                        if success:
                            log.info("✅ Trade executed successfully!")
                        else:
                            log.warning("⚠️  Trade execution failed - check logs above for details")
                
                # 9. Wait before next check with connection monitoring
                log.info("")
                log.info(f"⏳ Waiting {self.check_interval} seconds until next check...")
                log.info("")
                
                # Countdown with periodic connection checks
                wait_start = time.time()
                check_connection_every = 30  # Check connection every 30 seconds during wait
                last_connection_check = 0
                
                while time.time() - wait_start < self.check_interval:
                    remaining = int(self.check_interval - (time.time() - wait_start))
                    
                    # Check connection periodically during wait
                    if time.time() - last_connection_check >= check_connection_every:
                        try:
                            # Quick connection check
                            balance = self.trading_bot.get_balance()
                            current_price = self.trading_bot.get_current_price()
                            if balance is not None and current_price is not None:
                                log.info(f"   ✓ Connection OK | Remaining: {remaining}s | Price: ${current_price:,.2f}")
                            else:
                                log.warning(f"   ⚠️  Connection check failed | Remaining: {remaining}s")
                            last_connection_check = time.time()
                        except Exception as e:
                            log.warning(f"   ⚠️  Connection check error: {str(e)[:50]} | Remaining: {remaining}s")
                            last_connection_check = time.time()
                    
                    # Sleep in small increments to allow for responsive countdown
                    time.sleep(min(5, remaining))
                
        except KeyboardInterrupt:
            log.info("")
            log.info("=" * 80)
            log.info("STOPPING TRADING BOT")
            log.info("=" * 80)
            log.info("Received interrupt signal (Ctrl+C)")
            
            # Close all positions if requested
            response = input("Close all open positions? (y/n): ").lower().strip()
            if response == 'y':
                closed = self.trading_bot.close_all_positions()
                log.info(f"✓ Closed {closed} position(s)")
            
            log.info("✅ Bot stopped successfully")
            
        except Exception as e:
            log.error(f"❌ Error in main loop: {e}")
            import traceback
            traceback.print_exc()


def run_strategy_trading(strategy_name: str, data_path: str, symbol: str = 'BTC/USDT', 
                        use_demo: bool = True, test_mode: bool = True):
    """
    Run a strategy and execute trades based on signals
    
    Args:
        strategy_name: Name of strategy ('Bollinger_Bands', 'Moving_Average', 'RSI')
        data_path: Path to historical data CSV
        symbol: Trading pair
        use_demo: Use demo trading account
        test_mode: If True, only simulate trades (don't place real orders)
    """
    log.info("=" * 80)
    log.info("STRATEGY TRADING IMPLEMENTATION")
    log.info("=" * 80)
    log.info(f"Strategy: {strategy_name}")
    log.info(f"Symbol: {symbol}")
    log.info(f"Mode: {'DEMO' if use_demo else 'LIVE'}")
    log.info(f"Test Mode: {test_mode}")
    log.info("=" * 80)
    
    # Import analyzer to get strategy signals
    from Connection.analyzer import compare_strategies, load_data
    
    # Load data
    log.info("Loading historical data...")
    df = load_data(data_path)
    log.info(f"✓ Loaded {len(df)} data points")
    
    # Get strategy results
    log.info("Running strategy analysis...")
    results = compare_strategies(data_path)
    
    if not results:
        log.error("❌ Failed to get strategy results")
        return
    
    # Get the specific strategy
    strategy_key = strategy_name.replace(' ', '_')
    if strategy_key not in results['results']:
        log.error(f"❌ Strategy '{strategy_name}' not found in results")
        log.info(f"Available strategies: {list(results['results'].keys())}")
        return
    
    strategy_metrics = results['results'][strategy_key]
    log.info(f"✓ Strategy loaded: {strategy_metrics['strategy_name']}")
    log.info(f"  ROI: {strategy_metrics['roi']*100:.2f}%")
    log.info(f"  Sharpe: {strategy_metrics['sharpe_ratio']:.4f}")
    log.info(f"  Total Trades: {strategy_metrics['total_trades']}")
    
    # Initialize trading bot
    if test_mode:
        log.info("🧪 TEST MODE: Simulating trades (no real orders)")
        bot = None  # In test mode, we'll just simulate
    else:
        log.info("⚠️  LIVE MODE: Will place real orders!")
        bot = TradingBot(symbol=symbol, use_demo=use_demo)
    
    # Get signals from strategy (we need to re-run to get signals)
    # For now, we'll use the strategy wrapper functions directly
    from Connection.analyzer import run_bb_strategy, run_ma_strategy, run_rsi_strategy
    
    strategy_funcs = {
        'Bollinger_Bands': run_bb_strategy,
        'Moving_Average': run_ma_strategy,
        'RSI': run_rsi_strategy
    }
    
    if strategy_key not in strategy_funcs:
        log.error(f"❌ Strategy function not found for {strategy_key}")
        return
    
    log.info("Generating trading signals...")
    metrics, strategy_df = strategy_funcs[strategy_key](df)
    
    if strategy_df is None:
        log.error("❌ Failed to generate strategy signals")
        return
    
    # Get signals
    signals = strategy_df['Signal'].fillna(0)
    
    # Simulate trading using config.py risk management
    log.info("=" * 80)
    log.info("TRADING SIMULATION")
    log.info("=" * 80)
    
    # Use config.py capital and risk parameters
    initial_balance = float(config.TOTAL_PORTFOLIO_CAPITAL_USD)
    balance = float(initial_balance)
    peak_balance = float(initial_balance)
    
    # Track positions (support multiple concurrent trades)
    positions = {}  # {symbol: {'side': 1/-1, 'size': float, 'entry': float, 'sl': float, 'tp': float}}
    stop_loss_pct = 0.02  # 2% stop loss
    take_profit_pct = 0.04  # 4% take profit
    
    trades = []
    equity_curve = [initial_balance]
    trading_stopped = False  # Global kill switch flag
    
    for i in range(len(signals)):
        current_price = float(strategy_df['close'].iloc[i])
        signal = int(signals.iloc[i])
        
        # Check global drawdown limit (kill switch)
        if balance < peak_balance:
            drawdown = (peak_balance - balance) / peak_balance
            if drawdown >= config.GLOBAL_DRAWDOWN_LIMIT_PERCENT:
                if not trading_stopped:
                    log.error(f"🛑 GLOBAL DRAWDOWN LIMIT EXCEEDED at index {i}!")
                    log.error(f"   Current: ${balance:,.2f}, Peak: ${peak_balance:,.2f}")
                    log.error(f"   Drawdown: {drawdown*100:.2f}% (Limit: {config.GLOBAL_DRAWDOWN_LIMIT_PERCENT*100:.2f}%)")
                    log.error(f"   ⚠️  ALL TRADING STOPPED - KILL SWITCH ACTIVATED")
                    trading_stopped = True
        
        if trading_stopped:
            # Close all positions and stop trading
            if symbol in positions and positions[symbol] is not None:
                pos = positions[symbol]
                balance = float(balance + (pos['size'] * float(current_price) if pos['side'] == 1 else pos['size'] * float(pos['entry'])))
                positions[symbol] = None
            continue
        
        # Update peak balance
        if balance > peak_balance:
            peak_balance = balance
        
        # Check stop loss / take profit for existing position
        if symbol in positions and positions[symbol] is not None:
            pos = positions[symbol]
            current_price_float = float(current_price)
            
            # Check stop loss
            if (pos['side'] == 1 and current_price_float <= float(pos['sl'])) or \
               (pos['side'] == -1 and current_price_float >= float(pos['sl'])):
                log.info(f"🛑 Stop loss at {i}: ${current_price_float:.2f} <= ${float(pos['sl']):.2f}")
                balance = float(balance + (pos['size'] * current_price_float if pos['side'] == 1 else pos['size'] * float(pos['entry'])))
                positions[symbol] = None
            
            # Check take profit
            elif (pos['side'] == 1 and current_price_float >= float(pos['tp'])) or \
                 (pos['side'] == -1 and current_price_float <= float(pos['tp'])):
                log.info(f"🎯 Take profit at {i}: ${current_price_float:.2f} >= ${float(pos['tp']):.2f}")
                balance = float(balance + (pos['size'] * current_price_float if pos['side'] == 1 else pos['size'] * float(pos['entry'])))
                positions[symbol] = None
        
        # Check max concurrent trades
        active_positions = len([p for p in positions.values() if p is not None])
        if active_positions >= config.MAX_CONCURRENT_TRADES:
            continue  # Skip opening new position
        
        # Execute new signal
        if signal != 0:
            current_price_float = float(current_price)
            
            # Close opposite position if exists
            if symbol in positions and positions[symbol] is not None:
                existing_pos = positions[symbol]
                if signal != existing_pos['side']:
                    balance = float(balance + (existing_pos['size'] * current_price_float if existing_pos['side'] == 1 else existing_pos['size'] * float(existing_pos['entry'])))
                    positions[symbol] = None
                else:
                    continue  # Already in same position
            
            # Calculate stop loss and take profit prices
            if signal == 1:  # Long
                stop_loss_price = current_price_float * (1 - stop_loss_pct)
                take_profit_price = current_price_float * (1 + take_profit_pct)
            else:  # Short
                stop_loss_price = current_price_float * (1 + stop_loss_pct)
                take_profit_price = current_price_float * (1 - take_profit_pct)
            
            # Calculate position size using config.py risk management
            position_size = config.calculate_position_size(
                symbol=symbol,
                entry_price=current_price_float,
                stop_loss_price=stop_loss_price
            )
            
            if position_size > 0:
                cost = position_size * current_price_float
                if cost <= balance:  # Check if we have enough balance
                    balance = float(balance - cost)
                    
                    positions[symbol] = {
                        'side': signal,
                        'size': float(position_size),
                        'entry': current_price_float,
                        'sl': stop_loss_price,
                        'tp': take_profit_price
                    }
                    
                    trades.append({
                        'index': i,
                        'time': strategy_df.index[i],
                        'signal': signal,
                        'price': current_price_float,
                        'size': float(position_size),
                        'balance': balance,
                        'stop_loss': stop_loss_price,
                        'take_profit': take_profit_price
                    })
                    
                    log.info(f"📝 Trade {len(trades)}: {'LONG' if signal == 1 else 'SHORT'} {position_size:.6f} @ ${current_price_float:.2f}")
                    log.info(f"   Risk: ${config.TOTAL_PORTFOLIO_CAPITAL_USD * config.RISK_PER_TRADE_PERCENT:.2f} ({config.RISK_PER_TRADE_PERCENT*100:.2f}%)")
        
        # Update equity curve
        current_equity = float(balance)
        for pos in positions.values():
            if pos is not None:
                if pos['side'] == 1:
                    current_equity += float(pos['size']) * float(current_price)
                else:
                    current_equity += float(pos['size']) * float(pos['entry'])  # For short, use entry price
        equity_curve.append(float(current_equity))
    
    # Close final positions
    final_price = float(strategy_df['close'].iloc[-1])
    for sym, pos in positions.items():
        if pos is not None:
            balance = float(balance + (pos['size'] * final_price if pos['side'] == 1 else pos['size'] * float(pos['entry'])))
    equity_curve[-1] = float(balance)
    
    # Results - ensure we have scalar values, not numpy arrays
    final_balance = float(equity_curve[-1])
    total_return = float((final_balance - initial_balance) / initial_balance)
    
    log.info("=" * 80)
    log.info("TRADING RESULTS")
    log.info("=" * 80)
    log.info(f"Initial Balance: ${initial_balance:,.2f}")
    log.info(f"Final Balance: ${final_balance:,.2f}")
    log.info(f"Total Return: {total_return*100:.2f}%")
    log.info(f"Total Trades: {len(trades)}")
    log.info(f"Risk per Trade: {config.RISK_PER_TRADE_PERCENT*100:.2f}% (${config.TOTAL_PORTFOLIO_CAPITAL_USD * config.RISK_PER_TRADE_PERCENT:.2f})")
    log.info(f"Max Concurrent Trades: {config.MAX_CONCURRENT_TRADES}")
    log.info(f"Global Drawdown Limit: {config.GLOBAL_DRAWDOWN_LIMIT_PERCENT*100:.2f}%")
    if trading_stopped:
        log.warning("⚠️  Trading was stopped due to global drawdown limit!")
    log.info("=" * 80)
    
    return {
        'initial_balance': initial_balance,
        'final_balance': final_balance,
        'total_return': total_return,
        'trades': trades,
        'equity_curve': equity_curve
    }


def run_live_bot(strategy_name: str = None, symbol: str = None, 
                 use_demo: bool = None, check_interval: int = None, timeframe: str = None):
    """
    Run the live trading bot (monitors for signals and executes trades)
    
    Args:
        strategy_name: Strategy to use
        symbol: Trading pair
        use_demo: Use demo trading (None = auto-detect from config)
        check_interval: How often to check for signals (seconds)
        timeframe: Timeframe for OHLCV data (e.g., '1m', '5m', '15m', '1h', '4h', '1d')
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Auto-detect from config if not explicitly set
    if use_demo is None:
        use_demo = (config.ENVIRONMENT == 'DEMO')
    
    # Load config to show what will be used (if not provided via args)
    trading_config = config.load_trading_config()
    actual_strategy = strategy_name or trading_config.get('strategy', 'Bollinger_Bands')
    actual_symbol = symbol or trading_config.get('symbol', 'BTC/USDT')
    actual_timeframe = timeframe or trading_config.get('timeframe', '1h')
    actual_interval = check_interval or trading_config.get('check_interval', 60)
    
    # Confirm settings
    log.info("=" * 80)
    log.info("TRADING BOT CONFIGURATION")
    log.info("=" * 80)
    log.info(f"Strategy: {actual_strategy} {'(from config)' if strategy_name is None else '(from command line)'}")
    log.info(f"Symbol: {actual_symbol} {'(from config)' if symbol is None else '(from command line)'}")
    log.info(f"Timeframe: {actual_timeframe} {'(from config)' if timeframe is None else '(from command line)'}")
    log.info(f"Mode: {'DEMO TRADING (Safe for Testing)' if use_demo else '⚠️  LIVE TRADING (Real Money!)'}")
    log.info(f"Check Interval: {actual_interval} seconds {'(from config)' if check_interval is None else '(from command line)'}")
    log.info(f"Config Environment: {config.ENVIRONMENT}")
    log.info("=" * 80)
    
    # Safety check for LIVE trading
    if not use_demo:
        log.warning("")
        log.warning("⚠️  ⚠️  ⚠️  WARNING: LIVE TRADING MODE ⚠️  ⚠️  ⚠️")
        log.warning("This will use REAL MONEY and execute REAL TRADES!")
        log.warning("")
        response = input("Type 'YES' (all caps) to continue with LIVE trading: ").strip()
        if response != 'YES':
            log.info("Cancelled by user. Switching to DEMO mode for safety...")
            use_demo = True
            log.info("✅ Now using DEMO trading mode (safe for testing)")
    else:
        log.info("✅ Using DEMO trading mode - Safe for testing!")
        log.info("   (No real money will be used)")
    
    # Initialize and run bot
    try:
        bot = LiveTradingBot(
            strategy_name=strategy_name,
            symbol=symbol,
            use_demo=use_demo,
            check_interval=check_interval,
            timeframe=timeframe
        )
        bot.run()
    except Exception as e:
        log.error(f"❌ Failed to start bot: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Check command line arguments to determine mode
    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        # Live trading bot mode
        # Usage: python trading_implementation.py --live [strategy] [symbol] [timeframe] [check_interval]
        # If arguments are not provided, will read from trading_config.json
        
        # Load config first to use as defaults
        trading_config = config.load_trading_config()
        
        strategy_name = sys.argv[2] if len(sys.argv) > 2 else None
        symbol = sys.argv[3] if len(sys.argv) > 3 else None
        timeframe = sys.argv[4] if len(sys.argv) > 4 else None
        check_interval = int(sys.argv[5]) if len(sys.argv) > 5 else None
        use_demo = False if len(sys.argv) > 6 and sys.argv[6] == '--live' else None
        
        run_live_bot(strategy_name=strategy_name, symbol=symbol, 
                    use_demo=use_demo, check_interval=check_interval, timeframe=timeframe)
    else:
        # Simulation mode (default) - uses historical CSV data
        # NOTE: Simulation mode uses hardcoded CSV file (1h data)
        # For timeframe control from trading_config.json, use --live mode instead
        
        # Load config to show what would be used in live mode
        trading_config = config.load_trading_config()
        
        default_data_path = "/Users/bryanlew/Document/AlgoCrypto/Backend/Data/bybit_btc_1h_20210101_20241231.csv"
        
        # Get strategy name from command line, config, or use default
        if len(sys.argv) > 1:
            strategy_name = sys.argv[1]
        else:
            strategy_name = trading_config.get('strategy', 'Bollinger_Bands')
        
        symbol = trading_config.get('symbol', 'BTC/USDT')
        
        log.info("=" * 80)
        log.info("SIMULATION MODE (Historical Data)")
        log.info("=" * 80)
        log.info(f"Strategy: {strategy_name} {'(from config)' if len(sys.argv) == 1 else '(from command line)'}")
        log.info(f"Symbol: {symbol} (from config)")
        log.info(f"Data Source: {default_data_path}")
        log.info("⚠️  NOTE: Simulation uses 1h historical CSV data")
        log.info("   For timeframe control (e.g., 1m from trading_config.json), use --live mode:")
        log.info("   python trading_implementation.py --live")
        log.info("=" * 80)
        log.info("")
        
        # Run trading simulation
        results = run_strategy_trading(
            strategy_name=strategy_name,
            data_path=default_data_path,
            symbol=symbol,
            use_demo=True,
            test_mode=True  # Set to False for real trading (USE WITH CAUTION!)
        )
        
        if results:
            log.info("✅ Trading simulation completed successfully!")
            log.info("")
            log.info("=" * 80)
            log.info("TO USE TIMEFRAME FROM trading_config.json:")
            log.info("=" * 80)
            log.info("Run with --live flag (reads from trading_config.json):")
            log.info("  python trading_implementation.py --live")
            log.info("")
            log.info("This will use:")
            log.info(f"  - Strategy: {trading_config.get('strategy', 'Bollinger_Bands')} (from config)")
            log.info(f"  - Symbol: {trading_config.get('symbol', 'BTC/USDT')} (from config)")
            log.info(f"  - Timeframe: {trading_config.get('timeframe', '1h')} (from config)")
            log.info(f"  - Check Interval: {trading_config.get('check_interval', 60)}s (from config)")
            log.info("")
            log.info("Or override with command line arguments:")
            log.info("  python trading_implementation.py --live [strategy] [symbol] [timeframe] [interval]")
            log.info("")
            log.info("Examples:")
            log.info("  python trading_implementation.py --live")
            log.info("  python trading_implementation.py --live Bollinger_Bands BTC/USDT 1m 60")
            log.info("=" * 80)

