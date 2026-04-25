"""
analytics.py — Post-simulation performance metrics.

Computes key market microstructure statistics including
fill rate, VWAP, price drift, spread stats, and trade size distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from order import Order, OrderStatus, Side, Trade
from order_book import OrderBook


@dataclass
class AnalyticsReport:
    """Container for all computed analytics."""
    total_orders: int = 0
    total_trades: int = 0
    total_cancellations: int = 0
    fill_rate: float = 0.0
    avg_spread: float = 0.0
    min_spread: float = 0.0
    max_spread: float = 0.0
    vwap: float = 0.0
    start_mid: Optional[float] = None
    end_mid: Optional[float] = None
    price_drift_pct: float = 0.0
    book_imbalance: float = 0.0
    trade_size_mean: float = 0.0
    trade_size_median: float = 0.0
    trade_size_std: float = 0.0
    buy_initiated_volume: int = 0
    sell_initiated_volume: int = 0


class Analytics:
    """Computes post-simulation analytics from the order book state."""

    @staticmethod
    def compute(
        book: OrderBook, orders: List[Order], cancellations: int = 0,
    ) -> AnalyticsReport:
        """Compute all analytics metrics from simulation results."""
        report = AnalyticsReport()
        trades = book.trade_log

        report.total_orders = len(orders)
        report.total_trades = len(trades)
        report.total_cancellations = cancellations

        filled = sum(1 for o in orders if o.status in (OrderStatus.FILLED, OrderStatus.PARTIAL))
        report.fill_rate = (filled / len(orders) * 100) if orders else 0.0

        if book.spread_history:
            spreads = [s for _, s in book.spread_history]
            report.avg_spread = sum(spreads) / len(spreads)
            report.min_spread = min(spreads)
            report.max_spread = max(spreads)

        if trades:
            total_notional = sum(t.price * t.quantity for t in trades)
            total_vol = sum(t.quantity for t in trades)
            report.vwap = round(total_notional / total_vol, 4) if total_vol else 0.0

        if book.mid_price_history:
            report.start_mid = book.mid_price_history[0][1]
            report.end_mid = book.mid_price_history[-1][1]
            if report.start_mid and report.start_mid != 0:
                report.price_drift_pct = round(
                    (report.end_mid - report.start_mid) / report.start_mid * 100, 4)

        report.book_imbalance = book.get_book_imbalance()

        if trades:
            sizes = pd.Series([t.quantity for t in trades])
            report.trade_size_mean = round(sizes.mean(), 2)
            report.trade_size_median = round(sizes.median(), 2)
            report.trade_size_std = round(sizes.std(), 2)

        report.buy_initiated_volume = sum(t.quantity for t in trades if t.aggressor_side == Side.BUY)
        report.sell_initiated_volume = sum(t.quantity for t in trades if t.aggressor_side == Side.SELL)

        return report

    @staticmethod
    def print_report(report: AnalyticsReport) -> None:
        """Pretty-print the analytics report to stdout."""
        print("\n" + "=" * 52)
        print("  ORDER BOOK SIMULATION - ANALYTICS REPORT")
        print("=" * 52)
        print(f"\n  {'Orders submitted':<28} {report.total_orders:>10,}")
        print(f"  {'Trades executed':<28} {report.total_trades:>10,}")
        print(f"  {'Orders cancelled':<28} {report.total_cancellations:>10,}")
        print(f"  {'Fill rate':<28} {report.fill_rate:>9.2f}%")
        print(f"\n  {'Avg spread':<28} ${report.avg_spread:>9.4f}")
        print(f"  {'Min spread':<28} ${report.min_spread:>9.4f}")
        print(f"  {'Max spread':<28} ${report.max_spread:>9.4f}")
        print(f"\n  {'VWAP':<28} ${report.vwap:>9.4f}")
        if report.start_mid is not None:
            print(f"  {'Start mid-price':<28} ${report.start_mid:>9.4f}")
            print(f"  {'End mid-price':<28} ${report.end_mid:>9.4f}")
        sign = "+" if report.price_drift_pct >= 0 else ""
        print(f"  {'Price drift':<28} {sign}{report.price_drift_pct:.2f}%")
        print(f"\n  {'Book imbalance':<28} {report.book_imbalance:>10.4f}")
        if report.book_imbalance > 0.05:
            print(f"  {'  -> Interpretation':<28} {'Mild buy pressure':>10}")
        elif report.book_imbalance < -0.05:
            print(f"  {'  -> Interpretation':<28} {'Mild sell pressure':>10}")
        else:
            print(f"  {'  -> Interpretation':<28} {'Balanced':>10}")
        print(f"\n  {'Trade size - mean':<28} {report.trade_size_mean:>10.2f}")
        print(f"  {'Trade size - median':<28} {report.trade_size_median:>10.2f}")
        print(f"  {'Trade size - std':<28} {report.trade_size_std:>10.2f}")
        print(f"\n  {'Buy-initiated volume':<28} {report.buy_initiated_volume:>10,}")
        print(f"  {'Sell-initiated volume':<28} {report.sell_initiated_volume:>10,}")
        print("\n" + "=" * 52)

    @staticmethod
    def get_trade_dataframe(trades: List[Trade]) -> pd.DataFrame:
        """Convert the trade log to a pandas DataFrame."""
        if not trades:
            return pd.DataFrame()
        return pd.DataFrame({
            "trade_id": [t.trade_id for t in trades],
            "price": [t.price for t in trades],
            "quantity": [t.quantity for t in trades],
            "aggressor": [t.aggressor_side.value for t in trades],
            "timestamp": [t.timestamp for t in trades],
        })
