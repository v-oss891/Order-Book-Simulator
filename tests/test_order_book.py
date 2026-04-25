"""
test_order_book.py — Pytest test suite for the order book matching engine.

Covers: basic matching, partial fills, price-time priority,
cancellation, market orders, FOK, IOC, spread/mid-price.
"""

import sys
import os

# Ensure the project root is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from order import Order, OrderType, OrderStatus, Side
from order_book import OrderBook


# ─── Test 1: Basic limit order match ────────────────────

def test_basic_limit_match(book: OrderBook) -> None:
    """A bid and ask at the same price produce exactly one trade."""
    sell = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=5)
    buy = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=100.0, quantity=5)

    book.add_order(sell)
    trades = book.add_order(buy)

    assert len(trades) == 1
    assert trades[0].price == 100.0
    assert trades[0].quantity == 5
    assert trades[0].buyer_order_id == buy.order_id
    assert trades[0].seller_order_id == sell.order_id
    assert buy.status == OrderStatus.FILLED
    assert sell.status == OrderStatus.FILLED


# ─── Test 2: Partial fill ───────────────────────────────

def test_partial_fill(book: OrderBook) -> None:
    """Buy 10 vs resting sell 6 → trade of 6, buy remains with 4."""
    sell = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=6)
    buy = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=100.0, quantity=10)

    book.add_order(sell)
    trades = book.add_order(buy)

    assert len(trades) == 1
    assert trades[0].quantity == 6
    assert buy.status == OrderStatus.PARTIAL
    assert buy.remaining_qty == 4
    assert sell.status == OrderStatus.FILLED

    # Buy order should be resting on the book
    snap = book.get_depth_snapshot()
    assert len(snap["bids"]) == 1
    assert snap["bids"][0] == (100.0, 4)


# ─── Test 3: Price-time priority ────────────────────────

def test_price_time_priority(book: OrderBook) -> None:
    """Two asks at the same price — the first submitted is filled first."""
    sell_first = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=5)
    sell_second = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=5)
    buy = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=100.0, quantity=5)

    book.add_order(sell_first)
    book.add_order(sell_second)
    trades = book.add_order(buy)

    assert len(trades) == 1
    # The first sell order should be the one that was matched
    assert trades[0].seller_order_id == sell_first.order_id
    assert sell_first.status == OrderStatus.FILLED
    assert sell_second.status == OrderStatus.OPEN


# ─── Test 4: Cancel order ──────────────────────────────

def test_cancel_order(book: OrderBook) -> None:
    """Cancelled order does not appear in depth and is not matched."""
    sell = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=5)
    book.add_order(sell)

    # Cancel it
    result = book.cancel_order(sell.order_id)
    assert result is True
    assert sell.status == OrderStatus.CANCELLED

    # Should not appear in depth snapshot
    snap = book.get_depth_snapshot()
    assert len(snap["asks"]) == 0

    # Should not be matched by incoming buy
    buy = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=100.0, quantity=5)
    trades = book.add_order(buy)
    assert len(trades) == 0


# ─── Test 5: Market order ──────────────────────────────

def test_market_order(book: OrderBook) -> None:
    """Market buy walks the ask side and fills until exhausted."""
    sell1 = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=3)
    sell2 = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=101.0, quantity=4)
    book.add_order(sell1)
    book.add_order(sell2)

    buy = Order(side=Side.BUY, order_type=OrderType.MARKET, quantity=6)
    trades = book.add_order(buy)

    assert len(trades) == 2
    assert trades[0].price == 100.0
    assert trades[0].quantity == 3
    assert trades[1].price == 101.0
    assert trades[1].quantity == 3
    assert buy.status == OrderStatus.FILLED

    # 1 unit should remain on the ask side at 101
    snap = book.get_depth_snapshot()
    assert len(snap["asks"]) == 1
    assert snap["asks"][0] == (101.0, 1)


# ─── Test 6: FOK — insufficient liquidity ──────────────

def test_fok_insufficient_liquidity(book: OrderBook) -> None:
    """FOK with insufficient liquidity → zero trades, order cancelled."""
    sell = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=3)
    book.add_order(sell)

    # FOK buy for 10 — only 3 available
    fok = Order(side=Side.BUY, order_type=OrderType.FOK, price=100.0, quantity=10)
    trades = book.add_order(fok)

    assert len(trades) == 0
    assert fok.status == OrderStatus.CANCELLED
    # Original sell should still be on the book untouched
    assert sell.status == OrderStatus.OPEN


def test_fok_sufficient_liquidity(book: OrderBook) -> None:
    """FOK with enough liquidity → fully filled."""
    sell = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=10)
    book.add_order(sell)

    fok = Order(side=Side.BUY, order_type=OrderType.FOK, price=100.0, quantity=5)
    trades = book.add_order(fok)

    assert len(trades) == 1
    assert trades[0].quantity == 5
    assert fok.status == OrderStatus.FILLED


# ─── Test 7: IOC — fill what you can, cancel rest ──────

def test_ioc_partial_fill(book: OrderBook) -> None:
    """IOC fills what it can, cancels remainder, never rests on book."""
    sell = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=100.0, quantity=3)
    book.add_order(sell)

    ioc = Order(side=Side.BUY, order_type=OrderType.IOC, price=100.0, quantity=10)
    trades = book.add_order(ioc)

    assert len(trades) == 1
    assert trades[0].quantity == 3
    assert ioc.status == OrderStatus.CANCELLED  # remainder cancelled
    assert ioc.filled_qty == 3

    # IOC should NOT rest on the book
    snap = book.get_depth_snapshot()
    assert len(snap["bids"]) == 0


def test_ioc_no_liquidity(book: OrderBook) -> None:
    """IOC with no liquidity → zero trades, order cancelled."""
    ioc = Order(side=Side.BUY, order_type=OrderType.IOC, price=100.0, quantity=5)
    trades = book.add_order(ioc)

    assert len(trades) == 0
    assert ioc.status == OrderStatus.CANCELLED


# ─── Test 8: Spread and mid-price ──────────────────────

def test_spread_and_mid_price(book: OrderBook) -> None:
    """Bid at 99, ask at 101 → spread == 2.0, mid == 100.0."""
    bid = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=99.0, quantity=5)
    ask = Order(side=Side.SELL, order_type=OrderType.LIMIT, price=101.0, quantity=5)

    book.add_order(bid)
    book.add_order(ask)

    assert book.get_spread() == 2.0
    assert book.get_mid_price() == 100.0
    assert book.get_best_bid() == 99.0
    assert book.get_best_ask() == 101.0
