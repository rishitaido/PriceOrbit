"""
Price History Statistics Service - PriceOrbit.

A pure, stateless computation layer.  No database session is required;
all methods operate on the raw ``price_history`` JSON list stored in the
Product model.

Design rationale
----------------
Keeping statistics logic here (not inside ProductService or the model)
means every calculation can be unit-tested by just passing a plain Python
list — no mocking, no database, no FastAPI app.  ProductService imports
this class and delegates; the router never touches it directly.
"""

import logging
import statistics
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PriceHistoryService:
    """
    Stateless analytics service for product price history.

    All public methods are ``@staticmethod`` so they can be called either
    on the class or on an instance injected via FastAPI ``Depends()``.
    """

    # Relative-slope threshold that separates "stable" from directional trends.
    # 0.02 = the fitted price must move by ≥ 2% of its mean per observation
    # before we call it "increasing" or "decreasing".
    TREND_THRESHOLD: float = 0.02

    # Minimum number of historical data points required to compute a trend
    # or a meaningful volatility score.
    MIN_POINTS_FOR_ANALYSIS: int = 3

    # ---------------------------------------------------------------------------
    # Parsing
    # ---------------------------------------------------------------------------

    @staticmethod
    def parse_history(history: List[dict]) -> List[Tuple[date, float]]:
        """
        Convert raw ``price_history`` JSON into typed ``(date, price)`` tuples.

        Entries are returned in **chronological order** (oldest first), which
        is the order required by the trend and change calculations.

        Malformed entries are skipped with a ``WARNING`` log instead of
        raising, so one bad record never breaks the entire endpoint.
        Specifically, entries are skipped when:

        - ``date`` or ``price`` key is missing
        - date string cannot be parsed as ISO-8601
        - price is negative

        Args:
            history: Raw ``price_history`` list from the Product ORM model,
                e.g. ``[{"date": "2025-01-15", "price": 3.99}, ...]``.

        Returns:
            List of ``(date, price)`` tuples sorted oldest → newest.
        """
        parsed: List[Tuple[date, float]] = []

        for entry in history:
            try:
                raw_date = entry.get("date")
                raw_price = entry.get("price")

                if raw_date is None or raw_price is None:
                    logger.warning("Skipping history entry with missing fields: %s", entry)
                    continue

                # Accept both "2025-01-15" and "2025-01-15T12:00:00" formats
                date_str = str(raw_date).split("T")[0]
                parsed_date = date.fromisoformat(date_str)
                parsed_price = float(raw_price)

                if parsed_price < 0:
                    logger.warning(
                        "Skipping history entry with negative price %.4f (date=%s)",
                        parsed_price,
                        parsed_date,
                    )
                    continue

                parsed.append((parsed_date, parsed_price))

            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning("Skipping malformed history entry %s: %s", entry, exc)

        return sorted(parsed, key=lambda t: t[0])

    # ---------------------------------------------------------------------------
    # Public statistics entry-point
    # ---------------------------------------------------------------------------

    @staticmethod
    def calculate_statistics(
        history: List[dict],
        current_price: Optional[float],
    ) -> Dict[str, Any]:
        """
        Compute a comprehensive statistics dictionary from raw price history.

        The ``current_price`` is included in aggregate calculations (min, max,
        average, volatility) so the "live" price is always represented.
        Change and trend metrics are derived from historical data only.

        Args:
            history: Raw ``price_history`` list from the Product model.
            current_price: Product's current price; may be ``None``.

        Returns:
            Dict with keys:

            - ``count`` (int): Number of historical data points.
            - ``min`` (float | None): Lowest observed price.
            - ``max`` (float | None): Highest observed price.
            - ``average`` (float | None): Mean of all prices incl. current.
            - ``volatility`` (float | None): Coefficient of variation (%).
            - ``change_7d`` (float | None): % change from 7 days ago.
            - ``change_30d`` (float | None): % change from 30 days ago.
            - ``trend`` (str): ``"increasing"``, ``"decreasing"``,
              ``"stable"``, or ``"insufficient_data"``.
        """
        parsed = PriceHistoryService.parse_history(history)
        hist_prices = [p for _, p in parsed]

        # Aggregate pool includes current_price when available
        all_prices = list(hist_prices)
        if current_price is not None:
            all_prices.append(current_price)

        if not all_prices:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "average": None,
                "volatility": None,
                "change_7d": None,
                "change_30d": None,
                "trend": "insufficient_data",
            }

        return {
            "count": len(hist_prices),
            "min": round(min(all_prices), 4),
            "max": round(max(all_prices), 4),
            "average": round(sum(all_prices) / len(all_prices), 4),
            "volatility": PriceHistoryService._calculate_volatility(all_prices),
            "change_7d": PriceHistoryService._calculate_change(parsed, current_price, 7),
            "change_30d": PriceHistoryService._calculate_change(parsed, current_price, 30),
            "trend": PriceHistoryService._calculate_trend(hist_prices),
        }

    # ---------------------------------------------------------------------------
    # Private calculation helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _calculate_trend(prices_chrono: List[float]) -> str:
        """
        Classify price direction using ordinary least-squares linear regression.

        An OLS slope is computed over the price series treated as evenly-spaced
        observations.  The slope is divided by the mean price to produce a
        scale-independent *relative slope*:

        ``relative_slope = slope / mean_price``

        Classification rules (``TREND_THRESHOLD = 0.02``):

        - ``relative_slope > +0.02``  → ``"increasing"``
        - ``relative_slope < -0.02``  → ``"decreasing"``
        - otherwise                   → ``"stable"``

        Requires at least ``MIN_POINTS_FOR_ANALYSIS`` data points; returns
        ``"insufficient_data"`` otherwise.

        Args:
            prices_chrono: Prices in chronological order (oldest first).

        Returns:
            One of ``"increasing"``, ``"decreasing"``, ``"stable"``,
            ``"insufficient_data"``.
        """
        if len(prices_chrono) < PriceHistoryService.MIN_POINTS_FOR_ANALYSIS:
            return "insufficient_data"

        n = len(prices_chrono)
        mean_x = (n - 1) / 2.0
        mean_y = sum(prices_chrono) / n

        if mean_y == 0:
            return "stable"

        numerator = sum(
            (i - mean_x) * (p - mean_y) for i, p in enumerate(prices_chrono)
        )
        denominator = sum((i - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator
        relative_slope = slope / mean_y

        logger.debug(
            "Trend OLS: n=%d slope=%.6f relative_slope=%.6f threshold=%.4f",
            n,
            slope,
            relative_slope,
            PriceHistoryService.TREND_THRESHOLD,
        )

        if relative_slope > PriceHistoryService.TREND_THRESHOLD:
            return "increasing"
        if relative_slope < -PriceHistoryService.TREND_THRESHOLD:
            return "decreasing"
        return "stable"

    @staticmethod
    def _calculate_change(
        parsed: List[Tuple[date, float]],
        current_price: Optional[float],
        days: int,
    ) -> Optional[float]:
        """
        Percentage price change from ``days`` ago to ``current_price``.

        Algorithm:

        1. Compute ``target_date = today - days``.
        2. Filter parsed history to entries on or before ``target_date``.
        3. Pick the entry **closest** to (but not after) ``target_date``
           — i.e. the most-recent old price available.
        4. Return ``(current - old) / old * 100``, rounded to 2 dp.

        Returns ``None`` when:

        - ``current_price`` is unknown
        - no historical entries are old enough (metric only appears with
          sufficient history)
        - the reference price is zero (division undefined)

        Args:
            parsed: Chronologically-sorted ``(date, price)`` tuples.
            current_price: Product's current price.
            days: Lookback window in calendar days.

        Returns:
            Percentage change (positive = price increased), or ``None``.
        """
        if current_price is None or not parsed:
            return None

        target_date = date.today() - timedelta(days=days)
        candidates = [(d, p) for d, p in parsed if d <= target_date]

        if not candidates:
            return None

        # Most recent entry that is at least ``days`` old
        ref_date, old_price = max(candidates, key=lambda t: t[0])

        if old_price == 0:
            return None

        change_pct = ((current_price - old_price) / old_price) * 100
        logger.debug(
            "change_%dd: ref_date=%s old=%.4f current=%.4f → %.2f%%",
            days,
            ref_date,
            old_price,
            current_price,
            change_pct,
        )
        return round(change_pct, 2)

    @staticmethod
    def _calculate_volatility(prices: List[float]) -> Optional[float]:
        """
        Coefficient of variation (CV) as a percentage.

        ``CV = (std_dev / mean) * 100``

        A CV of 0 % means perfectly stable prices; higher values mean more
        volatility.  Two or more data points are required.

        Args:
            prices: Price values to analyse (order does not matter).

        Returns:
            CV percentage rounded to 2 decimal places, or ``None`` if
            fewer than 2 prices are provided.
        """
        if len(prices) < 2:
            return None

        mean_price = sum(prices) / len(prices)
        if mean_price == 0:
            return None

        std_dev = statistics.stdev(prices)
        cv_pct = (std_dev / mean_price) * 100
        return round(cv_pct, 2)

    # ---------------------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------------------

    @staticmethod
    def clean_old_history(
        history: List[dict],
        max_days: int = 365,
    ) -> List[dict]:
        """
        Remove price history entries older than ``max_days`` from today.

        Entries with unparseable dates are **retained** (not silently
        dropped) so historical data is never lost to a format issue.
        A ``WARNING`` is logged for each retained-but-unparseable entry.

        The returned list is sorted **newest-first** to match the
        convention used across the rest of the codebase.

        Args:
            history: Raw ``price_history`` list from the Product model.
            max_days: Cutoff in calendar days before today (default 365).

        Returns:
            Filtered and sorted list.
        """
        cutoff = date.today() - timedelta(days=max_days)
        cleaned: List[dict] = []

        for entry in history:
            try:
                date_str = str(entry.get("date", "")).split("T")[0]
                entry_date = date.fromisoformat(date_str)
                if entry_date >= cutoff:
                    cleaned.append(entry)
                else:
                    logger.debug("Pruning old history entry: date=%s", entry_date)
            except (ValueError, TypeError):
                logger.warning(
                    "Retaining history entry with unparseable date: %s", entry
                )
                cleaned.append(entry)

        cleaned.sort(key=lambda e: str(e.get("date", "")), reverse=True)
        return cleaned

    @staticmethod
    def format_response(
        product_id: int,
        product_name: str,
        current_price: Optional[float],
        history: List[dict],
        stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build the standardised price-history API response dict.

        Args:
            product_id: Primary key of the product.
            product_name: Human-readable product name.
            current_price: Product's current price (may be ``None``).
            history: Raw ``price_history`` list (newest-first).
            stats: Pre-computed statistics dict from
                :meth:`calculate_statistics`.

        Returns:
            API-ready response dictionary.
        """
        return {
            "product_id": product_id,
            "product_name": product_name,
            "current_price": current_price,
            "history": history,
            "statistics": stats,
        }
