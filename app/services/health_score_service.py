"""
Health score computation service.

Sprint 2 formula:
- Tariff rate: 40% weight
- Import dependency: 30% weight
- Price volatility: 30% weight
"""

from __future__ import annotations

import statistics
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List


class HealthScoreService:
    """Pure computation service for product health scores."""

    MAX_TARIFF_RATE: float = 25.0
    MAX_TARIFF_PENALTY: float = 40.0
    MAX_DEPENDENCY_PENALTY: float = 30.0
    MAX_VOLATILITY_PENALTY: float = 30.0
    MIN_HISTORY_POINTS: int = 3

    DEPENDENCY_PENALTIES = {
        "Low": 0.0,
        "Medium": 15.0,
        "High": 30.0,
        "Unknown": 10.0,
    }

    @staticmethod
    def _normalise_dependency(value: Any) -> str:
        candidate = (str(value or "Unknown")).strip().capitalize()
        return candidate if candidate in HealthScoreService.DEPENDENCY_PENALTIES else "Unknown"

    @staticmethod
    def _extract_prices(history: List[dict]) -> List[float]:
        prices: List[float] = []
        for entry in history or []:
            try:
                raw = entry.get("price")
                if raw is None:
                    continue
                price = float(raw)
                if price >= 0:
                    prices.append(price)
            except (TypeError, ValueError, AttributeError):
                continue
        return prices

    @staticmethod
    def calculate_volatility_penalty(price_history: List[dict]) -> float:
        """
        Convert price-history volatility to a 0-30 penalty.

        Uses coefficient of variation (std_dev / mean), clamped to [0, 1].
        """
        prices = HealthScoreService._extract_prices(price_history)
        if len(prices) < HealthScoreService.MIN_HISTORY_POINTS:
            return 0.0

        mean_price = statistics.mean(prices)
        if mean_price == 0:
            return 0.0

        std_dev = statistics.stdev(prices)
        cv = std_dev / mean_price
        cv_clamped = max(0.0, min(1.0, cv))
        return cv_clamped * HealthScoreService.MAX_VOLATILITY_PENALTY

    @staticmethod
    def calculate_health_score(product: Any) -> Decimal:
        """Calculate a health score in the range [0, 100]."""
        tariff_rate = float(getattr(product, "tariff_rate", 0) or 0)
        tariff_penalty = min(
            (tariff_rate / HealthScoreService.MAX_TARIFF_RATE) * HealthScoreService.MAX_TARIFF_PENALTY,
            HealthScoreService.MAX_TARIFF_PENALTY,
        )

        dependency = HealthScoreService._normalise_dependency(
            getattr(product, "import_dependency", "Unknown")
        )
        dependency_penalty = HealthScoreService.DEPENDENCY_PENALTIES[dependency]

        price_history = getattr(product, "price_history", []) or []
        volatility_penalty = HealthScoreService.calculate_volatility_penalty(price_history)

        raw_score = 100.0 - tariff_penalty - dependency_penalty - volatility_penalty
        final_score = max(0.0, min(100.0, raw_score))
        return Decimal(str(final_score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
