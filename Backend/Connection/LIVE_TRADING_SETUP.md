# Live Trading Setup Guide

## ⚠️ IMPORTANT WARNINGS

**LIVE TRADING USES REAL MONEY!**

- You can lose real funds
- Test your strategies thoroughly before going live
- Start with small amounts
- Use proper risk management
- Monitor your trades closely

## Step-by-Step Setup

### 1. Get Live Trading API Keys from Bybit

1. Go to **https://www.bybit.com/**
2. Log in to your account
3. Navigate to **Account → API**
4. Make sure you're in the **"Live Trading"** tab (NOT Demo Trading)
5. Click **"Create New API Key"**
6. Configure the key:
   - **Name**: Give it a descriptive name (e.g., "AlgoCrypto Bot")
   - **Permissions**: 
     - ✅ **Read** (required)
     - ✅ **Trade** (if you want to place orders)
     - ⚠️ **Withdraw** (ONLY enable if absolutely necessary - high risk!)
   - **IP Whitelist**: 
     - For testing: **DISABLE** it
     - For production: **ENABLE** and add your server IP
7. Click **"Create"**
8. **IMMEDIATELY copy both:**
   - API Key (you can see this later)
   - API Secret (you can ONLY see this once!)

### 2. Update Your .env File

Edit `/Users/bryanlew/Document/AlgoCrypto/Backend/Connection/.env`:

```bash
# Set environment to LIVE
BYBIT_ENVIRONMENT=LIVE

# Add your LIVE trading API keys
BYBIT_API_KEY_LIVE=your_live_api_key_here
BYBIT_API_SECRET_LIVE=your_live_api_secret_here

# Keep demo keys for reference (optional)
# BYBIT_API_KEY_DEMO=your_demo_key
# BYBIT_API_SECRET_DEMO=your_demo_secret
```

**Important:**
- No spaces around the `=` sign
- No quotes around the values
- Each key on its own line

### 3. Test the Connection

```bash
cd /Users/bryanlew/Document/AlgoCrypto/Backend/Connection
python Bybit_connection_test.py
```

You should see:
- ⚠️ Warnings about LIVE TRADING mode
- Connection test results
- Your real account balance

### 4. Verify Everything Works

The test will:
- ✅ Connect to Bybit
- ✅ Fetch your account balance
- ✅ Get market data
- ✅ Check positions

## Security Best Practices

1. **IP Whitelist**: Enable it in production and only allow your server IP
2. **Permissions**: Only enable what you need (Read + Trade, avoid Withdraw)
3. **Key Rotation**: Regularly rotate your API keys
4. **Monitor**: Watch your account for unexpected activity
5. **Backup**: Keep a backup of your .env file in a secure location

## Switching Back to Demo

To switch back to demo trading:

1. Edit `.env` file:
   ```
   BYBIT_ENVIRONMENT=DEMO
   ```

2. Or remove the `BYBIT_ENVIRONMENT` line (defaults to DEMO)

## Troubleshooting

### "API key is invalid" Error

1. Check you're using **Live Trading** keys (not Demo Trading)
2. Verify IP whitelist is disabled (or your IP is added)
3. Check key permissions in Bybit dashboard
4. Wait 1-2 minutes after creating a new key

### Connection Fails

1. Check your internet connection
2. Verify Bybit API status: https://bybit-exchange.github.io/docs/
3. Check if your IP is blocked
4. Try disabling IP whitelist temporarily

## Risk Management

Before going live:

- ✅ Test strategies thoroughly with paper trading
- ✅ Start with small position sizes
- ✅ Set stop losses
- ✅ Monitor trades actively
- ✅ Have a plan for emergencies
- ✅ Never risk more than you can afford to lose

