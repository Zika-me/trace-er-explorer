"""
TRACE-ER Explorer — Texas Railroad Commission (RRC) R-3 Gas Processing
Plants connector.


RRC's main bulk data catalog (drilling permits, well data, production
data, most everything else) routes through mft.rrc.texas.gov, a
Managed File Transfer domain. 

IMPORTANT — the download URLs are NOT predictable from month/year
alone. Each file lives at a URL with an unpredictable hash segment
(e.g. /media/hffk1bkg/r3dataload-july-2026.zip), assigned by RRC's
CMS. This connector discovers the current set of available links by
parsing the listing page itself
(https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/r-3-gas-processing-plants-report)
each run, rather than attempting to construct URLs — those hashes
cannot be guessed or derived.

IMPORTANT — scope. R-3 covers gas PROCESSING PLANTS specifically (per
RRC's own count, roughly 2,000 filings/month nationally, a small
fraction of Texas's oil and gas facility universe) — not wells,
leases, or the broader production data this project's scope document
originally had in mind. This is a deliberate, documented scope
narrowing: the alternative (the 25GB production dump) requires a
human to email RRC directly, which this project's owner is not able
to do. R-3 is real, usable, self-service Texas RRC data — narrower
than originally scoped, but genuine.

IMPORTANT — the real field name is "Longtitude", not "Longitude".
Confirmed directly from RRC's own JSON schema documentation and its
sample record. This is preserved exactly, not corrected, the same
principle applied to FRS's plural NAICS_CODES/SIC_CODES fields and
TRI's "frs id" (space, not underscore) earlier this session.

IMPORTANT — CONFIRMED nested JSON structure: sections like "Facility
Information", "Section I: Intake Volumes", "Section III: Disposition
of Residual Gas" are each a LIST containing exactly one dict in the
real sample record, even for single-valued sections. This connector
indexes [0] defensively (checking the list is non-empty first) rather
than assuming a bare dict — confirmed against the real sample record
in RRC's own documentation, not guessed.

This is a curated subset of the full R-3 schema (Sections IV through
XI, covering detailed sulfur recovery, liquid hydrocarbon accounting,
and gas injection detail, are NOT extracted) — facility identity,
location, compliance status, and two summary volume figures (net gas
to plant, vented gas) that are directly relevant to environmental
risk screening. Mirrors the same curation decision made for ECHO's
~90 undeferred per-program fields and TRI's ~90 per-transfer-method
release columns.

Usage:
    python src/ingest/fetch_rrc_r3_gas_plants.py
"""

from __future__ import annotations

import re
import sys
import zipfile
import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import append_source_volume_log, logger  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "rrc_r3"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
SOURCE_VOLUME_LOG = REPO_ROOT / "validation" / "source_volume_log.csv"

LISTING_PAGE_URL = (
    "https://www.rrc.texas.gov/resource-center/research/"
    "data-sets-available-for-download/r-3-gas-processing-plants-report"
)

# Matches an href like:
#   /media/hffk1bkg/r3dataload-july-2026.zip          (relative — what RRC currently serves)
#   https://www.rrc.texas.gov/media/.../r3dataload-... (absolute — kept for safety)
# Captures: (path_or_full_url, month, year)
# NOTE: RRC's CMS renders hrefs as site-relative paths, not absolute URLs.
# The base domain is prepended in discover_available_months() below.

_RRC_BASE = "https://www.rrc.texas.gov"

R3_LINK_PATTERN = re.compile(
    r'href\s*=\s*["\']((https://www\.rrc\.texas\.gov)?/media/[a-z0-9]+/r3dataload-([a-z]+)-(\d{4})\.zip)["\']',
    re.IGNORECASE,
)

REQUIRED_FIELDS = {"facility_key", "reporting_month", "reporting_year"}


def discover_available_months(listing_page_html: str) -> dict:
    """
    Pure function: parse the listing page's HTML for the current set
    of month/year -> download URL links. Returns {(month, year): url}
    with month lowercased (e.g. "july") and year as a 4-digit string.

    Does not attempt to construct URLs from month/year — the hash
    slug in each path is CMS-assigned and not derivable.

    Handles both relative (/media/...) and absolute (https://...) hrefs
    since RRC's CMS has served both at different times.
    """
    matches = R3_LINK_PATTERN.findall(listing_page_html)
    result = {}
    for full_match, maybe_domain, month, year in matches:
        url = full_match if maybe_domain else _RRC_BASE + full_match
        result[(month.lower(), year)] = url
    return result


def fetch_month_json(url: str) -> list[dict]:
    """
    Download one month's ZIP file and parse the JSON file(s) inside
    it. Each ZIP may contain more than one JSON file (per RRC's own
    documentation: "Files are delivered as ZIP archives containing
    one or more JSON files") — all are read and combined.
    """
    response = requests.get(url, timeout=180)
    response.raise_for_status()

    all_reports = []
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        json_names = [n for n in zf.namelist() if n.lower().endswith(".json")]
        for name in json_names:
            with zf.open(name) as f:
                data = json.load(f)
                reports = data.get("R3Report", [])
                all_reports.extend(reports)
    return all_reports


