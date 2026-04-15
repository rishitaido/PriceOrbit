"""
Update tariff rates in data/tariff_rates.csv from the USITC REST search endpoint.

This script reads HTS codes from the local tariff CSV, looks each code up in:
https://hts.usitc.gov/reststop/search?keyword=<hts_code>
and refreshes `tariff_rate` when an ad valorem percentage can be parsed from
USITC's `general` duty expression.

For specific-duty-only lines (for example, cents/kg without a `%`), the script
keeps the existing `tariff_rate` value and marks the row for manual review.

Usage examples:
    python scripts/update_tariffs_from_usitc.py --dry-run
    python scripts/update_tariffs_from_usitc.py --csv data/tariff_rates.csv
    python scripts/update_tariffs_from_usitc.py --resolve-products
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent

USITC_SEARCH_URL = "https://hts.usitc.gov/reststop/search"
DEFAULT_CSV_PATH = "data/tariff_rates.csv"

REQUIRED_COLUMNS = {
    "product_name",
    "hts_code",
    "tariff_rate",
    "origin_country",
    "import_dependency",
}

AUDIT_COLUMNS = [
    "usitc_general",
    "usitc_special",
    "usitc_rate_type",
    "usitc_parse_status",
    "usitc_updated_at",
]


@dataclass
class RowUpdateResult:
    product_name: str
    hts_code: str
    old_rate: Optional[Decimal]
    new_rate: Optional[Decimal]
    changed: bool
    parse_status: str
    rate_type: str
    general_text: str
    special_text: str


@dataclass
class RunSummary:
    total_rows: int = 0
    looked_up: int = 0
    matched: int = 0
    changed: int = 0
    unchanged: int = 0
    missing_hts: int = 0
    no_match: int = 0
    parse_unresolved: int = 0
    errors: int = 0


def _resolve_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _normalize_hts(raw: str) -> str:
    return re.sub(r"[^0-9]", "", str(raw or ""))


def _coerce_decimal(raw: Any) -> Optional[Decimal]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _is_specific_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ["¢", "cent", "/kg", "/m", "/l", "/doz", "/pair", "/ea", "/unit", " per "])


def parse_general_rate(general_text: str) -> Tuple[Optional[Decimal], str, str]:
    """
    Parse USITC `general` duty expression.

    Returns:
        (percent_or_none, rate_type, parse_status)
    """
    text = str(general_text or "").strip()
    if not text:
        return None, "unknown", "missing_general"

    lowered = text.lower()
    if "free" in lowered:
        return Decimal("0.00"), "duty_free", "ok_free"

    percent_tokens = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    if not percent_tokens:
        return None, "specific", "non_ad_valorem"

    try:
        percent = Decimal(percent_tokens[0]).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None, "unknown", "parse_error"

    if _is_specific_marker(text) or len(percent_tokens) > 1:
        return percent, "mixed", "ok_mixed"

    return percent, "ad_valorem", "ok_ad_valorem"


def _choose_best_usitc_row(rows: Iterable[Dict[str, Any]], target_hts: str) -> Optional[Dict[str, Any]]:
    target_norm = _normalize_hts(target_hts)
    candidates = [row for row in rows if isinstance(row, dict)]
    if not candidates:
        return None

    exact = [row for row in candidates if _normalize_hts(row.get("htsno")) == target_norm]
    if exact:
        preferred_exact = [row for row in exact if str(row.get("general") or "").strip()]
        if preferred_exact:
            return preferred_exact[0]
        return exact[0]

    prefix = [row for row in candidates if _normalize_hts(row.get("htsno")).startswith(target_norm)]
    if prefix:
        with_general = [row for row in prefix if str(row.get("general") or "").strip()]
        if with_general:
            return with_general[0]
        return prefix[0]

    return candidates[0]


def fetch_usitc_row(
    client: httpx.Client,
    hts_code: str,
    *,
    max_retries: int = 3,
    backoff_seconds: float = 0.5,
) -> Optional[Dict[str, Any]]:
    params = {"keyword": hts_code}
    for attempt in range(max_retries):
        try:
            response = client.get(USITC_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return None
            return _choose_best_usitc_row(payload, target_hts=hts_code)
        except (httpx.HTTPError, ValueError):
            if attempt == max_retries - 1:
                return None
            time.sleep(backoff_seconds * (2 ** attempt))
    return None


def _load_rows(csv_path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV is missing headers.")

        missing = REQUIRED_COLUMNS.difference(set(reader.fieldnames))
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        return list(reader.fieldnames), list(reader)


def _write_rows(csv_path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _format_decimal(rate: Decimal) -> str:
    return f"{rate.quantize(Decimal('0.01'))}"


def update_tariff_csv_from_usitc(
    csv_path: str,
    *,
    timeout_seconds: float,
    delay_seconds: float,
    max_retries: int,
    dry_run: bool,
) -> Tuple[RunSummary, List[RowUpdateResult]]:
    resolved_csv = _resolve_path(csv_path)
    fieldnames, rows = _load_rows(resolved_csv)

    output_fieldnames = list(fieldnames)
    for column in AUDIT_COLUMNS:
        if column not in output_fieldnames:
            output_fieldnames.append(column)

    summary = RunSummary(total_rows=len(rows))
    row_results: List[RowUpdateResult] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for row in rows:
            product_name = (row.get("product_name") or "").strip()
            hts_code = (row.get("hts_code") or "").strip()
            current_rate = _coerce_decimal(row.get("tariff_rate"))

            if not hts_code:
                summary.missing_hts += 1
                row["usitc_parse_status"] = "missing_hts"
                row["usitc_updated_at"] = now_iso
                row_results.append(
                    RowUpdateResult(
                        product_name=product_name,
                        hts_code="",
                        old_rate=current_rate,
                        new_rate=current_rate,
                        changed=False,
                        parse_status="missing_hts",
                        rate_type="unknown",
                        general_text="",
                        special_text="",
                    )
                )
                continue

            summary.looked_up += 1
            usitc_row = fetch_usitc_row(client, hts_code, max_retries=max_retries)
            if usitc_row is None:
                summary.no_match += 1
                row["usitc_parse_status"] = "no_match"
                row["usitc_updated_at"] = now_iso
                row_results.append(
                    RowUpdateResult(
                        product_name=product_name,
                        hts_code=hts_code,
                        old_rate=current_rate,
                        new_rate=current_rate,
                        changed=False,
                        parse_status="no_match",
                        rate_type="unknown",
                        general_text="",
                        special_text="",
                    )
                )
                time.sleep(max(0.0, delay_seconds))
                continue

            summary.matched += 1
            general_text = str(usitc_row.get("general") or "").strip()
            special_text = str(usitc_row.get("special") or "").strip()
            parsed_rate, rate_type, parse_status = parse_general_rate(general_text)

            if parsed_rate is None:
                summary.parse_unresolved += 1
                next_rate = current_rate
            else:
                next_rate = parsed_rate

            changed = False
            if next_rate is not None:
                next_rate_text = _format_decimal(next_rate)
                if row.get("tariff_rate") != next_rate_text:
                    row["tariff_rate"] = next_rate_text
                    changed = True

            row["usitc_general"] = general_text
            row["usitc_special"] = special_text
            row["usitc_rate_type"] = rate_type
            row["usitc_parse_status"] = parse_status
            row["usitc_updated_at"] = now_iso

            if changed:
                summary.changed += 1
            else:
                summary.unchanged += 1

            row_results.append(
                RowUpdateResult(
                    product_name=product_name,
                    hts_code=hts_code,
                    old_rate=current_rate,
                    new_rate=next_rate,
                    changed=changed,
                    parse_status=parse_status,
                    rate_type=rate_type,
                    general_text=general_text,
                    special_text=special_text,
                )
            )

            time.sleep(max(0.0, delay_seconds))

    if not dry_run:
        _write_rows(resolved_csv, output_fieldnames, rows)

    return summary, row_results


def resolve_products_from_updated_tariffs(*, limit: int, stale_only: bool, force: bool) -> Dict[str, Any]:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.append(str(PROJECT_ROOT))

    # Some local setups store DEBUG=release, which is not parseable as bool.
    if (os.getenv("DEBUG") or "").strip().lower() == "release":
        os.environ["DEBUG"] = "False"

    from app.db.session import SessionLocal
    from app.services.product_service import ProductService

    db = SessionLocal()
    try:
        service = ProductService(db)
        return service.resolve_tariffs(limit=limit, stale_only=stale_only, force=force)
    finally:
        db.close()


def _print_summary(summary: RunSummary) -> None:
    print("=== USITC TARIFF CSV UPDATE ===")
    print(f"Rows in CSV: {summary.total_rows}")
    print(f"Rows looked up: {summary.looked_up}")
    print(f"USITC matches: {summary.matched}")
    print(f"Tariff changes written: {summary.changed}")
    print(f"Unchanged rows: {summary.unchanged}")
    print(f"Missing HTS rows: {summary.missing_hts}")
    print(f"No USITC match rows: {summary.no_match}")
    print(f"Needs manual review (non-ad-valorem/parse): {summary.parse_unresolved}")


def _print_changed_rows(results: List[RowUpdateResult], limit: int) -> None:
    changed = [result for result in results if result.changed]
    if not changed:
        print("No tariff_rate values changed.")
        return

    print(f"Changed rows (showing up to {limit}):")
    for result in changed[:limit]:
        old_text = "N/A" if result.old_rate is None else _format_decimal(result.old_rate)
        new_text = "N/A" if result.new_rate is None else _format_decimal(result.new_rate)
        print(
            f"- {result.product_name} [{result.hts_code}] {old_text}% -> {new_text}% "
            f"({result.parse_status})"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh tariff_rates.csv from USITC HTS search data."
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV_PATH,
        help=f"Path to tariff CSV (default: {DEFAULT_CSV_PATH}).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=20.0,
        help="HTTP timeout per USITC request (default: 20).",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.2,
        help="Delay between USITC requests (default: 0.2).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retry attempts per HTS lookup (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run lookups and print summary without writing CSV.",
    )
    parser.add_argument(
        "--show-changes",
        type=int,
        default=20,
        help="How many changed rows to print (default: 20).",
    )
    parser.add_argument(
        "--resolve-products",
        action="store_true",
        help="After CSV update, run ProductService.resolve_tariffs to refresh product records.",
    )
    parser.add_argument(
        "--resolve-limit",
        type=int,
        default=500,
        help="Batch limit passed to resolve_tariffs (default: 500).",
    )
    parser.add_argument(
        "--resolve-stale-only",
        action="store_true",
        help="Only resolve products with stale/missing verification.",
    )
    parser.add_argument(
        "--resolve-force",
        action="store_true",
        help="Force tariff resolution even when manual_tariff_override is true.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    summary, results = update_tariff_csv_from_usitc(
        args.csv,
        timeout_seconds=max(1.0, args.timeout_seconds),
        delay_seconds=max(0.0, args.delay_seconds),
        max_retries=max(1, args.max_retries),
        dry_run=bool(args.dry_run),
    )

    _print_summary(summary)
    _print_changed_rows(results, limit=max(0, args.show_changes))

    if args.dry_run:
        print("Dry run mode enabled. CSV was not modified.")

    if args.resolve_products:
        print("=== PRODUCT TARIFF RESOLUTION ===")
        try:
            payload = resolve_products_from_updated_tariffs(
                limit=max(1, min(args.resolve_limit, 500)),
                stale_only=bool(args.resolve_stale_only),
                force=bool(args.resolve_force),
            )
        except Exception as exc:
            print(f"Resolution step failed: {exc}")
        else:
            print(payload)


if __name__ == "__main__":
    main()
