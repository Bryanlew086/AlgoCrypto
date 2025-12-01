import ccxt
import logging
import os
import sys
import time
import hmac
import hashlib
import requests
from pathlib import Path # Import Path for finding files

# --- Robust Pathing ---
# This ensures Python finds your 'config.py' file
# It adds the script's own folder ('/Connection/') to the path
script_dir = Path(__file__).parent
sys.path.append(str(script_dir))

try:
    import config  # This imports your config.py file
except ImportError:
    print(f"CRITICAL ERROR: Could not find config.py in the directory: {script_dir}")
    print("Make sure config.py is in the same folder as this script.")
    sys.exit(1)
# ----------------------


# 1. Configure Logging
logging.basicConfig(level=config.LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger()

def test_demo_connection():
    """
    Connects to Bybit and runs read-only tests.
    Supports:
    - DEMO: Bybit Demo Trading or Testnet
    - LIVE: Real trading with real money (WARNING!)
    """
    if config.ENVIRONMENT == 'LIVE':
        log.error("="*70)
        log.error("⚠️  ⚠️  ⚠️  LIVE TRADING MODE - REAL MONEY ⚠️  ⚠️  ⚠️")
        log.error("="*70)
        log.error("You are about to connect to LIVE trading with REAL MONEY!")
        log.error("Make sure:")
        log.error("  1. You understand the risks")
        log.error("  2. Your API keys have proper permissions")
        log.error("  3. You have tested your strategies thoroughly")
        log.error("  4. You have proper risk management in place")
        log.error("="*70)
        log.info("")
    
    log.info(f"Attempting to connect to Bybit {config.ENVIRONMENT} environment...")
    if config.ENVIRONMENT == 'DEMO':
        log.info("Note: Demo trading on main Bybit site uses regular endpoints (not sandbox)")
        log.info("      Testnet uses sandbox mode with testnet.bybit.com endpoints")
    else:
        log.info("⚠️  LIVE TRADING: Using real Bybit API with real funds")

    # --- Pre-flight Check ---
    if not config.API_KEY or not config.API_SECRET:
        log.error("="*60)
        log.error("CRITICAL ERROR: API_KEY or API_SECRET is not set in your .env file.")
        log.error("="*60)
        log.error("SETUP INSTRUCTIONS:")
        log.error("1. Create/update .env file in the Backend/Connection/ directory")
        if config.ENVIRONMENT == 'LIVE':
            log.error("2. Add the following lines with your Bybit LIVE API keys:")
            log.error("   BYBIT_ENVIRONMENT=LIVE")
            log.error("   BYBIT_API_KEY_LIVE=your_live_api_key_here")
            log.error("   BYBIT_API_SECRET_LIVE=your_live_api_secret_here")
            log.error("   ⚠️  WARNING: These are REAL trading keys with REAL MONEY!")
        else:
            log.error("2. Add the following lines with your Bybit Demo API keys:")
            log.error("   BYBIT_ENVIRONMENT=DEMO")
            log.error("   BYBIT_API_KEY_DEMO=your_demo_api_key_here")
            log.error("   BYBIT_API_SECRET_DEMO=your_demo_api_secret_here")
        log.error("3. Make sure there are NO spaces around the = sign")
        log.error("4. Save the file and run this script again")
        log.error("="*60)
        sys.exit(1) # Exit the script
    
    # Validate API key format
    api_key_len = len(config.API_KEY)
    api_secret_len = len(config.API_SECRET)
    
    log.info("✅ API keys loaded successfully from .env file.")
    log.info(f"Verifying API Key (first 5 chars): {config.API_KEY[:5]}")
    log.info(f"API Key length: {api_key_len} characters")
    log.info(f"API Secret length: {api_secret_len} characters")
    
    # Test API keys directly with Bybit REST API (both main and testnet)
    log.info("")
    log.info("="*60)
    log.info("Testing API keys directly with Bybit REST API...")
    log.info("="*60)
    
    api_key = config.API_KEY
    api_secret = config.API_SECRET
    
    # Test URLs based on environment
    if config.ENVIRONMENT == 'DEMO':
        # Demo trading uses api-demo.bybit.com according to Bybit docs
        test_urls = [
            ("Demo Trading (api-demo.bybit.com)", "https://api-demo.bybit.com"),
            ("Main Site (fallback)", "https://api.bybit.com"),
        ]
    else:
        # Live trading uses regular api.bybit.com
        test_urls = [
            ("Live Trading (api.bybit.com)", "https://api.bybit.com"),
        ]
    
    keys_work = False
    working_url = None
    
    for name, base_url in test_urls:
        try:
            log.info(f"Testing against {name}...")
            
            # Prepare request - Bybit V5 API signature format
            # Signature = HMAC_SHA256(timestamp + api_key + recv_window + query_string, secret)
            timestamp = str(int(time.time() * 1000))
            recv_window = "5000"
            
            # For GET requests, query_string is the sorted query parameters
            # Format: key1=value1&key2=value2 (sorted by key)
            query_string = "accountType=UNIFIED"
            
            # Build the string for signature: timestamp + api_key + recv_window + query_string
            sign_string = timestamp + api_key + recv_window + query_string
            
            # Generate signature
            signature = hmac.new(
                api_secret.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            url = f"{base_url}/v5/account/wallet-balance"
            headers = {
                'X-BAPI-API-KEY': api_key,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recv_window,
            }
            
            # Query parameters (only accountType, others are in headers)
            response = requests.get(url, headers=headers, params={'accountType': 'UNIFIED'}, timeout=10)
            log.info(f"  Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                log.info(f"  Response: {response.text[:150]}")
                
                if data.get('retCode') == 0:
                    log.info(f"✅ SUCCESS! Keys work with {name}")
                    keys_work = True
                    working_url = base_url
                    break
                else:
                    ret_code = data.get('retCode')
                    ret_msg = data.get('retMsg', 'Unknown')
                    log.warning(f"  ❌ {name} rejected keys: {ret_msg} (code: {ret_code})")
                    
                    # Special handling for specific error codes
                    if ret_code == 10010:
                        log.error("")
                        log.error("  🔍 DETECTED: IP Whitelist Error (10010)")
                        log.error("  This means your API key has IP restrictions enabled.")
                        log.error("  SOLUTION:")
                        log.error("  1. Go to Bybit.com → Account → API → Demo Trading")
                        log.error("  2. Click on your API key")
                        log.error("  3. Find 'IP Whitelist' setting")
                        log.error("  4. Either DISABLE it OR add your current IP address")
                        log.error("  5. Check your IP: https://whatismyipaddress.com/")
                        log.error("")
                    elif ret_code == 10032:
                        log.error("")
                        log.error("  🔍 DETECTED: Demo Trading Not Supported (10032)")
                        log.error("  This endpoint doesn't support demo trading.")
                        log.error("  Note: Some endpoints work with demo, others don't.")
                        log.error("  The /v5/account/wallet-balance endpoint should work.")
                        log.error("")
                    elif ret_code == 10004:
                        log.error("")
                        log.error("  🔍 DETECTED: Signature Error (10004)")
                        log.error("  The API signature is incorrect.")
                        log.error("  This might be a bug in the signature generation.")
                        log.error("")
            else:
                log.warning(f"  ⚠️  {name} returned status {response.status_code}")
                
        except Exception as e:
            log.warning(f"  ⚠️  {name} test exception: {str(e)[:100]}")
    
    log.info("="*60)
    if not keys_work:
        log.error("")
        log.error("="*60)
        log.error("❌ API KEYS ARE INVALID OR FROM WRONG ENVIRONMENT")
        log.error("="*60)
        if config.ENVIRONMENT == 'DEMO':
            log.error("TROUBLESHOOTING DEMO TRADING KEYS:")
            log.error("")
            log.error("According to Bybit docs: https://bybit-exchange.github.io/docs/v5/demo")
            log.error("Demo trading uses: https://api-demo.bybit.com (NOT api.bybit.com)")
            log.error("")
            log.error("1. Verify Demo Trading API Key Creation:")
            log.error("   - Log in to mainnet account (bybit.com)")
            log.error("   - Switch to 'Demo Trading' tab (independent account)")
            log.error("   - Hover user avatar → Click 'API' → Generate key")
            log.error("   - Make sure key is created from Demo Trading, not Live Trading")
            log.error("")
            log.error("2. Check IP Whitelist:")
            log.error("   - Go to Bybit.com → Account → API → Demo Trading → Your Key")
            log.error("   - Make sure 'IP Whitelist' is DISABLED (or add your current IP)")
            log.error("   - Your current IP: https://whatismyipaddress.com/")
            log.error("")
            log.error("3. Verify Key Permissions:")
            log.error("   - Key must have at least 'Read' permission")
            log.error("   - Check all permission checkboxes are correct")
            log.error("")
            log.error("4. Wait for Key Activation:")
            log.error("   - New keys can take 1-5 minutes to activate")
            log.error("   - Try waiting a few minutes and test again")
            log.error("")
            log.error("5. Verify Key Format in .env:")
            log.error("   - Make sure: BYBIT_ENVIRONMENT=DEMO")
            log.error("   - Check key length and format (no spaces, quotes, or line breaks)")
        else:
            log.error("TROUBLESHOOTING LIVE TRADING KEYS:")
            log.error("")
            log.error("1. Check IP Whitelist:")
            log.error("   - Go to Bybit.com → Account → API → Live Trading → Your Key")
            log.error("   - Make sure 'IP Whitelist' is DISABLED (or add your current IP)")
            log.error("")
            log.error("2. Verify Key Permissions:")
            log.error("   - Key must have at least 'Read' permission")
            log.error("   - For trading: Enable 'Trade' permission")
            log.error("")
        log.error("="*60)
        log.error("")
    else:
        log.info(f"✅ Keys validated! Working with: {working_url}")
        log.info("")
    
    log.info("")
    
    # Warn if keys seem too short (but demo trading keys can be shorter)
    if api_key_len < 15:
        log.error("="*60)
        log.error("⚠️  WARNING: API Key appears to be too short!")
        log.error(f"   Current length: {api_key_len} characters")
        log.error("   Minimum expected: 15 characters")
        log.error("")
        log.error("   This usually means:")
        log.error("   1. The key was not copied completely")
        log.error("   2. There are hidden characters or line breaks")
        log.error("   3. The key format is incorrect")
        log.error("")
        log.error("   SOLUTION:")
        log.error("   1. Go to Bybit → Account → API → Demo Trading")
        log.error("   2. Create a NEW API key (or view existing one)")
        log.error("   3. Copy the ENTIRE key")
        log.error("   4. Paste it in your .env file on a SINGLE line")
        log.error("   5. Make sure there are no spaces or line breaks")
        log.error("="*60)
        log.error("Continuing anyway, but authentication will likely fail...")
        log.error("="*60)
    elif api_key_len < 30:
        log.info(f"ℹ️  API Key length: {api_key_len} chars (Demo Trading keys are typically 15-20 chars)")

    # 1. Initialize the CCXT Exchange
    exchange = None
    
    if config.ENVIRONMENT == 'LIVE':
        # Live trading uses regular api.bybit.com
        log.info("Initializing Live Trading connection...")
        exchange = ccxt.bybit({
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'sandbox': False,
            'options': {
                'defaultType': 'linear',
            },
            'enableRateLimit': True,
        })
        log.info(f"API Base URL: {exchange.urls['api']['public']}")
        log.info("✅ Successfully configured for Live Trading")
    else:
        # Demo trading uses api-demo.bybit.com (different domain!)
        # Per Bybit docs: https://bybit-exchange.github.io/docs/v5/demo
        log.info("Initializing Demo Trading connection...")
        log.info("Note: Demo trading uses api-demo.bybit.com (not api.bybit.com)")
        log.info("Reference: https://bybit-exchange.github.io/docs/v5/demo")
        
        exchange = ccxt.bybit({
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'sandbox': False,  # Demo trading is NOT sandbox, it's a different domain
            'options': {
                'defaultType': 'linear',
            },
            'enableRateLimit': True,
        })

        # Override URLs to use demo domain (per Bybit docs)
        # Demo trading MUST use api-demo.bybit.com
        exchange.urls = {
            'api': {
                'public': 'https://api-demo.bybit.com',
                'private': 'https://api-demo.bybit.com',
                'rest': 'https://api-demo.bybit.com',
            },
            'www': 'https://www.bybit.com',
            'doc': ['https://bybit-exchange.github.io/docs/v5/demo'],
        }
        
        # Also set the base URL directly if CCXT supports it
        if hasattr(exchange, 'urls'):
            exchange.base_url = 'https://api-demo.bybit.com'
        
        log.info(f"API Base URL: {exchange.urls['api']['public']}")
        log.info("✅ Successfully configured for Demo Trading (api-demo.bybit.com)")
    
    if exchange is None:
        log.error("Failed to initialize exchange")
        sys.exit(1)
    
    try:
        log.info("Successfully instantiated CCXT. Checking connection...")

        # --- TEST 0: Public API Test (No Auth Required) ---
        log.info("TEST 0: Testing Public API (no auth required)...")
        try:
            ticker_public = exchange.fetch_ticker('BTC/USDT')
            log.info(f"✅ Public API OK: BTC Price = ${ticker_public['last']}")
        except Exception as e:
            error_str = str(e)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                log.info("ℹ️  Public API endpoints don't support demo trading (error 10032)")
                log.info("   This is normal - public market data uses regular API")
                log.info("   Private endpoints (balance, orders) use api-demo.bybit.com")
            else:
                log.warning(f"⚠️  Public API test failed: {e}")
                log.warning("This might indicate a network or URL issue.")

        # --- TEST 1: Try simple authenticated endpoint first ---
        log.info("TEST 1: Testing authentication with simple endpoint...")
        try:
            # Try to get account info - this is a simpler endpoint
            account_info = exchange.fetch_balance({'type': 'spot'})
            log.info("✅ Authentication successful with spot balance")
        except Exception as e:
            error_str = str(e)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                log.info("ℹ️  Spot balance endpoint doesn't support demo trading")
            else:
                log.warning(f"Spot balance failed: {e}")
            try:
                # Try linear/contracts
                account_info = exchange.fetch_balance({'type': 'linear'})
                log.info("✅ Authentication successful with linear balance")
            except Exception as e2:
                error_str2 = str(e2)
                if "10032" in error_str2 or "Demo trading are not supported" in error_str2:
                    log.info("ℹ️  Linear balance endpoint doesn't support demo trading")
                else:
                    log.warning(f"Linear balance also failed: {e2}")
                # Continue to main balance test
                pass
        
        # --- TEST 2: Fetch Balance (Proves Authentication) ---
        log.info("TEST 2: Fetching Account Balance...")
        try:
            balance = exchange.fetch_balance()
            
            if 'USDT' in balance.get('total', {}):
                usdt_balance = balance['total']['USDT']
                if usdt_balance > 0:
                    log.info(f"--- Balance: ${usdt_balance:.2f} USDT ({config.ENVIRONMENT})")
                else:
                    log.info(f"--- Balance: $0.00 USDT ({config.ENVIRONMENT}) - No funds, but connection works!")
            else:
                # Check other currencies or show total
                total_currencies = list(balance.get('total', {}).keys())
                if total_currencies:
                    log.info(f"--- Balance found for: {', '.join(total_currencies)}")
                else:
                    log.info("--- Balance: $0.00 - Account is empty, but authentication successful!")
            
            log.info("✅ Connection test PASSED - API keys are valid!")
        except Exception as e:
            error_str = str(e)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                log.warning("⚠️  CCXT's fetch_balance() doesn't work with demo trading (error 10032)")
                log.info("   Using direct API call as fallback...")
                
                # Fallback: Use direct API call (we know it works from the test above)
                try:
                    if working_url:
                        timestamp = str(int(time.time() * 1000))
                        recv_window = "5000"
                        query_string = "accountType=UNIFIED"
                        sign_string = timestamp + config.API_KEY + recv_window + query_string
                        signature = hmac.new(
                            config.API_SECRET.encode('utf-8'),
                            sign_string.encode('utf-8'),
                            hashlib.sha256
                        ).hexdigest()
                        
                        url = f"{working_url}/v5/account/wallet-balance"
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
                                result = data.get('result', {}).get('list', [{}])[0]
                                coin_list = result.get('coin', [])
                                usdt_coin = next((c for c in coin_list if c.get('coin') == 'USDT'), {})
                                usdt_balance = float(usdt_coin.get('walletBalance', 0))
                                
                                if usdt_balance > 0:
                                    log.info(f"--- Balance: ${usdt_balance:.2f} USDT ({config.ENVIRONMENT})")
                                else:
                                    log.info(f"--- Balance: $0.00 USDT ({config.ENVIRONMENT}) - No funds, but connection works!")
                                
                                log.info("✅ Connection test PASSED - API keys are valid!")
                                log.info("   (Using direct API call since CCXT doesn't support demo trading endpoints)")
                            else:
                                raise Exception(f"Direct API call failed: {data.get('retMsg')}")
                        else:
                            raise Exception(f"HTTP {response.status_code}")
                except Exception as fallback_error:
                    log.error("")
                    log.error("❌ Error 10032: Demo trading endpoint not supported")
                    log.error("")
                    log.error("CCXT's balance method doesn't work with demo trading.")
                    log.error("The direct API test above confirmed your keys are valid.")
                    log.error("")
                    log.error("According to Bybit docs, these endpoints work with demo trading:")
                    log.error("  - /v5/account/wallet-balance (should work)")
                    log.error("  - /v5/order/* (trading endpoints)")
                    log.error("  - /v5/position/* (position endpoints)")
                    log.error("")
                    log.error("Your API keys are valid - you can use direct API calls for demo trading.")
                    raise
            else:
                raise
        
        # --- TEST 3: Fetch Market Data (Proves Public API) ---
        log.info("TEST 3: Fetching Market Ticker for BTC/USDT...")
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            log.info(f"--- Ticker OK: Current BTC Price is ${ticker['last']}")
        except Exception as e:
            error_str = str(e)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                log.info("--- Ticker: Skipped (public endpoints don't support demo trading)")
            else:
                log.warning(f"--- Ticker failed: {e}")
        
        # --- TEST 4: Fetch Positions (Proves Trading API) ---
        log.info("TEST 4: Fetching Open Positions...")
        try:
            positions = exchange.fetch_positions(params={'type': 'linear'})
            open_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]
            log.info(f"--- Positions OK: You have {len(open_positions)} open positions.")
        except Exception as e:
            error_str = str(e)
            if "10032" in error_str or "Demo trading are not supported" in error_str:
                log.info("--- Positions: Skipped (CCXT positions endpoint doesn't support demo trading)")
                log.info("   You can use direct API calls to /v5/position/list for demo trading")
            else:
                log.warning(f"--- Positions failed: {e}")
        
        log.info("="*70)
        if config.ENVIRONMENT == 'LIVE':
            log.info("✅ SUCCESS: Connection to Bybit LIVE Account is working!")
            log.info("   Your API keys are valid and authenticated.")
            log.info("   You can now use this connection for trading.")
        else:
            log.info("✅ SUCCESS: Connection to Bybit Demo Account is stable.")
        log.info("="*70)

    except ccxt.AuthenticationError as e:
        log.error("="*60)
        log.error(f"❌ AUTHENTICATION FAILED: {e}")
        log.error("="*60)
        
        # Check for IP whitelist error (10010)
        error_str = str(e)
        if "10010" in error_str or "Unmatched IP" in error_str or "IP" in error_str:
            log.error("")
            log.error("🔍 DETECTED: IP Whitelist Error (10010)")
            log.error("Your API key has IP restrictions enabled.")
            log.error("")
            log.error("SOLUTION:")
            if config.ENVIRONMENT == 'DEMO':
                log.error("  1. Go to Bybit.com → Account → API → Demo Trading")
            else:
                log.error("  1. Go to Bybit.com → Account → API → Live Trading")
            log.error("  2. Click on your API key")
            log.error("  3. Find 'IP Whitelist' or 'Restrict Access to IP' setting")
            log.error("  4. Either DISABLE it OR add your current IP address")
            log.error("  5. Check your IP: https://whatismyipaddress.com/")
            log.error("  6. Save changes and wait 1-2 minutes for it to take effect")
            log.error("")
            log.error("="*60)
        
        log.error("TROUBLESHOOTING STEPS:")
        log.error("1. Verify your API keys are correct:")
        if config.ENVIRONMENT == 'DEMO':
            log.error("   - For DEMO TRADING: Get keys from main Bybit site (bybit.com)")
            log.error("     → Account → API → Demo Trading → Create API Key")
            log.error("   - Demo trading uses: https://api-demo.bybit.com")
        else:
            log.error("   - For LIVE TRADING: Get keys from main Bybit site (bybit.com)")
            log.error("     → Account → API → Live Trading → Create API Key")
        log.error("   - For TESTNET: Get keys from testnet.bybit.com")
        log.error("2. Check your .env file:")
        log.error(f"   - API Key starts with: {config.API_KEY[:5]}...")
        if config.ENVIRONMENT == 'DEMO':
            log.error(f"   - API Key length: {len(config.API_KEY)} characters (Demo keys: 15-20 chars)")
            log.error(f"   - API Secret length: {len(config.API_SECRET)} characters (Demo secrets: 30-40 chars)")
        else:
            log.error(f"   - API Key length: {len(config.API_KEY)} characters (Live keys: ~40-50 chars)")
            log.error(f"   - API Secret length: {len(config.API_SECRET)} characters (Live secrets: ~40-50 chars)")
        log.error("3. Verify API key permissions in Bybit dashboard:")
        log.error("   - Must have 'Read' permission at minimum")
        log.error("   - Check if IP whitelist is enabled (disable for testing)")
        if config.ENVIRONMENT == 'DEMO':
            log.error("4. Important: Demo Trading uses api-demo.bybit.com (NOT api.bybit.com)")
            log.error("   - Reference: https://bybit-exchange.github.io/docs/v5/demo")
        log.error("5. Double-check you copied the keys correctly:")
        log.error("   - No extra spaces before/after the = sign")
        log.error("   - No quotes around the values")
        log.error("   - Keys are from the correct account (demo vs live vs testnet)")
        log.error("="*60)
    except ccxt.NetworkError as e:
        log.error(f"❌ NETWORK FAILED: {e}")
        log.error("Could not connect to Bybit. Check your internet connection.")
    except Exception as e:
        log.error(f"❌ AN UNEXPECTED ERROR OCCURRED: {e}")

if __name__ == "__main__":
    log.info("="*60)
    log.info("Bybit Connection Test")
    log.info("="*60)
    log.info("")
    log.info("Testing Bybit API connection...")
    log.info("")
    log.info("="*60)
    log.info("")
    
    # Test real connection
    test_demo_connection()