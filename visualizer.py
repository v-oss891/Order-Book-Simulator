"""
visualizer.py — Matplotlib charts for order book simulation.

Produces a 2x2 grid of:
1. Mid-price over time with VWAP overlay
2. Bid-ask spread over time with anomaly highlighting
3. Order book depth snapshot (horizontal bar chart)
4. Trade volume over time (buy vs sell initiated)
"""

from __future__ import annotations

from typing import List, Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from analytics import AnalyticsReport
from order import Trade, Side
from order_book import OrderBook


class Visualizer:
    """Generates publication-quality charts from simulation data."""

    # Color palette
    C_BG = "#0f1117"
    C_PANEL = "#1a1d27"
    C_TEXT = "#e0e0e0"
    C_GREEN = "#00c896"
    C_RED = "#ff4757"
    C_BLUE = "#4a9eff"
    C_PURPLE = "#a855f7"
    C_YELLOW = "#fbbf24"
    C_GRID = "#2a2d3a"

    @classmethod
    def plot_all(
        cls,
        book: OrderBook,
        report: AnalyticsReport,
        save_path: Optional[str] = None,
    ) -> None:
        """
        Render the 2x2 analytics dashboard.

        Args:
            book:      The OrderBook after simulation.
            report:    Computed AnalyticsReport.
            save_path: If given, save the figure to this path.
        """
        plt.style.use("dark_background")
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.patch.set_facecolor(cls.C_BG)
        fig.suptitle(
            "Order Book Simulator — Analytics Dashboard",
            fontsize=18, fontweight="bold", color=cls.C_TEXT, y=0.98,
        )

        cls._plot_mid_price(axes[0, 0], book, report)
        cls._plot_spread(axes[0, 1], book)
        cls._plot_depth(axes[1, 0], book)
        cls._plot_volume(axes[1, 1], book.trade_log)

        plt.tight_layout(rect=[0, 0, 1, 0.95])

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches="tight",
                        facecolor=cls.C_BG)
            print(f"  Chart saved to {save_path}")

        plt.show()

    # ── Chart 1: Mid-price + VWAP ─────────────

    @classmethod
    def _plot_mid_price(
        cls, ax: plt.Axes, book: OrderBook, report: AnalyticsReport,
    ) -> None:
        ax.set_facecolor(cls.C_PANEL)
        if not book.mid_price_history:
            ax.text(0.5, 0.5, "No data", ha="center",
                    va="center", color=cls.C_TEXT)
            return

        indices = list(range(len(book.mid_price_history)))
        mids = [m for _, m in book.mid_price_history]

        ax.plot(indices, mids, color=cls.C_BLUE, linewidth=1.2,
                alpha=0.9, label="Mid Price")

        if report.vwap > 0:
            ax.axhline(y=report.vwap, color=cls.C_YELLOW,
                       linestyle="--", linewidth=1.5,
                       alpha=0.8, label=f"VWAP ${report.vwap:.2f}")

        ax.set_title("Mid-Price Over Time", color=cls.C_TEXT,
                     fontsize=12, pad=10)
        ax.set_xlabel("Event", color=cls.C_TEXT, fontsize=9)
        ax.set_ylabel("Price ($)", color=cls.C_TEXT, fontsize=9)
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(True, alpha=0.15, color=cls.C_GRID)
        ax.tick_params(colors=cls.C_TEXT, labelsize=8)

    # ── Chart 2: Bid-Ask Spread ───────────────

    @classmethod
    def _plot_spread(cls, ax: plt.Axes, book: OrderBook) -> None:
        ax.set_facecolor(cls.C_PANEL)
        if not book.spread_history:
            ax.text(0.5, 0.5, "No data", ha="center",
                    va="center", color=cls.C_TEXT)
            return

        indices = list(range(len(book.spread_history)))
        spreads = [s for _, s in book.spread_history]

        # Threshold for "anomaly" = mean + 2*std
        arr = np.array(spreads)
        threshold = float(arr.mean() + 2 * arr.std())

        normal_x, normal_y = [], []
        anom_x, anom_y = [], []
        for i, s in zip(indices, spreads):
            if s > threshold:
                anom_x.append(i)
                anom_y.append(s)
            else:
                normal_x.append(i)
                normal_y.append(s)

        ax.scatter(normal_x, normal_y, color=cls.C_GREEN,
                   s=1, alpha=0.6, label="Normal")
        if anom_x:
            ax.scatter(anom_x, anom_y, color=cls.C_RED,
                       s=6, alpha=0.9, label="Wide Spread")

        ax.axhline(y=threshold, color=cls.C_RED, linestyle=":",
                   linewidth=1, alpha=0.5)
        ax.set_title("Bid-Ask Spread Over Time", color=cls.C_TEXT,
                     fontsize=12, pad=10)
        ax.set_xlabel("Event", color=cls.C_TEXT, fontsize=9)
        ax.set_ylabel("Spread ($)", color=cls.C_TEXT, fontsize=9)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.15, color=cls.C_GRID)
        ax.tick_params(colors=cls.C_TEXT, labelsize=8)

    # ── Chart 3: Depth Snapshot ───────────────

    @classmethod
    def _plot_depth(cls, ax: plt.Axes, book: OrderBook) -> None:
        ax.set_facecolor(cls.C_PANEL)
        snap = book.get_depth_snapshot(levels=10)
        bids = snap["bids"]
        asks = snap["asks"]

        if not bids and not asks:
            ax.text(0.5, 0.5, "Book empty", ha="center",
                    va="center", color=cls.C_TEXT)
            return

        labels, values, colors = [], [], []
        for price, qty in reversed(bids):
            labels.append(f"${price:.2f}")
            values.append(-qty)
            colors.append(cls.C_GREEN)
        for price, qty in asks:
            labels.append(f"${price:.2f}")
            values.append(qty)
            colors.append(cls.C_RED)

        y_pos = range(len(labels))
        ax.barh(y_pos, values, color=colors, alpha=0.8,
                edgecolor="none", height=0.7)
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(labels, fontsize=7)
        ax.axvline(x=0, color=cls.C_TEXT, linewidth=0.5, alpha=0.3)
        ax.set_title("Order Book Depth", color=cls.C_TEXT,
                     fontsize=12, pad=10)
        ax.set_xlabel("Quantity (Bids ← | → Asks)",
                     color=cls.C_TEXT, fontsize=9)
        ax.grid(True, alpha=0.15, color=cls.C_GRID, axis="x")
        ax.tick_params(colors=cls.C_TEXT, labelsize=8)

    # ── Chart 4: Trade Volume ─────────────────

    @classmethod
    def _plot_volume(
        cls, ax: plt.Axes, trades: List[Trade],
    ) -> None:
        ax.set_facecolor(cls.C_PANEL)
        if not trades:
            ax.text(0.5, 0.5, "No trades", ha="center",
                    va="center", color=cls.C_TEXT)
            return

        n_buckets = min(50, len(trades))
        bucket_size = max(1, len(trades) // n_buckets)

        buy_vols, sell_vols = [], []
        for i in range(0, len(trades), bucket_size):
            chunk = trades[i : i + bucket_size]
            bv = sum(t.quantity for t in chunk
                     if t.aggressor_side == Side.BUY)
            sv = sum(t.quantity for t in chunk
                     if t.aggressor_side == Side.SELL)
            buy_vols.append(bv)
            sell_vols.append(sv)

        x = np.arange(len(buy_vols))
        w = 0.75
        ax.bar(x, buy_vols, width=w, color=cls.C_GREEN,
               alpha=0.8, label="Buy-initiated")
        ax.bar(x, sell_vols, width=w, bottom=buy_vols,
               color=cls.C_RED, alpha=0.8, label="Sell-initiated")

        ax.set_title("Trade Volume Over Time", color=cls.C_TEXT,
                     fontsize=12, pad=10)
        ax.set_xlabel("Time Bucket", color=cls.C_TEXT, fontsize=9)
        ax.set_ylabel("Volume", color=cls.C_TEXT, fontsize=9)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.15, color=cls.C_GRID, axis="y")
        ax.tick_params(colors=cls.C_TEXT, labelsize=8)
