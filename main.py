#!/usr/bin/env python3
"""
main.py — Entry point for the Order Book Simulator.

Usage:
    python main.py --orders 10000 --rounds 500 --plot
    python main.py --orders 5000 --rounds 200
    python main.py --help
"""

from __future__ import annotations

import argparse
import time
import sys

from simulator import Simulator, SimulatorConfig
from analytics import Analytics
from visualizer import Visualizer


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Order Book Simulator — Price-Time Priority Matching Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py --orders 10000 --rounds 500 --plot\n"
            "  python main.py --orders 5000 --rounds 200\n"
        ),
    )
    parser.add_argument(
        "--orders", type=int, default=5000,
        help="Total number of orders to simulate (default: 5000)",
    )
    parser.add_argument(
        "--rounds", type=int, default=200,
        help="Number of simulation rounds (default: 200)",
    )
    parser.add_argument(
        "--price", type=float, default=100.0,
        help="Initial reference price (default: 100.0)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Show matplotlib visualization dashboard",
    )
    parser.add_argument(
        "--save-plot", type=str, default=None,
        help="Save the plot to a file (e.g., output.png)",
    )
    return parser.parse_args()


def main() -> None:
    """Run the order book simulation."""
    args = parse_args()

    print("\n" + "=" * 52)
    print("  ORDER BOOK SIMULATOR")
    print("  Price-Time Priority Matching Engine")
    print("=" * 52)
    print(f"\n  Config: {args.orders:,} orders | {args.rounds} rounds")
    print(f"  Initial price: ${args.price:.2f} | Seed: {args.seed}")
    print(f"  {'─' * 44}")

    # Configure and run simulation
    config = SimulatorConfig(
        initial_price=args.price,
        num_orders=args.orders,
        rounds=args.rounds,
        seed=args.seed,
    )

    sim = Simulator(config)

    print("\n  Running simulation...", end=" ", flush=True)
    t0 = time.perf_counter()
    result = sim.run()
    elapsed = time.perf_counter() - t0
    print(f"done in {elapsed:.3f}s")

    throughput = args.orders / elapsed if elapsed > 0 else float("inf")
    print(f"  Throughput: {throughput:,.0f} orders/sec")

    # Compute analytics
    report = Analytics.compute(
        result.order_book,
        result.orders_submitted,
        result.cancellations,
    )
    Analytics.print_report(report)

    # Final book state
    book = result.order_book
    print(f"\n  Final book: {book}")
    snap = book.get_depth_snapshot(5)
    if snap["bids"] or snap["asks"]:
        print(f"  Top 5 bids: {snap['bids']}")
        print(f"  Top 5 asks: {snap['asks']}")

    # Visualization
    if args.plot or args.save_plot:
        print("\n  Generating charts...")
        Visualizer.plot_all(
            book, report,
            save_path=args.save_plot,
        )

    print()


if __name__ == "__main__":
    main()
