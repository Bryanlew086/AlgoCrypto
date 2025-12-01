import os
import logging
from pathlib import Path
from dotenv import load_dotenv  # Imports the library to read .env

# --- Load .env from multiple possible locations ---
# Try Connection directory first, then Backend root
script_dir = Path(__file__).parent
backend_root = script_dir.parent

# Load .env from Connection directory (preferred)
env_file_connection = script_dir / '.env'
env_file_backend = backend_root / '.env'

if env_file_connection.exists():
    load_dotenv(env_file_connection)
    print(f"✅ Loaded .env from: {env_file_connection}")
elif env_file_backend.exists():
    load_dotenv(env_file_backend)
    print(f"✅ Loaded .env from: {env_file_backend}")
else:
    # Try default location (current directory)
    load_dotenv()
    print("⚠️  No .env file found in Connection/ or Backend/ directories")
    print("   Using default .env search (current directory)")
# --------------------------

# =============================================================================
# 1. ENVIRONMENT & API CONFIGURATION
# =============================================================================
# Set the master switch for the entire system.
# 'DEMO' uses Bybit demo URLs and keys. 'LIVE' uses REAL MONEY - BE CAREFUL!
# Change this to 'LIVE' only when you're ready to trade with real funds.
ENVIRONMENT = os.environ.get('BYBIT_ENVIRONMENT', 'DEMO').upper()  # Can be set in .env

# API Keys are now loaded from your .env file
# This code reads the variables that load_dotenv() just set.
if ENVIRONMENT == 'LIVE':
    API_KEY = os.environ.get('BYBIT_API_KEY_LIVE')
    API_SECRET = os.environ.get('BYBIT_API_SECRET_LIVE')
    print("⚠️  WARNING: LIVE TRADING MODE - Using REAL MONEY!")
    print("⚠️  Make sure you understand the risks before proceeding!")
else:
    API_KEY = os.environ.get('BYBIT_API_KEY_DEMO')
    API_SECRET = os.environ.get('BYBIT_API_SECRET_DEMO')

# Logging level for all bots
LOG_LEVEL = logging.INFO

# =============================================================================
# 2. CAPITAL & RISK PARAMETERS (THE "GLOBAL RULES")
# =============================================================================

# The total capital allocated to this portfolio (in USD)
TOTAL_PORTFOLIO_CAPITAL_USD = 100000

# The maximum % of TOTAL capital to risk on a SINGLE trade.
# 0.01 = 1% risk per trade.
RISK_PER_TRADE_PERCENT = 0.01

# The absolute maximum number of positions allowed open at any time.
MAX_CONCURRENT_TRADES = 5

# A "global kill switch." If total portfolio value drops by this %
# (e.g., 0.20 = 20%), all bots will be stopped.
GLOBAL_DRAWDOWN_LIMIT_PERCENT = 0.20

# =============================================================================
# 3. MARKET & ASSET UNIVERSE
# =============================================================================

# The *only* assets your strategies are allowed to trade.
TRADEABLE_ASSETS = [
    'BTC/USDT',
    
]

# Per-asset leverage settings
LEVERAGE_SETTINGS = {
    'BTC/USDT': 100,  # 10x leverage
    'DEFAULT': 1,     # Default leverage (1x = no leverage) for any other asset
}

def get_leverage(symbol):
    return LEVERAGE_SETTINGS.get(symbol, LEVERAGE_SETTINGS.get('DEFAULT', 1))

# =============================================================================
# 4. TRADING CONFIGURATION (Frontend-Controlled)
# =============================================================================
# These settings can be controlled by your frontend website
# The bot reads from trading_config.json file

import json
from datetime import datetime

def load_trading_config():
    """
    Load trading configuration from JSON file (can be updated by frontend)
    Returns default config if file doesn't exist or is invalid
    """
    script_dir = Path(__file__).parent
    config_file = script_dir / 'trading_config.json'
    
    default_config = {
        'timeframe': '1h',
        'strategy': 'Bollinger_Bands',
        'symbol': 'BTC/USDT',
        'check_interval': 60,
        'enabled': True,
        'quantity_btc': None,  # Fixed BTC quantity (None = use risk-based calculation)
        'last_updated': None
    }
    
    if not config_file.exists():
        # Create default config file
        try:
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"✅ Created default trading_config.json at {config_file}")
        except Exception as e:
            print(f"⚠️  Could not create trading_config.json: {e}")
        return default_config
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Validate and merge with defaults
        for key in default_config:
            if key not in config:
                config[key] = default_config[key]
        
        return config
    except Exception as e:
        print(f"⚠️  Error loading trading_config.json: {e}. Using defaults.")
        return default_config

def update_trading_config(**kwargs):
    """
    Update trading configuration (can be called by frontend API)
    
    Args:
        **kwargs: Configuration values to update (timeframe, strategy, symbol, etc.)
    
    Returns:
        Updated config dict
    """
    script_dir = Path(__file__).parent
    config_file = script_dir / 'trading_config.json'
    
    # Load current config
    current_config = load_trading_config()
    
    # Update with new values
    for key, value in kwargs.items():
        if key in current_config:
            current_config[key] = value
    
    # Add timestamp
    current_config['last_updated'] = datetime.now().isoformat()
    
    # Save to file
    try:
        with open(config_file, 'w') as f:
            json.dump(current_config, f, indent=2)
        print(f"✅ Updated trading_config.json: {kwargs}")
    except Exception as e:
        print(f"❌ Error updating trading_config.json: {e}")
    
    return current_config

# Load initial trading config
TRADING_CONFIG = load_trading_config()

# =============================================================================
# 5. POSITION SIZING ENGINE (THE "BRAIN")
# =============================================================================

def calculate_position_size(symbol, entry_price, stop_loss_price):
    """
    Calculates the exact position size based on the global risk rules.
    """
    
    # 1. Validation Check
    if symbol not in TRADEABLE_ASSETS:
        logging.warning(f"Trade DENIED: {symbol} is not in TRADEABLE_ASSETS list.")
        return 0.0
        
    if entry_price <= 0 or stop_loss_price <= 0:
        logging.error("Trade DENIED: Entry or Stop Loss price is zero.")
        return 0.0

    # 2. Calculate Risk Amount (in USD)
    risk_amount_usd = TOTAL_PORTFOLIO_CAPITAL_USD * RISK_PER_TRADE_PERCENT
    
    # 3. Calculate Stop-Loss Distance (in USD per coin)
    sl_distance_usd_per_coin = abs(entry_price - stop_loss_price)

    if sl_distance_usd_per_coin == 0:
        logging.warning("Trade DENIED: Stop-loss distance is zero.")
        return 0.0

    # 4. Calculate Position Size (in coins)
    position_size_in_coins = risk_amount_usd / sl_distance_usd_per_coin
    
    logging.info(f"Position Size Calculated: {position_size_in_coins:.6f} {symbol.split('/')[0]}")
    
    return position_size_in_coins