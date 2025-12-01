# ===========================================
# AlgoCrypto Parameter Optimization (Backtest)
# ===========================================
import pandas as pd
import numpy as np
import itertools
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# -----------------------------
# 1. Import your AlgoCrypto tools
# -----------------------------
# Example:
# from Backend.Strategies.moving_average import MovingAverageStrategy
# from Backend.Backtest.backtester import Backtester

# -----------------------------
# 2. Load Historical Data
# -----------------------------
df = pd.read_csv("/Users/bryanlew/Document/AlgoCrypto/Backend/Data/bybit_btc_1d_20210101_20241231.csv")
df.rename(columns=str.capitalize, inplace=True)
df = df.sort_values(by='Time', ascending=True)  # if timestamp exists

# -----------------------------
# 3. Define Wrapper for Backtesting
# -----------------------------
def run_backtest(short_window, long_window):
    """
    Run one instance of backtest using AlgoCrypto framework.
    Replace this block with your actual AlgoCrypto function call.
    """
    # ========== Example Logic ==========
    df_local = df.copy()
    df_local['MA_short'] = df_local['Close'].rolling(short_window).mean()
    df_local['MA_long'] = df_local['Close'].rolling(long_window).mean()
    
    df_local['Signal'] = np.where(df_local['MA_short'] > df_local['MA_long'], 1, -1)
    df_local['Return'] = df_local['Close'].pct_change()
    df_local['Strategy_Return'] = df_local['Signal'].shift(1) * df_local['Return']

    total_profit = (df_local['Strategy_Return'] + 1).prod() - 1
    sharpe_ratio = np.mean(df_local['Strategy_Return']) / np.std(df_local['Strategy_Return']) * np.sqrt(252)

    return total_profit, sharpe_ratio

    # ========== If using AlgoCrypto’s real API ==========
    # result = Backtester(strategy=MovingAverageStrategy(short_window, long_window)).run(df)
    # return result['profit'], result['sharpe']

# -----------------------------
# 4. Grid Search
# -----------------------------
short_windows = range(5, 30, 5)
long_windows = range(20, 100, 10)

results = []
for short, long in itertools.product(short_windows, long_windows):
    if short >= long:
        continue
    profit, sharpe = run_backtest(short, long)
    results.append([short, long, profit, sharpe])

results_df = pd.DataFrame(results, columns=['Short_MA', 'Long_MA', 'Profit', 'Sharpe'])

# -----------------------------
# 5. Find Best Parameters
# -----------------------------
best_profit = results_df.loc[results_df['Profit'].idxmax()]
best_sharpe = results_df.loc[results_df['Sharpe'].idxmax()]

print("===== BEST BY PROFIT =====")
print(best_profit)
print("\n===== BEST BY SHARPE RATIO =====")
print(best_sharpe)

# -----------------------------
# 6. Generate Heatmaps (Custom Colors)
# -----------------------------
from matplotlib.colors import LinearSegmentedColormap

# Custom colormap: Red → Deep Green → Light Green
colors = ["red", "green", "lightgreen"]
custom_cmap = LinearSegmentedColormap.from_list("profit_cmap", colors, N=256)

# ---- Profit Heatmap ----
pivot_profit = results_df.pivot(index='Short_MA', columns='Long_MA', values='Profit')
plt.figure(figsize=(10, 6))
sns.heatmap(pivot_profit, cmap=custom_cmap, annot=True, fmt=".2f", cbar_kws={'label': 'Profit'})
plt.title("Profit Heatmap (AlgoCrypto MA Strategy)")
plt.xlabel("Long Moving Average")
plt.ylabel("Short Moving Average")
plt.tight_layout()
plt.show()

# ---- Sharpe Ratio Heatmap ----
pivot_sharpe = results_df.pivot(index='Short_MA', columns='Long_MA', values='Sharpe')
plt.figure(figsize=(10, 6))
vmin = results_df['Profit'].min()
vmax = results_df['Profit'].max()
sns.heatmap(pivot_profit, cmap=custom_cmap, annot=True, fmt=".2f", vmin=vmin, vmax=vmax)

plt.title("Sharpe Ratio Heatmap (AlgoCrypto MA Strategy)")
plt.xlabel("Long Moving Average")
plt.ylabel("Short Moving Average")
plt.tight_layout()
plt.show()

# -----------------------------
# 7. Save Results
# -----------------------------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_df.to_csv(f"/Users/bryanlew/Document/AlgoCrypto/Backend/Results/optimization_results_{timestamp}.csv", index=False)
print(f"\nSaved optimization results to Results/optimization_results_{timestamp}.csv")
