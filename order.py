"""
order.py — Core data structures for the Order Book Simulator.

Contains the Order and Trade dataclasses that form the foundation
of the matching engine and trade logging system.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """Order side: BUY or SELL."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type: LIMIT or MARKET."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    """Order lifecycle status."""
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    """
    Represents a single order submitted to the exchange.

    Attributes:
        order_id:   Unique identifier (UUID).
        side:       BUY or SELL.
        order_type: LIMIT or MARKET.
        price:      Limit price (None for market orders).
        quantity:    Original quantity requested.
        timestamp:  Submission time.
        status:     Current lifecycle status.
        filled_qty: Quantity already filled through matching.
    """
    side: Side
    order_type: OrderType
    quantity: int
    price: Optional[float] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: OrderStatus = OrderStatus.OPEN
    filled_qty: int = 0

    @property
    def remaining_qty(self) -> int:
        """Quantity still waiting to be filled."""
        return self.quantity - self.filled_qty

    @property
    def is_active(self) -> bool:
        """True if the order can still participate in matching."""
        return self.status in (OrderStatus.OPEN, OrderStatus.PARTIAL)

    def fill(self, qty: int) -> None:
        """
        Record a (partial) fill of *qty* units.

        Updates filled_qty and transitions the status to PARTIAL
        or FILLED as appropriate.
        """
        self.filled_qty += qty
        if self.filled_qty >= self.quantity:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIAL

    def cancel(self) -> None:
        """Mark the order as cancelled."""
        self.status = OrderStatus.CANCELLED

    def __repr__(self) -> str:
        price_str = f"${self.price:.2f}" if self.price is not None else "MKT"
        return (
            f"Order({self.side.value} {self.order_type.value} "
            f"{price_str} x{self.quantity} [{self.status.value}])"
        )


@dataclass
class Trade:
    """
    Represents a single executed trade (fill).

    Attributes:
        trade_id:        Unique identifier (UUID).
        buyer_order_id:  Order ID of the buying side.
        seller_order_id: Order ID of the selling side.
        price:           Execution price.
        quantity:         Number of units traded.
        timestamp:       Execution time.
        aggressor_side:  Side of the order that initiated the trade.
    """
    buyer_order_id: str
    seller_order_id: str
    price: float
    quantity: int
    aggressor_side: Side
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"Trade({self.price:.2f} x{self.quantity} "
            f"agg={self.aggressor_side.value})"
        )
