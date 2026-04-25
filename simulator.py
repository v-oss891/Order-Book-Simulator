"""
simulator.py — Realistic random order generator.

Generates a stream of limit and market orders with:
- Configurable buy/sell ratio and limit/market split
- Prices drawn from a Normal distribution around the current mid-price
- Quantities drawn from a LogNormal distribution (realistic size skew)
- Random cancellations of resting orders each round
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from order import Order, OrderType, Side
from order_book import OrderBook


@dataclass
class SimulatorConfig:
    """
    Configuration knobs for the market simulator.

    Attributes:
        initial_price:     Starting reference price.
        num_orders:        Total orders to generate.
        rounds:            Number of simulation rounds.
        limit_pct:         Fraction of orders that are LIMIT (0–1).
        buy_pct:           Fraction of orders that are BUY (0–1).
        price_std_pct:     Std-dev of price noise as a fraction of mid-price.
        qty_mu:            Mean of the log-normal quantity distribution.
        qty_sigma:         Sigma of the log-normal quantity distribution.
        cancel_prob:       Probability of a random cancellation each round.
        seed:              Random seed for reproducibility.
    """
    initial_price: float = 100.0
    num_orders: int = 5000
    rounds: int = 200
    limit_pct: float = 0.60
    buy_pct: float = 0.55
    price_std_pct: float = 0.005
    qty_mu: float = 2.5
    qty_sigma: float = 0.8
    cancel_prob: float = 0.15
    seed: Optional[int] = 42


@dataclass
class SimulationResult:
    """Container for everything produced by a simulation run."""
    order_book: OrderBook
    orders_submitted: List[Order] = field(default_factory=list)
    cancellations: int = 0


class Simulator:
    """
    Generates realistic market activity against an OrderBook.

    Usage:
        sim = Simulator(config)
        result = sim.run()
    """

    def __init__(self, config: Optional[SimulatorConfig] = None) -> None:
        self.config = config or SimulatorConfig()
        self.book = OrderBook()
        self._rng = random.Random(self.config.seed)
        self._all_orders: List[Order] = []
        self._cancellations: int = 0

    def run(self) -> SimulationResult:
        """
        Execute the full simulation.

        Distributes *num_orders* across *rounds* rounds,
        injecting random cancellations along the way.

        Returns:
            SimulationResult with the final book state and order list.
        """
        cfg = self.config
        orders_per_round = max(1, cfg.num_orders // cfg.rounds)
        remaining = cfg.num_orders

        for _ in range(cfg.rounds):
            batch = min(orders_per_round, remaining)
            remaining -= batch

            for _ in range(batch):
                order = self._generate_order()
                self._all_orders.append(order)
                self.book.add_order(order)

            # Random cancellation
            if self._rng.random() < cfg.cancel_prob:
                self._random_cancel()

            if remaining <= 0:
                break

        # Drain any leftover orders (rounding remainder)
        for _ in range(remaining):
            order = self._generate_order()
            self._all_orders.append(order)
            self.book.add_order(order)

        return SimulationResult(
            order_book=self.book,
            orders_submitted=self._all_orders,
            cancellations=self._cancellations,
        )

    # ──────────────────────────────────────────
    # Order generation helpers
    # ──────────────────────────────────────────

    def _generate_order(self) -> Order:
        """Create a single random order based on the current book state."""
        cfg = self.config

        # Side
        side = Side.BUY if self._rng.random() < cfg.buy_pct else Side.SELL

        # Order type
        is_limit = self._rng.random() < cfg.limit_pct
        order_type = OrderType.LIMIT if is_limit else OrderType.MARKET

        # Quantity — log-normal distribution
        qty = max(1, int(math.exp(self._rng.gauss(cfg.qty_mu, cfg.qty_sigma))))

        # Price
        price: Optional[float] = None
        if order_type == OrderType.LIMIT:
            mid = self.book.get_mid_price() or cfg.initial_price
            std = mid * cfg.price_std_pct
            raw = self._rng.gauss(mid, std)
            # Round to 2 decimal places (tick size = $0.01)
            price = round(max(0.01, raw), 2)

        return Order(
            side=side,
            order_type=order_type,
            price=price,
            quantity=qty,
        )

    def _random_cancel(self) -> None:
        """Cancel a random resting order from the book."""
        # Collect active resting order IDs
        active_ids = [
            o.order_id
            for o in self._all_orders
            if o.is_active and o.order_type == OrderType.LIMIT
        ]
        if not active_ids:
            return

        target_id = self._rng.choice(active_ids)
        if self.book.cancel_order(target_id):
            self._cancellations += 1
