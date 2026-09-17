"""
TRACE-ER Explorer — shared ingestion utilities.

Every source connector in src/ingest/ should use these instead of
re-implementing download, checksum, or column-detection logic.

"""

from __future__ import annotations

import csv
import hashlib
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import requests

logger = logging.getLogger("trace_er.ingest")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@dataclass
class DownloadResult:
    url: str
    dest_path: Path
    bytes_downloaded: int
    sha256: str
    accessed_at: str  # ISO 8601 UTC timestamp, for the provenance manifest


def sha256_checksum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute a SHA-256 checksum for a file already on disk."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    dest_path: Path,
    timeout: int = 120,
    chunk_size: int = 1024 * 1024,
) -> DownloadResult:
    """
    Stream a file to disk and compute its checksum as it comes down,
    rather than trusting the source's Content-Length header alone.

    Raises requests.HTTPError on a non-2xx response instead of writing
    a partial or error-page file to disk silently.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    bytes_downloaded = 0

    accessed_at = datetime.now(timezone.utc).isoformat()

    logger.info("Downloading %s -> %s", url, dest_path)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                digest.update(chunk)
                bytes_downloaded += len(chunk)

    checksum = digest.hexdigest()
    logger.info(
        "Downloaded %s bytes, sha256=%s, accessed_at=%s",
        bytes_downloaded,
        checksum,
        accessed_at,
    )
    return DownloadResult(
        url=url,
        dest_path=dest_path,
        bytes_downloaded=bytes_downloaded,
        sha256=checksum,
        accessed_at=accessed_at,
    )


def unzip_file(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract a zip archive and return the paths of every extracted file."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            # Refuse anything that would escape extract_dir (zip-slip guard).
            target = (extract_dir / member).resolve()
            if not str(target).startswith(str(extract_dir.resolve())):
                raise ValueError(f"Unsafe path in archive, refusing to extract: {member}")
        zf.extractall(extract_dir)
        extracted = [extract_dir / name for name in zf.namelist() if not name.endswith("/")]
    logger.info("Extracted %s files from %s", len(extracted), zip_path)
    return extracted


def discover_csv_files(directory: Path) -> list[Path]:
    """Find CSV files without assuming a specific filename in advance."""
    found = sorted(directory.rglob("*.csv")) + sorted(directory.rglob("*.CSV"))
    # de-duplicate while preserving order, in case of case-insensitive filesystems
    seen = set()
    unique = []
    for p in found:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def detect_column(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    """
    Match a real column name against a list of likely candidate names,
    case- and whitespace-insensitively. Returns the ACTUAL column name
    from `columns` (preserving its original casing) so callers can use
    it directly, or None if nothing matched.
    """
    normalized = {c.strip().lower(): c for c in columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return normalized[key]
    return None


def require_column(columns: Iterable[str], candidates: Iterable[str], label: str) -> str:
    """Like detect_column, but raises a clear, actionable error if nothing matches."""
    match = detect_column(columns, candidates)
    if match is None:
        raise ValueError(
            f"Could not find a column for '{label}'. Tried candidates {list(candidates)}. "
            f"Actual columns in file: {list(columns)}. "
            f"Update the candidate list in this connector once you've confirmed the real "
            f"column name — do not guess."
        )
    return match


def resolve_columns(
    columns: Iterable[str],
    candidates: dict[str, list[str]],
    required_fields: Iterable[str],
) -> dict:
    """
    Generic column-resolution logic shared by every connector. Required
    fields raise immediately (via require_column) if no candidate
    matches; optional fields log a warning and resolve to None.

    """
    required_fields = set(required_fields)
    columns = list(columns)
    resolved: dict[str, Optional[str]] = {}
    for field_name, field_candidates in candidates.items():
        if field_name in required_fields:
            resolved[field_name] = require_column(columns, field_candidates, field_name)
        else:
            match = detect_column(columns, field_candidates)
            if match is None:
                logger.warning(
                    "Optional column '%s' not found (tried %s). Continuing without it.",
                    field_name,
                    field_candidates,
                )
            resolved[field_name] = match
    return resolved


def filter_and_standardize_by_state(
    df,
    resolved: dict,
    target_states: list[str],
    state_field: str = "state",
    lat_field: str = "latitude",
    lon_field: str = "longitude",
):
    """
    Generic state-filtering and column-renaming logic shared by every
    connector whose standardized schema has a 'state' field and
    (optionally) latitude/longitude fields. 

    """
    state_col = resolved[state_field]
    state_norm = df[state_col].astype(str).str.strip().str.upper()
    filtered = df[state_norm.isin(target_states)].copy()
    accepted_rows = len(filtered)

    lat_col = resolved.get(lat_field)
    lon_col = resolved.get(lon_field)
    if lat_col and lon_col:
        missing_coords = int((filtered[lat_col].isna() | filtered[lon_col].isna()).sum())
    else:
        # Can't even evaluate coordinate presence — treat every row as
        # unknown/missing, never as present, per the missing-data rule
        # in the scope document.
        missing_coords = accepted_rows

    rename_map = {source_col: field_name for field_name, source_col in resolved.items() if source_col}
    standardized = filtered.rename(columns=rename_map)

    state_breakdown = state_norm[state_norm.isin(target_states)].value_counts().to_dict()

    stats = {
        "accepted_rows": accepted_rows,
        "missing_coords": missing_coords,
        "state_breakdown": state_breakdown,
    }
    return standardized, stats


def discover_columns_by_keyword(
    columns: Iterable[str], keyword_buckets: dict[str, list[str]]
) -> dict[str, list[str]]:
    """
    For each bucket, find every column whose name contains any of the
    bucket's keywords (case-insensitive substring match).

    """
    result: dict[str, list[str]] = {}
    columns = list(columns)
    for bucket, keywords in keyword_buckets.items():
        matches = [col for col in columns if any(kw.upper() in col.upper() for kw in keywords)]
        result[bucket] = matches
    return result


def haversine_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    Great-circle distance between two lat/lon points, in kilometers.
    Used here to cross-check whether two sources' coordinates for the
    same entity roughly agree
    """
    from math import radians, sin, cos, sqrt, atan2

    R = 6371.0088  # mean Earth radius, km
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def verify_filtered_count(filtered_count: int, unfiltered_count: int, filter_description: str) -> None:
    """
    Defends against a real, documented failure mode of EPA's Envirofacts
    efservice API (confirmed via third-party tooling that measured it
    directly).
    """
    if filtered_count <= 0:
        raise ValueError(
            f"Filtered count for {filter_description} is {filtered_count}. Expected a "
            f"positive number of records. Either the filter column name is wrong, or "
            f"there genuinely are zero matching records — check manually before proceeding, "
            f"do not assume either explanation."
        )
    if filtered_count >= unfiltered_count:
        raise ValueError(
            f"Filtered count ({filtered_count}) for {filter_description} is not smaller "
            f"than the unfiltered count ({unfiltered_count}). This is the exact signature "
            f"of EPA's efservice API silently ignoring an unrecognized filter column and "
            f"returning the full unfiltered table instead of erroring. Do not trust this "
            f"data — verify the filter column name against the live API before retrying."
        )


