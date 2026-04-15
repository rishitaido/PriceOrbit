"""Deterministic tariff resolution based on local tariff reference data."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_RATE_TYPES = {"ad_valorem", "specific", "mixed", "duty_free"}
ALLOWED_REVIEW_STATUSES = {"incomplete", "needs_review", "verified", "manual_override"}


@dataclass(frozen=True)
class TariffRow:
    product_name: str
    hts_code: str
    tariff_rate: Decimal
    origin_country: str
    import_dependency: str


@dataclass(frozen=True)
class TariffResolution:
    matched: bool
    match_strategy: str
    confidence_score: Decimal
    review_status: str
    verification_notes: str
    tariff_rate: Optional[Decimal]
    rate_type: Optional[str]
    specific_duty_value: Optional[str]
    hts_code: Optional[str]
    origin_country: Optional[str]
    import_dependency: Optional[str]
    verification_source: str
    source_url: str


@dataclass(frozen=True)
class _TariffIndex:
    rows: List[TariffRow]
    by_name: Dict[str, TariffRow]
    by_hts_origin: Dict[Tuple[str, str], TariffRow]
    by_hts: Dict[str, List[TariffRow]]


class TariffResolverService:
    """Resolve product tariff metadata using deterministic matching rules."""

    _index_cache: Dict[str, Tuple[float, int, _TariffIndex]] = {}

    def __init__(
        self,
        *,
        csv_path: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
    ) -> None:
        self.csv_path = self._resolve_path(csv_path or settings.TARIFF_DATA_CSV_PATH)
        threshold = settings.TARIFF_CONFIDENCE_THRESHOLD if confidence_threshold is None else confidence_threshold
        self.confidence_threshold = max(0.0, min(float(threshold), 100.0))
        self.source_url = settings.TARIFF_SOURCE_URL

    @staticmethod
    def _resolve_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate

    @staticmethod
    def _normalize_text(raw: str) -> str:
        text = str(raw or "").lower()
        text = text.replace("&", " and ")
        text = re.sub(r"[^a-z0-9 ]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _normalize_code(raw: str) -> str:
        return re.sub(r"[^0-9.]", "", str(raw or "").strip())

    @classmethod
    def _singularize(cls, token: str) -> str:
        if token.endswith("ies") and len(token) > 4:
            return token[:-3] + "y"
        if token.endswith("es") and len(token) > 3:
            return token[:-2]
        if token.endswith("s") and len(token) > 3:
            return token[:-1]
        return token

    @classmethod
    def _token_set(cls, raw: str) -> set[str]:
        normalized = cls._normalize_text(raw)
        return {cls._singularize(token) for token in normalized.split(" ") if token}

    @staticmethod
    def _coerce_decimal(raw: str, default: Decimal = Decimal("0")) -> Decimal:
        try:
            value = Decimal(str(raw).strip() or "0")
        except (InvalidOperation, ValueError):
            return default
        if value < 0:
            return Decimal("0")
        return value

    def _load_index(self) -> _TariffIndex:
        if not self.csv_path.exists():
            logger.warning("Tariff CSV file not found at %s", self.csv_path)
            return _TariffIndex(rows=[], by_name={}, by_hts_origin={}, by_hts={})

        stat = self.csv_path.stat()
        cache_key = str(self.csv_path)
        cached = self._index_cache.get(cache_key)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]

        rows: List[TariffRow] = []
        by_name: Dict[str, TariffRow] = {}
        by_hts_origin: Dict[Tuple[str, str], TariffRow] = {}
        by_hts: Dict[str, List[TariffRow]] = {}

        with self.csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for raw_row in reader:
                product_name = (raw_row.get("product_name") or raw_row.get("name") or "").strip()
                if not product_name:
                    continue

                hts_code = self._normalize_code(raw_row.get("hts_code") or "")
                origin_country = (raw_row.get("origin_country") or "").strip()
                tariff_rate = self._coerce_decimal(raw_row.get("tariff_rate") or "0")
                import_dependency = (raw_row.get("import_dependency") or "Unknown").strip() or "Unknown"

                row = TariffRow(
                    product_name=product_name,
                    hts_code=hts_code,
                    tariff_rate=tariff_rate,
                    origin_country=origin_country,
                    import_dependency=import_dependency,
                )
                rows.append(row)

                name_key = self._normalize_text(product_name)
                by_name.setdefault(name_key, row)

                if hts_code:
                    by_hts.setdefault(hts_code, []).append(row)

                origin_key = self._normalize_text(origin_country)
                if hts_code and origin_key:
                    by_hts_origin.setdefault((hts_code, origin_key), row)

        index = _TariffIndex(
            rows=rows,
            by_name=by_name,
            by_hts_origin=by_hts_origin,
            by_hts=by_hts,
        )
        self._index_cache[cache_key] = (stat.st_mtime, stat.st_size, index)
        return index

    @staticmethod
    def _f1_similarity(a_tokens: set[str], b_tokens: set[str]) -> float:
        if not a_tokens or not b_tokens:
            return 0.0
        overlap = len(a_tokens & b_tokens)
        if overlap == 0:
            return 0.0
        precision = overlap / len(a_tokens)
        recall = overlap / len(b_tokens)
        return (2 * precision * recall) / (precision + recall)

    @staticmethod
    def _derive_rate_type(tariff_rate: Decimal) -> str:
        return "duty_free" if tariff_rate <= 0 else "ad_valorem"

    def _derive_review_status(self, confidence_score: Decimal, matched: bool) -> str:
        if not matched:
            return "incomplete"
        return "verified" if float(confidence_score) >= self.confidence_threshold else "needs_review"

    def _build_resolution(
        self,
        *,
        row: Optional[TariffRow],
        matched: bool,
        match_strategy: str,
        confidence_score: Decimal,
        verification_notes: str,
    ) -> TariffResolution:
        if row is None:
            return TariffResolution(
                matched=False,
                match_strategy=match_strategy,
                confidence_score=Decimal("0.00"),
                review_status="incomplete",
                verification_notes=verification_notes,
                tariff_rate=None,
                rate_type=None,
                specific_duty_value=None,
                hts_code=None,
                origin_country=None,
                import_dependency=None,
                verification_source="tariff_rates_csv",
                source_url=self.source_url,
            )

        score = max(Decimal("0"), min(confidence_score, Decimal("100"))).quantize(Decimal("0.01"))
        rate_type = self._derive_rate_type(row.tariff_rate)
        return TariffResolution(
            matched=matched,
            match_strategy=match_strategy,
            confidence_score=score,
            review_status=self._derive_review_status(score, matched=matched),
            verification_notes=verification_notes,
            tariff_rate=row.tariff_rate.quantize(Decimal("0.01")),
            rate_type=rate_type,
            specific_duty_value=None,
            hts_code=row.hts_code or None,
            origin_country=row.origin_country or None,
            import_dependency=row.import_dependency or None,
            verification_source="tariff_rates_csv",
            source_url=self.source_url,
        )

    def resolve(
        self,
        *,
        product_name: str,
        hts_code: Optional[str] = None,
        origin_country: Optional[str] = None,
    ) -> TariffResolution:
        """
        Resolve tariff metadata for a product using deterministic rule order.

        Match order:
        1) Exact HTS + origin
        2) Unique HTS
        3) Exact normalized product name
        4) Token-based F1 similarity (>= 0.60)
        """
        index = self._load_index()
        if not index.rows:
            return self._build_resolution(
                row=None,
                matched=False,
                match_strategy="no_reference_data",
                confidence_score=Decimal("0"),
                verification_notes=f"Tariff reference CSV not available at {self.csv_path}",
            )

        normalized_hts = self._normalize_code(hts_code or "")
        normalized_origin = self._normalize_text(origin_country or "")

        if normalized_hts and normalized_origin:
            direct_row = index.by_hts_origin.get((normalized_hts, normalized_origin))
            if direct_row is not None:
                return self._build_resolution(
                    row=direct_row,
                    matched=True,
                    match_strategy="hts_origin_exact",
                    confidence_score=Decimal("100"),
                    verification_notes="Matched by exact HTS code and origin country.",
                )

        if normalized_hts:
            hts_rows = index.by_hts.get(normalized_hts, [])
            if len(hts_rows) == 1:
                return self._build_resolution(
                    row=hts_rows[0],
                    matched=True,
                    match_strategy="hts_unique",
                    confidence_score=Decimal("95"),
                    verification_notes="Matched by unique HTS code in tariff reference data.",
                )

        normalized_name = self._normalize_text(product_name)
        if normalized_name in index.by_name:
            return self._build_resolution(
                row=index.by_name[normalized_name],
                matched=True,
                match_strategy="name_exact",
                confidence_score=Decimal("92"),
                verification_notes="Matched by exact normalized product name.",
            )

        product_tokens = self._token_set(product_name)
        best_row: Optional[TariffRow] = None
        best_score = 0.0
        for row in index.rows:
            candidate_score = self._f1_similarity(product_tokens, self._token_set(row.product_name))
            if candidate_score > best_score:
                best_score = candidate_score
                best_row = row

        if best_row is not None and best_score >= 0.60:
            score = Decimal(str(round(best_score * 100, 2)))
            return self._build_resolution(
                row=best_row,
                matched=True,
                match_strategy="token_similarity",
                confidence_score=score,
                verification_notes=(
                    "Matched by token similarity to tariff reference product "
                    f"'{best_row.product_name}' (F1={best_score:.2f})."
                ),
            )

        return self._build_resolution(
            row=None,
            matched=False,
            match_strategy="unmatched",
            confidence_score=Decimal("0"),
            verification_notes="No deterministic tariff match found.",
        )
