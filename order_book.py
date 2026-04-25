"""
order_book.py — Price-time priority limit order book.

Implements a full matching engine with:
- SortedDict-backed bid/ask price levels
- deque-based FIFO queues at each price level
- Support for LIMIT, MARKET, IOC, and FOK order matching
- Lazy cancellation for O(1) cancel performance
- Depth snapshots, spread tracking, and order cancellation
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sortedcontainers import SortedDict

from order import Order, OrderStatus, OrderType, Side, Trade


class OrderBook:
    """
    A price-time priority limit order book.

    Bids are stored in *descending* price order (best bid = highest price).
    Asks are stored in *ascending* price order (best ask = lowest price).
    Within each price level, orders are matched FIFO via a deque.

    Cancellation uses a lazy pattern: cancelled orders remain in the
    deque but are skipped during matching and depth calculations.

    Public API:
        add_order(order)        → list[Trade]
        cancel_order(order_id)  → bool
        get_best_bid()          → Optional[float]
        get_best_ask()          → Optional[float]
        get_mid_price()         → Optional[float]
        get_spread()            → Optional[float]
        get_depth_snapshot(n)   → dict
    """

    def __init__(self) -> None:
        # Bids: highest price first  → use negated keys in SortedDict
        # Asks: lowest price first   → natural SortedDict order
        self._bids: SortedDict = SortedDict()  # neg_price → deque[Order]
        self._asks: SortedDict = SortedDict()  # price     → deque[Order]

        # Fast lookup by order_id for cancellation
        self._orders: Dict[str, Order] = {}

        # Complete trade log
        self.trade_log: List[Trade] = []

        # Spread / mid-price history for analytics
        self.spread_history: List[Tuple[datetime, float]] = []
        self.mid_price_history: List[Tuple[datetime, float]] = []

    # ──────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────

    def add_order(self, order: Order) -> List[Trade]:
        """
        Submit an order to the book.

        The matching engine will attempt to fill the order immediately
        against the opposite side.  Behaviour depends on order type:
        - LIMIT:  match then rest remainder on book
        - MARKET: match then cancel remainder
        - IOC:    match then cancel remainder (never rests)
        - FOK:    check liquidity first; fill entirely or cancel

        Returns:
            List of Trade objects produced by this submission.
        """
        self._orders[order.order_id] = order
        trades: List[Trade] = []

        if order.order_type == OrderType.MARKET:
            trades = self._match_market(order)
        elif order.order_type == OrderType.IOC:
            trades = self._match_ioc(order)
        elif order.order_type == OrderType.FOK:
            trades = self._match_fok(order)
        else:
            trades = self._match_limit(order)

        # Record snapshots after each order event
        self._record_snapshot()

        return trades

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a resting order by its ID (lazy cancellation).

        The order is marked as cancelled but NOT eagerly removed
        from the price-level deque.  It will be skipped during
        matching and excluded from depth snapshots.

        Returns True if the order was found and cancelled,
        False otherwise.
        """
        order = self._orders.get(order_id)
        if order is None or not order.is_active:
            return False

        order.cancel()
        # Lazy: do NOT remove from deque — it will be skipped during matching
        return True

    def get_best_bid(self) -> Optional[float]:
        """Return the highest resting bid price, or None."""
        self._clean_top_bids()
        if not self._bids:
            return None
        return -self._bids.keys()[0]

    def get_best_ask(self) -> Optional[float]:
        """Return the lowest resting ask price, or None."""
        self._clean_top_asks()
        if not self._asks:
            return None
        return self._asks.keys()[0]

    def get_mid_price(self) -> Optional[float]:
        """Return (best_bid + best_ask) / 2, or None."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return round((bid + ask) / 2, 4)

    def get_spread(self) -> Optional[float]:
        """Return best_ask − best_bid, or None."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return round(ask - bid, 4)

    def get_depth_snapshot(self, levels: int = 10) -> Dict:
        """
        Return the top *levels* price levels on each side.

        Cancelled orders are excluded from the quantity totals.

        Returns:
            {
                "bids": [(price, total_qty), ...],  # descending by price
                "asks": [(price, total_qty), ...],  # ascending by price
            }
        """
        bids: List[Tuple[float, int]] = []
        for neg_price in self._bids.keys():
            q = self._bids[neg_price]
            total = sum(o.remaining_qty for o in q if o.is_active)
            if total > 0:
                bids.append((-neg_price, total))
            if len(bids) >= levels:
                break

        asks: List[Tuple[float, int]] = []
        for price in self._asks.keys():
            q = self._asks[price]
            total = sum(o.remaining_qty for o in q if o.is_active)
            if total > 0:
                asks.append((price, total))
            if len(asks) >= levels:
                break

        return {"bids": bids, "asks": asks}

    @property
    def total_bid_volume(self) -> int:
        """Total resting bid quantity across all price levels."""
        return sum(
            o.remaining_qty for q in self._bids.values()
            for o in q if o.is_active
        )

    @property
    def total_ask_volume(self) -> int:
        """Total resting ask quantity across all price levels."""
        return sum(
            o.remaining_qty for q in self._asks.values()
            for o in q if o.is_active
        )

    def get_book_imbalance(self) -> float:
        """
        Compute order-book imbalance:
            (bid_vol − ask_vol) / (bid_vol + ask_vol)

        Returns 0.0 if the book is empty.
        """
        bv = self.total_bid_volume
        av = self.total_ask_volume
        total = bv + av
        if total == 0:
            return 0.0
        return round((bv - av) / total, 4)

    # ──────────────────────────────────────────
    # Matching engine internals
    # ──────────────────────────────────────────

    def _match_limit(self, order: Order) -> List[Trade]:
        """Match a LIMIT order against the opposite side, then rest remainder."""
        trades: List[Trade] = []

        if order.side == Side.BUY:
            trades = self._match_buy_limit(order)
        else:
            trades = self._match_sell_limit(order)

        # Rest any unfilled remainder on the book
        if order.remaining_qty > 0 and order.is_active:
            self._rest_order(order)

        return trades

    def _match_market(self, order: Order) -> List[Trade]:
        """Match a MARKET order, walking the opposite side until filled."""
        trades: List[Trade] = []

        if order.side == Side.BUY:
            trades = self._match_buy_market(order)
        else:
            trades = self._match_sell_market(order)

        # Cancel any unfilled remainder (no resting for market orders)
        if order.remaining_qty > 0:
            order.cancel()

        return trades

    def _match_ioc(self, order: Order) -> List[Trade]:
        """
        Match an IOC (Immediate-Or-Cancel) order.

        Fills whatever is available immediately, then cancels
        any unfilled remainder.  Never rests on the book.
        """
        trades: List[Trade] = []

        if order.side == Side.BUY:
            trades = self._match_buy_limit(order)
        else:
            trades = self._match_sell_limit(order)

        # Cancel remainder — IOC orders never rest
        if order.remaining_qty > 0:
            order.cancel()

        return trades

    def _match_fok(self, order: Order) -> List[Trade]:
        """
        Match a FOK (Fill-Or-Kill) order.

        Checks available liquidity at the limit price BEFORE
        executing.  If insufficient liquidity exists, the entire
        order is cancelled with zero fills.
        """
        # Check if enough liquidity exists
        available = self._available_liquidity(order)
        if available < order.quantity:
            order.cancel()
            return []

        # Sufficient liquidity — execute as a normal limit match
        trades: List[Trade] = []
        if order.side == Side.BUY:
            trades = self._match_buy_limit(order)
        else:
            trades = self._match_sell_limit(order)

        return trades

    def _available_liquidity(self, order: Order) -> int:
        """
        Calculate available liquidity on the opposite side at the
        order's limit price or better.
        """
        total = 0
        if order.side == Side.BUY:
            for ask_price in self._asks.keys():
                if order.price < ask_price:  # type: ignore[operator]
                    break
                q = self._asks[ask_price]
                total += sum(o.remaining_qty for o in q if o.is_active)
                if total >= order.quantity:
                    return total
        else:
            for neg_price in self._bids.keys():
                bid_price = -neg_price
                if order.price > bid_price:  # type: ignore[operator]
                    break
                q = self._bids[neg_price]
                total += sum(o.remaining_qty for o in q if o.is_active)
                if total >= order.quantity:
                    return total

        return total

    def _match_buy_limit(self, order: Order) -> List[Trade]:
        """Try to fill a BUY LIMIT against resting asks."""
        trades: List[Trade] = []

        while order.remaining_qty > 0 and self._asks:
            best_ask_price = self._asks.keys()[0]
            if order.price < best_ask_price:  # type: ignore[operator]
                break  # limit price too low

            trades += self._fill_against_asks(order, best_ask_price)

        return trades

    def _match_sell_limit(self, order: Order) -> List[Trade]:
        """Try to fill a SELL LIMIT against resting bids."""
        trades: List[Trade] = []

        while order.remaining_qty > 0 and self._bids:
            best_bid_neg = self._bids.keys()[0]
            best_bid_price = -best_bid_neg
            if order.price > best_bid_price:  # type: ignore[operator]
                break  # limit price too high

            trades += self._fill_against_bids(order, best_bid_neg)

        return trades

    def _match_buy_market(self, order: Order) -> List[Trade]:
        """Walk the ask side until the BUY MARKET order is filled."""
        trades: List[Trade] = []

        while order.remaining_qty > 0 and self._asks:
            best_ask_price = self._asks.keys()[0]
            trades += self._fill_against_asks(order, best_ask_price)

        return trades

    def _match_sell_market(self, order: Order) -> List[Trade]:
        """Walk the bid side until the SELL MARKET order is filled."""
        trades: List[Trade] = []

        while order.remaining_qty > 0 and self._bids:
            best_bid_neg = self._bids.keys()[0]
            trades += self._fill_against_bids(order, best_bid_neg)

        return trades

    def _fill_against_asks(
        self, incoming: Order, ask_price: float
    ) -> List[Trade]:
        """Execute fills against the ask queue at *ask_price*."""
        trades: List[Trade] = []
        q = self._asks[ask_price]

        while incoming.remaining_qty > 0 and q:
            resting = q[0]

            # Lazy cancellation: skip cancelled/filled orders
            if not resting.is_active:
                q.popleft()
                continue

            fill_qty = min(incoming.remaining_qty, resting.remaining_qty)

            incoming.fill(fill_qty)
            resting.fill(fill_qty)

            trade = Trade(
                buyer_order_id=incoming.order_id,
                seller_order_id=resting.order_id,
                price=ask_price,
                quantity=fill_qty,
                aggressor_side=incoming.side,
            )
            trades.append(trade)
            self.trade_log.append(trade)

            if not resting.is_active:
                q.popleft()

        if not q:
            del self._asks[ask_price]

        return trades

    def _fill_against_bids(
        self, incoming: Order, neg_price: float
    ) -> List[Trade]:
        """Execute fills against the bid queue at the negated price key."""
        trades: List[Trade] = []
        real_price = -neg_price
        q = self._bids[neg_price]

        while incoming.remaining_qty > 0 and q:
            resting = q[0]

            # Lazy cancellation: skip cancelled/filled orders
            if not resting.is_active:
                q.popleft()
                continue

            fill_qty = min(incoming.remaining_qty, resting.remaining_qty)

            incoming.fill(fill_qty)
            resting.fill(fill_qty)

            trade = Trade(
                buyer_order_id=resting.order_id,
                seller_order_id=incoming.order_id,
                price=real_price,
                quantity=fill_qty,
                aggressor_side=incoming.side,
            )
            trades.append(trade)
            self.trade_log.append(trade)

            if not resting.is_active:
                q.popleft()

        if not q:
            del self._bids[neg_price]

        return trades

    def _rest_order(self, order: Order) -> None:
        """Place an unfilled (remainder of a) LIMIT order on the book."""
        if order.side == Side.BUY:
            neg_price = -order.price  # type: ignore[operator]
            if neg_price not in self._bids:
                self._bids[neg_price] = deque()
            self._bids[neg_price].append(order)
        else:
            price = order.price
            if price not in self._asks:
                self._asks[price] = deque()
            self._asks[price].append(order)

    def _clean_top_bids(self) -> None:
        """Remove stale cancelled orders from the top of the bid side."""
        while self._bids:
            q = self._bids[self._bids.keys()[0]]
            while q and not q[0].is_active:
                q.popleft()
            if not q:
                del self._bids[self._bids.keys()[0]]
            else:
                break

    def _clean_top_asks(self) -> None:
        """Remove stale cancelled orders from the top of the ask side."""
        while self._asks:
            q = self._asks[self._asks.keys()[0]]
            while q and not q[0].is_active:
                q.popleft()
            if not q:
                del self._asks[self._asks.keys()[0]]
            else:
                break

    def _record_snapshot(self) -> None:
        """Capture current spread and mid-price for analytics."""
        now = datetime.now(timezone.utc)
        spread = self.get_spread()
        mid = self.get_mid_price()
        if spread is not None:
            self.spread_history.append((now, spread))
        if mid is not None:
            self.mid_price_history.append((now, mid))

    # ──────────────────────────────────────────
    # Diagnostics
    # ──────────────────────────────────────────

    def __repr__(self) -> str:
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        bid_str = f"${bid:.2f}" if bid else "---"
        ask_str = f"${ask:.2f}" if ask else "---"
        return (
            f"OrderBook(bid={bid_str}, ask={ask_str}, "
            f"trades={len(self.trade_log)})"
        )