def get_efservice_count(url: str, timeout: int = 60) -> int:
    """
    Fetch a count from an EPA efservice .../COUNT/JSON endpoint.
    """
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    # Shape 1: a list containing one dict with TOTALQUERYRESULTS
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        for key in ("TOTALQUERYRESULTS", "totalqueryresults", "TotalQueryResults"):
            if key in data[0]:
                return int(data[0][key])
    # Shape 2: a bare dict with the same key
    if isinstance(data, dict):
        for key in ("TOTALQUERYRESULTS", "totalqueryresults", "TotalQueryResults"):
            if key in data:
                return int(data[key])
    # Shape 3: a bare number or numeric string
    if isinstance(data, (int, float)):
        return int(data)

    raise ValueError(
        f"Could not parse a count from {url}. Response was: {data!r}. "
        f"The efservice COUNT/JSON response shape may differ from what was expected — "
        f"inspect it manually and update get_efservice_count() rather than guessing."
    )


def check_interim_freshness(df_columns: list[str], expected_fields: list[str], connector_name: str) -> list[str]:
    """
    Check whether an interim file has every field its connector is
    currently supposed to produce.
    """
    missing = [f for f in expected_fields if f not in df_columns]
    if missing:
        logger.warning(
            "%s interim file appears STALE — missing %d field(s) the connector "
            "currently produces: %s. This usually means the file predates a "
            "later expansion of the connector's column list. Re-run the "
            "connector to regenerate it before trusting downstream results.",
            connector_name, len(missing), missing,
        )
    return missing


SOURCE_VOLUME_LOG_FIELDS = [
    "source",
    "run_timestamp_utc",
    "downloaded_rows",
    "accepted_rows",
    "rejected_or_quarantined",
    "duplicate_rows",
    "linked_rows",
    "final_unique_entities",
    "notes",
]


def append_source_volume_log(log_path: Path, row: dict) -> None:
    """
    Append one run's counts to the source-volume log. Creates the file with a header if it
    doesn't exist yet.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {**{k: row.get(k, "") for k in SOURCE_VOLUME_LOG_FIELDS}}
    file_exists = log_path.exists()
    with open(log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SOURCE_VOLUME_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    logger.info("Logged source-volume entry for %s to %s", row.get("source"), log_path)
