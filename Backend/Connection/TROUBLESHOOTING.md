# Bybit Demo Trading API Connection Troubleshooting

## Current Issue: API Key Invalid (retCode 10003)

Your API keys are being rejected by Bybit. Here's how to fix it:

## Step-by-Step Fix

### 1. Check IP Whitelist (MOST COMMON ISSUE)

**This is usually the problem!**

1. Go to https://www.bybit.com/
2. Log in → Account → API
3. Click on your Demo Trading API key
4. Look for "IP Whitelist" setting
5. **DISABLE it** (or add your current IP address)

**To find your IP:**
- Visit: https://whatismyipaddress.com/
- Copy your IPv4 address
- Add it to the whitelist OR disable whitelist entirely

### 2. Verify Key Permissions

1. In Bybit → Account → API → Your Demo Key
2. Check that these permissions are enabled:
   - ✅ Read (minimum required)
   - ✅ Contracts - Orders, Positions (if trading futures)
   - ✅ Wallet - Account Transfer (if needed)

### 3. Wait for Key Activation

- New API keys can take **1-5 minutes** to activate
- If you just created the key, wait a few minutes and try again

### 4. Verify .env File Format

Your `.env` file should look exactly like this (no spaces, no quotes):
```
BYBIT_API_KEY_DEMO=zNipVm5ciOUo2aONpg
BYBIT_API_SECRET_DEMO=fROc2ccrgyb82ByXwhojsagqyJmeeEdcekiE
```

### 5. Create a Fresh API Key

If nothing works, create a completely new key:

1. Go to Bybit → Account → API → Demo Trading
2. **Delete** the old API key
3. Click "Create New API Key"
4. Set permissions (at least Read)
5. **Disable IP Whitelist** (important!)
6. Copy the key immediately
7. Copy the secret immediately (you can only see it once!)
8. Update your `.env` file
9. Wait 2-3 minutes
10. Test again

## Testnet Alternative (If Demo Trading Doesn't Work)

If testnet.bybit.com doesn't load for you:

1. **Try different URLs:**
   - https://testnet.bybit.com/
   - https://testnet.bybit.com/v5/
   - https://testnet.bybit.com/trade/

2. **Use VPN:**
   - Testnet might be blocked in some regions
   - Try using a VPN to access it

3. **Contact Bybit Support:**
   - If testnet is completely inaccessible, contact Bybit support
   - They can help with demo trading API access

## Quick Test Commands

```bash
# Test connection (this will also validate your .env file format)
python Bybit_connection_test.py
```

## Common Mistakes

❌ **Wrong:** `BYBIT_API_KEY_DEMO = "key"` (spaces and quotes)
✅ **Correct:** `BYBIT_API_KEY_DEMO=key` (no spaces, no quotes)

❌ **Wrong:** Using Live Trading keys for Demo Trading
✅ **Correct:** Use Demo Trading tab keys for Demo Trading

❌ **Wrong:** IP Whitelist enabled without your IP
✅ **Correct:** Disable IP Whitelist or add your IP

## Still Not Working?

1. Double-check IP whitelist is disabled
2. Verify you're using Demo Trading keys (not Live Trading)
3. Wait 5 minutes after creating a new key
4. Try creating a completely new key from scratch
5. Check Bybit status page for API issues

