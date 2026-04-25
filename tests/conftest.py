"""
conftest.py — Shared pytest fixtures for order book tests.
"""

import pytest

from order_book import OrderBook


@pytest.fixture
def book() -> OrderBook:
    """Provide a fresh OrderBook instance for each test."""
    return OrderBook()
