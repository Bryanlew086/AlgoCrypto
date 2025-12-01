"""
Bollinger Bands Strategy Module
Extracted from BB_breakout_backtest_latest.ipynb
"""
import pandas as pd
import numpy as np

def load_ohlc_csv(path: str) -> pd.DataFrame:
    """Robust loader: normalizes columns and ensures 'close' + 'time'"""
    df = pd.read_csv(path)
    df.columns = df.columns.str.lower()

    # Map alternate price names to 'close' if needed
    if 'close' not in df.columns:
        for alt in ('closing_price', 'price', 'last'):
            if alt in df.columns:
                df = df.rename(columns={alt: 'close'})
                break
    if 'close' not in df.columns:
        raise KeyError(f"Required column 'close' not found. Available: {list(df.columns)}")

    # Ensure 'time' column exists
    if 'time' not in df.columns:
        for cand in ('timestamp', 'date', 'datetime'):
            if cand in df.columns:
                df = df.rename(columns={cand: 'time'})
                break
    if 'time' not in df.columns:
        raise KeyError(f"Required column 'time' not found. Available: {list(df.columns)}")

    # Parse time if possible
    try:
        df['time'] = pd.to_datetime(df['time'])
    except Exception:
        pass

    return df.set_index('time') if 'time' in df.columns else df

def bollinger_bands(df: pd.DataFrame, column: str = 'close', window: int = 24, std_dev: float = 1.0) -> pd.DataFrame:
    """Calculate Bollinger Bands"""
    mid = df[column].rolling(window=window).mean()
    vol = df[column].rolling(window=window).std()
    df['BB_Middle'] = mid
    df['BB_Upper'] = mid + vol * std_dev
    df['BB_Lower'] = mid - vol * std_dev
    return df

def bollinger_band_entry_logic(df: pd.DataFrame) -> pd.DataFrame:
    """Generate entry signals based on Bollinger Bands"""
    sig = np.where(df['close'] < df['BB_Lower'], 1,
          np.where(df['close'] > df['BB_Upper'], -1, 0))
    df['Signal'] = pd.Series(sig, index=df.index).replace(0, np.nan).ffill().fillna(0)
    return df

def optimise_param_sr(df: pd.DataFrame) -> tuple:
    """Optimize parameters for Sharpe Ratio"""
    best_sr, best_lookback, best_std = -np.inf, -1, -1.0
    for lookback in np.arange(1, 200, 1):
        for std_dev in np.arange(0.5, 5, 0.5):
            tmp = df.copy()
            bollinger_bands(tmp, column='close', window=lookback, std_dev=std_dev)
            bollinger_band_entry_logic(tmp)
            tmp['price_chg'] = tmp['close'].pct_change()
            tmp['pnl'] = tmp['Signal'].shift(1) * tmp['price_chg']
            pnl = tmp['pnl'].dropna()
            if pnl.std() == 0 or np.isnan(pnl.std()):
                continue
            sr = pnl.mean() / pnl.std() * np.sqrt(365)
            if sr > best_sr:
                best_sr, best_lookback, best_std = sr, lookback, std_dev
    return int(best_lookback), best_sr, best_std

def optimise_param_pf(df: pd.DataFrame) -> tuple:
    """Optimize parameters for Profit Factor"""
    best_pf, best_lookback, best_std = -np.inf, -1, -1.0
    for lookback in range(12, 169):
        for std_dev in np.arange(0.5, 5, 0.5):
            tmp = df.copy()
            bollinger_bands(tmp, column='close', window=lookback, std_dev=std_dev)
            bollinger_band_entry_logic(tmp)
            tmp['price_chg'] = tmp['close'].pct_change()
            tmp['pnl'] = tmp['Signal'].shift(1) * tmp['price_chg']
            pnl = tmp['pnl'].dropna()
            pos = pnl[pnl > 0].sum()
            neg = pnl[pnl < 0].abs().sum()
            if neg == 0 or pos == 0:
                continue
            pf = pos / neg
            if pf > best_pf:
                best_pf, best_lookback, best_std = pf, lookback, std_dev
    return int(best_lookback), best_pf, best_std

