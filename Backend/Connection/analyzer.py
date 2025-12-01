"""
Strategy Performance Analyzer
Compares multiple trading strategies and identifies the best performing one.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os
from pathlib import Path

# Add parent directories to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import strategy functions
# Note: We'll need to extract functions from notebooks or create wrapper modules
import warnings
warnings.filterwarnings('ignore')

# ============================================
# 1. DATA LOADING
# ============================================
def load_data(data_path):
    """Load OHLC data from CSV"""
    df = pd.read_csv(data_path)
    # Normalize column names
    df.columns = df.columns.str.lower()
    
    # Ensure time column exists
    if 'time' not in df.columns:
        for col in ['timestamp', 'date', 'datetime']:
            if col in df.columns:
                df = df.rename(columns={col: 'time'})
                break
    
    # Parse time if possible
    if 'time' in df.columns:
        try:
            df['time'] = pd.to_datetime(df['time'])
            df = df.set_index('time')
        except:
            pass
    
    # Ensure required columns exist
    required_cols = ['open', 'high', 'low', 'close']
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Required column '{col}' not found. Available: {list(df.columns)}")
    
    # Convert to numeric
    for col in required_cols + ['volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna()
    return df

# ============================================
# 2. STRATEGY WRAPPERS
# ============================================

def run_bb_strategy(df):
    """
    Run Bollinger Bands strategy
    Returns: metrics dict and strategy data
    """
    try:
        # Import BB strategy functions
        from Strategy.bb_strategy import (
            bollinger_bands, bollinger_band_entry_logic,
            optimise_param_sr
        )
        
        # Use the strategy's optimization
        df_bb = df.copy()
        
        # Optimize parameters
        best_lookback, best_score, best_std = optimise_param_sr(df_bb)
        
        # Run with best parameters
        bollinger_bands(df_bb, column='close', window=best_lookback, std_dev=best_std)
        bollinger_band_entry_logic(df_bb)
        df_bb['price_chg'] = df_bb['close'].pct_change()
        df_bb['pnl'] = df_bb['Signal'].shift(1) * df_bb['price_chg']
        df_bb['cumu_pnl'] = df_bb['pnl'].cumsum()
        
        # Calculate metrics
        pnl = df_bb['pnl'].dropna()
        pos = pnl[pnl > 0].sum()
        neg = pnl[pnl < 0].abs().sum()
        pf = (pos / neg) if neg != 0 else np.nan
        
        sr = (pnl.mean() / pnl.std() * np.sqrt(365)) if pnl.std() != 0 else 0.0
        roi = df_bb['cumu_pnl'].iloc[-1] if not df_bb['cumu_pnl'].empty else 0
        
        # Trade counts
        sig = df_bb['Signal']
        prev = sig.shift(1).fillna(0)
        long_entries = ((prev != 1) & (sig == 1)).sum()
        short_entries = ((prev != -1) & (sig == -1)).sum()
        total_trades = int(long_entries + short_entries)
        
        # Max Drawdown
        roll_max = df_bb['cumu_pnl'].cummax()
        drawdown = df_bb['cumu_pnl'] - roll_max
        max_dd_abs = abs(drawdown.min()) if not drawdown.empty else 0
        
        # Sortino (downside deviation)
        downs = pnl[pnl < 0]
        downside_std = downs.std() if not downs.empty and downs.std() != 0 else np.nan
        sortino = (pnl.mean() / downside_std * np.sqrt(365)) if not np.isnan(downside_std) else np.nan
        
        # Calmar
        calmar = (sr if max_dd_abs != 0 else np.nan) if max_dd_abs != 0 else np.nan
        
        metrics = {
            'strategy_name': 'Bollinger Bands',
            'roi': roi,
            'sharpe_ratio': sr,
            'sortino_ratio': sortino if not np.isnan(sortino) else 0,
            'calmar_ratio': calmar if not np.isnan(calmar) else 0,
            'profit_factor': pf if not np.isnan(pf) else 0,
            'max_drawdown': max_dd_abs,
            'total_trades': total_trades,
            'avg_return': pnl.mean(),
            'std_dev': pnl.std(),
            'returns_series': pnl,
            'cumulative_pnl': df_bb['cumu_pnl']
        }
        
        return metrics, df_bb
        
    except Exception as e:
        print(f"Error running BB strategy: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def run_ma_strategy(df):
    """
    Run Moving Average Cross strategy
    Returns: metrics dict and strategy data
    """
    try:
        df_ma = df.copy()
        
        # Use optimized parameters (from MA.py grid search results)
        # Default: short=20, long=50 (can be optimized)
        short_window = 20
        long_window = 50
        
        df_ma['MA_short'] = df_ma['close'].rolling(short_window).mean()
        df_ma['MA_long'] = df_ma['close'].rolling(long_window).mean()
        
        df_ma['Signal'] = np.where(df_ma['MA_short'] > df_ma['MA_long'], 1, -1)
        df_ma['Return'] = df_ma['close'].pct_change()
        df_ma['Strategy_Return'] = df_ma['Signal'].shift(1) * df_ma['Return']
        
        # Calculate metrics
        returns = df_ma['Strategy_Return'].dropna()
        total_profit = (returns + 1).prod() - 1
        sharpe_ratio = np.sqrt(252) * returns.mean() / returns.std() if returns.std() != 0 else 0
        
        # Trade counts
        sig = df_ma['Signal']
        prev = sig.shift(1).fillna(0)
        long_entries = ((prev != 1) & (sig == 1)).sum()
        short_entries = ((prev != -1) & (sig == -1)).sum()
        total_trades = int(long_entries + short_entries)
        
        # Cumulative PnL
        cumu_pnl = (returns + 1).cumprod() - 1
        
        # Max Drawdown
        roll_max = cumu_pnl.cummax()
        drawdown = cumu_pnl - roll_max
        max_dd_abs = abs(drawdown.min()) if not drawdown.empty else 0
        
        # Profit Factor
        pos = returns[returns > 0].sum()
        neg = returns[returns < 0].abs().sum()
        pf = (pos / neg) if neg != 0 else np.nan
        
        # Sortino
        downs = returns[returns < 0]
        downside_std = downs.std() if not downs.empty and downs.std() != 0 else np.nan
        sortino = (returns.mean() / downside_std * np.sqrt(252)) if not np.isnan(downside_std) else np.nan
        
        # Calmar
        calmar = (sharpe_ratio if max_dd_abs != 0 else np.nan) if max_dd_abs != 0 else np.nan
        
        metrics = {
            'strategy_name': 'Moving Average Cross',
            'roi': total_profit,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino if not np.isnan(sortino) else 0,
            'calmar_ratio': calmar if not np.isnan(calmar) else 0,
            'profit_factor': pf if not np.isnan(pf) else 0,
            'max_drawdown': max_dd_abs,
            'total_trades': total_trades,
            'avg_return': returns.mean(),
            'std_dev': returns.std(),
            'returns_series': returns,
            'cumulative_pnl': cumu_pnl
        }
        
        return metrics, df_ma
        
    except Exception as e:
        print(f"Error running MA strategy: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def run_rsi_strategy(df):
    """
    Run RSI Mean-Reversion strategy
    Returns: metrics dict and strategy data
    """
    try:
        # Import RSI strategy functions from notebook
        # We'll need to extract the functions or run the notebook
        import subprocess
        import json
        
        # For now, we'll implement a simplified version
        df_rsi = df.copy()
        
        # Calculate RSI
        def calculate_rsi(series, period=14):
            delta = series.diff()
            gain = np.where(delta > 0, delta, 0)
            loss = np.where(delta < 0, -delta, 0)
            
            avg_gain = pd.Series(gain, index=series.index).rolling(period).mean()
            avg_loss = pd.Series(loss, index=series.index).rolling(period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(50)
            return rsi
        
        # RSI parameters
        rsi_period = 14
        oversold = 30
        overbought = 70
        
        df_rsi['RSI'] = calculate_rsi(df_rsi['close'], rsi_period)
        
        # Generate signals
        df_rsi['Signal'] = 0
        df_rsi.loc[df_rsi['RSI'] < oversold, 'Signal'] = 1  # Buy
        df_rsi.loc[df_rsi['RSI'] > overbought, 'Signal'] = -1  # Sell
        df_rsi['Signal'] = df_rsi['Signal'].shift(1).fillna(0)
        
        # Calculate returns
        df_rsi['Return'] = df_rsi['close'].pct_change()
        df_rsi['Strategy_Return'] = df_rsi['Signal'] * df_rsi['Return']
        
        # Calculate metrics
        returns = df_rsi['Strategy_Return'].dropna()
        total_profit = (returns + 1).prod() - 1
        sharpe_ratio = np.sqrt(252) * returns.mean() / returns.std() if returns.std() != 0 else 0
        
        # Trade counts
        sig = df_rsi['Signal']
        prev = sig.shift(1).fillna(0)
        long_entries = ((prev != 1) & (sig == 1)).sum()
        short_entries = ((prev != -1) & (sig == -1)).sum()
        total_trades = int(long_entries + short_entries)
        
        # Cumulative PnL
        cumu_pnl = (returns + 1).cumprod() - 1
        
        # Max Drawdown
        roll_max = cumu_pnl.cummax()
        drawdown = cumu_pnl - roll_max
        max_dd_abs = abs(drawdown.min()) if not drawdown.empty else 0
        
        # Profit Factor
        pos = returns[returns > 0].sum()
        neg = returns[returns < 0].abs().sum()
        pf = (pos / neg) if neg != 0 else np.nan
        
        # Sortino
        downs = returns[returns < 0]
        downside_std = downs.std() if not downs.empty and downs.std() != 0 else np.nan
        sortino = (returns.mean() / downside_std * np.sqrt(252)) if not np.isnan(downside_std) else np.nan
        
        # Calmar
        calmar = (sharpe_ratio if max_dd_abs != 0 else np.nan) if max_dd_abs != 0 else np.nan
        
        metrics = {
            'strategy_name': 'RSI Mean-Reversion',
            'roi': total_profit,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino if not np.isnan(sortino) else 0,
            'calmar_ratio': calmar if not np.isnan(calmar) else 0,
            'profit_factor': pf if not np.isnan(pf) else 0,
            'max_drawdown': max_dd_abs,
            'total_trades': total_trades,
            'avg_return': returns.mean(),
            'std_dev': returns.std(),
            'returns_series': returns,
            'cumulative_pnl': cumu_pnl
        }
        
        return metrics, df_rsi
        
    except Exception as e:
        print(f"Error running RSI strategy: {e}")
        import traceback
        traceback.print_exc()
        return None, None

# ============================================
# 3. COMPARISON AND ANALYSIS
# ============================================

def compare_strategies(data_path):
    """
    Main function to compare all strategies
    """
    print("=" * 80)
    print("STRATEGY PERFORMANCE ANALYZER")
    print("=" * 80)
    print()
    
    # Load data
    print("Loading data...")
    df = load_data(data_path)
    print(f"✓ Loaded {len(df)} data points")
    print()
    
    # Run all strategies
    print("Running strategies...")
    print("-" * 80)
    
    results = {}
    
    # Bollinger Bands
    print("1. Running Bollinger Bands strategy...")
    bb_metrics, bb_data = run_bb_strategy(df)
    if bb_metrics:
        results['Bollinger_Bands'] = bb_metrics
        print(f"   ✓ Completed")
    else:
        print(f"   ✗ Failed")

    # Moving Average
    print("2. Running Moving Average Cross strategy...")
    ma_metrics, ma_data = run_ma_strategy(df)
    if ma_metrics:
        results['Moving_Average'] = ma_metrics
        print(f"   ✓ Completed")
    else:
        print(f"   ✗ Failed")
    
    # RSI
    print("3. Running RSI Mean-Reversion strategy...")
    rsi_metrics, rsi_data = run_rsi_strategy(df)
    if rsi_metrics:
        results['RSI'] = rsi_metrics
        print(f"   ✓ Completed")
    else:
        print(f"   ✗ Failed")
    
    print()
    
    if not results:
        print("ERROR: No strategies completed successfully!")
        return None
    
    # ============================================
    # 4. CREATE COMPARISON TABLE
    # ============================================
    print("=" * 80)
    print("STRATEGY COMPARISON TABLE")
    print("=" * 80)
    print()
    
    comparison_data = []
    for name, metrics in results.items():
        comparison_data.append({
            'Strategy': metrics['strategy_name'],
            'ROI (%)': f"{metrics['roi'] * 100:.2f}%",
            'Sharpe Ratio': f"{metrics['sharpe_ratio']:.4f}",
            'Sortino Ratio': f"{metrics['sortino_ratio']:.4f}",
            'Calmar Ratio': f"{metrics['calmar_ratio']:.4f}",
            'Profit Factor': f"{metrics['profit_factor']:.4f}",
            'Max Drawdown (%)': f"{metrics['max_drawdown'] * 100:.2f}%",
            'Total Trades': metrics['total_trades'],
            'Avg Return': f"{metrics['avg_return']:.6f}",
            'Std Dev': f"{metrics['std_dev']:.6f}"
        })
    
    comparison_df = pd.DataFrame(comparison_data)
    print(comparison_df.to_string(index=False))
    print()
    
    # ============================================
    # 5. FIND BEST STRATEGY
    # ============================================
    print("=" * 80)
    print("BEST STRATEGY ANALYSIS")
    print("=" * 80)
    print()
    
    # Find best by different metrics
    best_by_roi = max(results.items(), key=lambda x: x[1]['roi'])
    best_by_sharpe = max(results.items(), key=lambda x: x[1]['sharpe_ratio'])
    best_by_pf = max(results.items(), key=lambda x: x[1]['profit_factor'])
    best_by_trades = max(results.items(), key=lambda x: x[1]['total_trades'])
    min_drawdown = min(results.items(), key=lambda x: x[1]['max_drawdown'])
    
    print(f"🏆 Best by ROI:           {best_by_roi[1]['strategy_name']:30s} ({best_by_roi[1]['roi']*100:.2f}%)")
    print(f"🏆 Best by Sharpe Ratio:  {best_by_sharpe[1]['strategy_name']:30s} ({best_by_sharpe[1]['sharpe_ratio']:.4f})")
    print(f"🏆 Best by Profit Factor: {best_by_pf[1]['strategy_name']:30s} ({best_by_pf[1]['profit_factor']:.4f})")
    print(f"🏆 Most Trades:           {best_by_trades[1]['strategy_name']:30s} ({best_by_trades[1]['total_trades']} trades)")
    print(f"🏆 Lowest Drawdown:        {min_drawdown[1]['strategy_name']:30s} ({min_drawdown[1]['max_drawdown']*100:.2f}%)")
    print()
    
    # Overall best (weighted score)
    print("=" * 80)
    print("OVERALL RANKING (Weighted Score)")
    print("=" * 80)
    print()
    
    # Calculate weighted score (normalize each metric to 0-1 scale)
    scores = {}
    for name, metrics in results.items():
        # Normalize metrics (higher is better, except drawdown)
        roi_score = (metrics['roi'] - min(r['roi'] for r in results.values())) / \
                   (max(r['roi'] for r in results.values()) - min(r['roi'] for r in results.values()) + 1e-10)
        
        sharpe_score = (metrics['sharpe_ratio'] - min(r['sharpe_ratio'] for r in results.values())) / \
                      (max(r['sharpe_ratio'] for r in results.values()) - min(r['sharpe_ratio'] for r in results.values()) + 1e-10)
        
        pf_score = (metrics['profit_factor'] - min(r['profit_factor'] for r in results.values())) / \
                   (max(r['profit_factor'] for r in results.values()) - min(r['profit_factor'] for r in results.values()) + 1e-10)
        
        # Drawdown (lower is better, so invert)
        dd_max = max(r['max_drawdown'] for r in results.values())
        dd_min = min(r['max_drawdown'] for r in results.values())
        dd_score = 1 - ((metrics['max_drawdown'] - dd_min) / (dd_max - dd_min + 1e-10))
        
        # Weighted combination (adjust weights as needed)
        total_score = (
            0.30 * roi_score +
            0.30 * sharpe_score +
            0.20 * pf_score +
            0.20 * dd_score
        )
        
        scores[name] = {
            'strategy': metrics['strategy_name'],
            'total_score': total_score,
            'roi_score': roi_score,
            'sharpe_score': sharpe_score,
            'pf_score': pf_score,
            'dd_score': dd_score
        }
    
    # Sort by total score
    ranked = sorted(scores.items(), key=lambda x: x[1]['total_score'], reverse=True)
    
    for i, (name, score_data) in enumerate(ranked, 1):
        print(f"{i}. {score_data['strategy']:30s} | Score: {score_data['total_score']:.4f}")
        print(f"   ROI: {score_data['roi_score']:.3f} | Sharpe: {score_data['sharpe_score']:.3f} | "
              f"PF: {score_data['pf_score']:.3f} | DD: {score_data['dd_score']:.3f}")
    
    print()
    print("=" * 80)
    print(f"🏆 RECOMMENDED STRATEGY: {ranked[0][1]['strategy']}")
    print("=" * 80)
    print()
    
    # ============================================
    # 6. VISUALIZATION
    # ============================================
    print("Generating visualizations...")
    
    # Create comparison plots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Cumulative PnL Comparison
    ax1 = axes[0, 0]
    for name, metrics in results.items():
        cumu_pnl = metrics['cumulative_pnl']
        ax1.plot(cumu_pnl.index, cumu_pnl.values, label=metrics['strategy_name'], linewidth=2)
    ax1.set_title('Cumulative PnL Comparison', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Cumulative PnL')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Returns Distribution
    ax2 = axes[0, 1]
    for name, metrics in results.items():
        returns = metrics['returns_series']
        ax2.hist(returns, bins=50, alpha=0.6, label=metrics['strategy_name'], density=True)
    ax2.set_title('Returns Distribution', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Returns')
    ax2.set_ylabel('Density')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Metrics Comparison Bar Chart
    ax3 = axes[1, 0]
    strategies = [m['strategy_name'] for m in results.values()]
    sharpe_values = [m['sharpe_ratio'] for m in results.values()]
    bars = ax3.bar(strategies, sharpe_values, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
    ax3.set_title('Sharpe Ratio Comparison', fontsize=14, fontweight='bold')
    ax3.set_ylabel('Sharpe Ratio')
    ax3.tick_params(axis='x', rotation=45)
    ax3.grid(True, alpha=0.3, axis='y')
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.3f}', ha='center', va='bottom')
    
    # 4. Correlation Matrix
    ax4 = axes[1, 1]
    # Combine returns for correlation
    returns_df = pd.DataFrame({
        name: metrics['returns_series'] for name, metrics in results.items()
    })
    returns_df = returns_df.fillna(0)
    correlation_matrix = returns_df.corr()
    
    sns.heatmap(correlation_matrix, annot=True, fmt='.3f', cmap='coolwarm', 
                center=0, vmin=-1, vmax=1, ax=ax4, cbar_kws={'label': 'Correlation'})
    ax4.set_title('Strategy Returns Correlation', fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    # Save plot
    output_path = Path(__file__).parent.parent / 'Results' / 'strategy_comparison.png'
    output_path.parent.mkdir(exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✓ Saved comparison plot to: {output_path}")
    
    plt.show()

    # ============================================
    # 7. RETURN RESULTS
    # ============================================
    return {
        'results': results,
        'best_strategy': ranked[0][1]['strategy'],
        'comparison_df': comparison_df,
        'scores': scores
    }

# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    # Default data path
    default_data_path = "/Users/bryanlew/Document/AlgoCrypto/Backend/Data/bybit_btc_1h_20210101_20241231.csv"
    
    # Allow command line argument
    if len(sys.argv) > 1:
        data_path = sys.argv[1]
    else:
        data_path = default_data_path
    
    # Check if file exists
    if not os.path.exists(data_path):
        print(f"ERROR: Data file not found: {data_path}")
        print(f"Using default: {default_data_path}")
        data_path = default_data_path
    
    if not os.path.exists(data_path):
        print(f"ERROR: Default data file also not found: {default_data_path}")
        print("Please provide a valid data path.")
        sys.exit(1)
    
    # Run comparison
    analysis_results = compare_strategies(data_path)
    
    if analysis_results:
        print("\n" + "=" * 80)
        print("Analysis complete! Use the recommended strategy for trading.")
        print("=" * 80)