def first_or_none(items: list, key: str):
    """Pure function: safely get a field from the first item of a possibly-empty list of dicts."""
    if items and isinstance(items[0], dict):
        return items[0].get(key)
    return None


def flatten_r3_report(report: dict) -> dict:
    """
    Pure function: flatten one R3Report entry into a single standardized
    flat dict. Extracts a curated subset of the full schema — facility
    identity, location, compliance status, and two summary volume
    figures — not every accounting-detail section.
    """
    facility_info = report.get("Facility Information", [])
    section_i = report.get("Section I: Intake Volumes", [])
    section_iii = report.get("Section III: Disposition of Residual Gas", [])

    return {
        "facility_key": report.get("Facility Key"),
        "serial_number": report.get("Serial Number"),
        "facility_name": report.get("Facility Name"),
        "plant_type": report.get("Plant Type"),
        "r3_plant_id": report.get("R3 Plant ID"),
        "is_cid_critical": report.get("CIDCritical"),
        "reporting_month": report.get("ReportingPeriodMonth"),
        "reporting_year": report.get("ReportingPeriodYear"),
        "latitude": report.get("Latitude"),
        "longitude": report.get("Longtitude"),  # confirmed real spelling, not a typo
        "plant_avg_capacity": report.get("PlantAverageCapacity"),
        "district": report.get("District"),
        "county": report.get("County"),
        "rrc_facility_id": first_or_none(facility_info, "RRC ID"),
        "facility_status": first_or_none(facility_info, "Facility Status"),
        "certificate_of_compliance": first_or_none(facility_info, "CoC"),
        "net_gas_to_plant_mcf": first_or_none(section_i, "12. Net Gas to Plant for Processing"),
        "vented_gas_mcf": first_or_none(section_iii, "13. Vented"),
    }


def parse_r3_reports(reports: list[dict]) -> pd.DataFrame:
    """Pure function: flatten a list of raw R3Report dicts into a standardized DataFrame."""
    flattened = [flatten_r3_report(r) for r in reports]
    df = pd.DataFrame(flattened, dtype=str)
    missing_required = [f for f in REQUIRED_FIELDS if f not in df.columns]
    if missing_required:
        raise ValueError(f"Required fields missing from parsed R3 data: {missing_required}")
    return df


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching listing page: %s", LISTING_PAGE_URL)
    listing_response = requests.get(LISTING_PAGE_URL, timeout=60)
    listing_response.raise_for_status()

    available_months = discover_available_months(listing_response.text)
    logger.info("Discovered %d available month(s): %s", len(available_months), sorted(available_months.keys()))

    if not available_months:
        raise RuntimeError(
            "No R3dataload download links found on the listing page. RRC may have changed "
            "the page structure — inspect the page manually before assuming the data is gone."
        )

    all_dfs = []
    failed_months = []
    for (month, year), url in sorted(available_months.items(), key=lambda kv: kv[0][1] + kv[0][0]):
        logger.info("Fetching %s %s: %s", month, year, url)
        try:
            reports = fetch_month_json(url)
            raw_path = RAW_DIR / f"r3_{year}_{month}.json"
            raw_path.write_text(json.dumps(reports))
            df = parse_r3_reports(reports)
            all_dfs.append(df)
            logger.info("%s %s: %d facility reports", month, year, len(df))
        except Exception as exc:  # noqa: BLE001 — one bad month must not abort the run
            logger.error("FAILED for %s %s: %s. Skipping, continuing.", month, year, exc)
            failed_months.append((month, year, str(exc)))
        time.sleep(1)  # polite pacing

    if not all_dfs:
        raise RuntimeError(f"No months succeeded. Failed: {failed_months}")

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info("Combined %d months: %d total facility reports.", len(all_dfs), len(combined))
    if failed_months:
        logger.warning("%d month(s) failed: %s", len(failed_months), failed_months)

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTERIM_DIR / "rrc_r3_gas_plants.csv"
    combined.to_csv(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(combined), out_path)

    append_source_volume_log(
        SOURCE_VOLUME_LOG,
        {
            "source": "tx_rrc_r3_gas_plants",
            "run_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "downloaded_rows": len(combined),
            "accepted_rows": len(combined),
            "rejected_or_quarantined": "",
            "duplicate_rows": "",
            "linked_rows": "",
            "final_unique_entities": "",
            "notes": f"months_covered={sorted(available_months.keys())}; failed_months={failed_months}; "
                     f"Sections IV-XI (detailed liquid/sulfur/injection accounting) NOT extracted, see module docstring",
        },
    )


if __name__ == "__main__":
    main()