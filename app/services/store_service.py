"""
Store service layer for store retrieval and geospatial lookup.
"""

from __future__ import annotations

import logging
import math
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.store_model import Store

logger = logging.getLogger(__name__)


class StoreService:
    """Business logic for store-related operations."""

    EARTH_RADIUS_MILES = 3958.8

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _validate_pagination(skip: int, limit: int) -> None:
        if skip < 0:
            raise ValidationError("Pagination 'skip' must be >= 0.", details={"skip": skip})
        if limit < 1 or limit > 100:
            raise ValidationError(
                "Pagination 'limit' must be between 1 and 100.",
                details={"limit": limit},
            )

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> None:
        if latitude < -90 or latitude > 90:
            raise ValidationError(
                "Latitude must be between -90 and 90.",
                details={"latitude": latitude},
            )
        if longitude < -180 or longitude > 180:
            raise ValidationError(
                "Longitude must be between -180 and 180.",
                details={"longitude": longitude},
            )

    @staticmethod
    def _haversine_distance_miles(
        origin_lat: float,
        origin_lng: float,
        target_lat: float,
        target_lng: float,
    ) -> float:
        """
        Compute great-circle distance between two coordinate points.
        """
        lat1 = math.radians(origin_lat)
        lng1 = math.radians(origin_lng)
        lat2 = math.radians(target_lat)
        lng2 = math.radians(target_lng)

        delta_lat = lat2 - lat1
        delta_lng = lng2 - lng1

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return StoreService.EARTH_RADIUS_MILES * c

    def get_all_stores(self, skip: int = 0, limit: int = 100) -> List[Store]:
        """Return paginated store list."""
        self._validate_pagination(skip, limit)
        return self.db.query(Store).order_by(Store.id.asc()).offset(skip).limit(limit).all()

    def get_store_count(self) -> int:
        """Return total number of stores."""
        return self.db.query(Store).count()

    def get_store_by_id(self, store_id: int) -> Store:
        """Return a single store by identifier."""
        store = self.db.query(Store).filter(Store.id == store_id).first()
        if not store:
            raise NotFoundError("Store", store_id)
        return store

    def get_nearby_stores(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 10.0,
        limit: int = 20,
    ) -> List[Tuple[Store, float]]:
        """
        Return stores within radius, sorted by distance ascending.
        """
        self._validate_coordinates(latitude, longitude)
        if radius_miles <= 0:
            raise ValidationError(
                "Radius must be greater than 0.",
                details={"radius_miles": radius_miles},
            )
        if limit < 1 or limit > 100:
            raise ValidationError(
                "Limit must be between 1 and 100.",
                details={"limit": limit},
            )

        stores = self.db.query(Store).all()
        matches: List[Tuple[Store, float]] = []

        for store in stores:
            distance = self._haversine_distance_miles(
                latitude,
                longitude,
                float(store.latitude),
                float(store.longitude),
            )
            if distance <= radius_miles:
                matches.append((store, round(distance, 2)))

        matches.sort(key=lambda item: item[1])
        logger.info(
            "Nearby store lookup lat=%s lng=%s radius=%s returned=%s",
            latitude,
            longitude,
            radius_miles,
            len(matches),
        )
        return matches[:limit]
