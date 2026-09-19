#!/usr/bin/env python3
"""
src/ingest/join_rrc_r3_to_master.py

Two-stage pipeline for integrating Texas RRC R-3 Gas Processing Plant data
into the master facility index.

Stage 1 — Aggregate
    Collapses monthly facility-month rows into one row per gas plant (keyed
    on serial_number), computing cumulative throughput, capacity statistics,
    and year coverage across the 13-month reporting window.

    Coordinate policy: use the first non-placeholder (lat, lon) pair seen
    across months for a plant. If every month carries the RRC sentinel value
    (30.0, −100.0), the plant is flagged r3_coords_valid=False and excluded
    from the spatial join.

Stage 2 — Spatial join
    For plants with valid coordinates, performs a nearest-neighbour spatial
    join against Texas rows in the master facility index within
    SPATIAL_THRESHOLD_M metres (UTM zone 14N, EPSG:32614).

    If two R3 plants are both nearest to the same master row, the closer one
    wins; the other is recorded as unmatched. Plants beyond the threshold and
    placeholder-coord plants are documented in the volume log but not forced
    into the master index.

    NOTE: ~42 % of plants carry placeholder coordinates and cannot be
    spatially matched. A future enhancement could attempt county + normalised
    name matching to recover some of these; for now they are left as
    RRC-only records in rrc_r3_plant_features.csv.

Inputs:
    data/interim/rrc_r3_gas_plants.csv
    data/processed/master_facility_index_with_tri_features.csv

Outputs:
    data/processed/rrc_r3_plant_features.csv
    data/processed/master_facility_index_with_rrc_features.csv
    validation/source_volume_log.csv   (appended)
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

R3_INTERIM  = DATA_DIR / "interim" / "rrc_r3_gas_plants.csv"
MASTER_IN   = DATA_DIR / "processed" / "master_facility_index_with_tri_features.csv"
R3_FEAT_OUT = DATA_DIR / "processed" / "rrc_r3_plant_features.csv"
MASTER_OUT  = DATA_DIR / "processed" / "master_facility_index_with_rrc_features.csv"
VOL_LOG     = BASE_DIR / "validation" / "source_volume_log.csv"

# Conservative threshold: gas processing plants are large fixed industrial
# sites; 500 m accommodates different reference-point conventions between
# RRC and EPA without introducing false matches in dense urban areas.
SPATIAL_THRESHOLD_M = 500

PLACEHOLDER_LAT = 30.0      # RRC sentinel value for unknown latitude
PLACEHOLDER_LON = -100.0    # RRC sentinel value for unknown longitude

WGS84  = "EPSG:4326"
UTM14N = "EPSG:32614"   # UTM zone 14N — covers Texas; metre-based distances

NUMERIC_COLS = ["net_gas_to_plant_mcf", "vented_gas_mcf", "plant_avg_capacity"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# Stage 1: Aggregate monthly rows - one row per plant

def aggregate_r3_to_plants(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse monthly R3 rows to one row per gas plant (serial_number).
    All r3_* prefixed columns are safe to left-join onto the master index.
    """
    for col in NUMERIC_COLS:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["latitude"]  = pd.to_numeric(raw["latitude"],  errors="coerce")
    raw["longitude"] = pd.to_numeric(raw["longitude"], errors="coerce")

    raw["_placeholder"] = (
        (raw["latitude"]  == PLACEHOLDER_LAT) &
        (raw["longitude"] == PLACEHOLDER_LON)
    )

    records: list[dict] = []
    for serial, grp in raw.groupby("serial_number", sort=True):

        def first_valid(col: str):
            s = grp[col].dropna()
            return s.iloc[0] if len(s) else None

        # Prefer the first non-placeholder coordinate pair across months
        real = grp[~grp["_placeholder"]]
        if len(real):
            lat          = real["latitude"].iloc[0]
            lon          = real["longitude"].iloc[0]
            coords_valid = True
        else:
            lat          = PLACEHOLDER_LAT
            lon          = PLACEHOLDER_LON
            coords_valid = False

        years = sorted({y for y in grp["reporting_year"].dropna().tolist()})

        records.append({
            "r3_serial_number":        serial,
            "r3_facility_name":        first_valid("facility_name"),
            "r3_plant_type":           first_valid("plant_type"),
            "r3_district":             first_valid("district"),
            "r3_county":               first_valid("county"),
            "r3_is_cid_critical":      first_valid("is_cid_critical"),
            "r3_latitude":             lat,
            "r3_longitude":            lon,
            "r3_coords_valid":         coords_valid,
            "r3_months_reported":      len(grp),
            "r3_years_covered":        ",".join(years),
            "r3_net_gas_total_mcf":    grp["net_gas_to_plant_mcf"].sum(min_count=1),
            "r3_vented_gas_total_mcf": grp["vented_gas_mcf"].sum(min_count=1),
            "r3_avg_capacity_mean":    (
                round(float(grp["plant_avg_capacity"].mean()), 4)
                if grp["plant_avg_capacity"].notna().any() else None
            ),
        })

    return pd.DataFrame(records)


# Stage 2: Spatial join - master facility index (Texas only)

def spatial_join_to_master(
    r3_plants: pd.DataFrame,
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Nearest-neighbour spatial join:
      - Left:  R3 plants with valid coordinates
      - Right: Texas rows in the master facility index

    Distance is computed in metres after projecting both layers to UTM 14N.
    Matches beyond SPATIAL_THRESHOLD_M are discarded (plant treated as
    unmatched rather than forcing a questionable link).

    Returns (extended_master_df, stats_dict).
    """
    r3_valid   = r3_plants[r3_plants["r3_coords_valid"]].copy().reset_index(drop=True)
    r3_invalid = r3_plants[~r3_plants["r3_coords_valid"]].copy()
    log.info(
        "Plants with valid coordinates: %d  |  placeholder (excluded from join): %d",
        len(r3_valid), len(r3_invalid),
    )

    # Restrict master to Texas rows that have parseable coordinates
    master = master.copy()
    master["_lat"] = pd.to_numeric(master["latitude"],  errors="coerce")
    master["_lon"] = pd.to_numeric(master["longitude"], errors="coerce")
    mi_tx = master[
        (master["state"] == "TX") &
        master["_lat"].notna() &
        master["_lon"].notna()
    ].copy().reset_index(drop=True)
    log.info("Master index — TX rows with coordinates: %d", len(mi_tx))

    # Build GeoDataFrames in WGS84, then reproject to UTM 14N
    gdf_r3 = gpd.GeoDataFrame(
        r3_valid[["r3_serial_number"]].copy(),
        geometry=gpd.points_from_xy(r3_valid["r3_longitude"], r3_valid["r3_latitude"]),
        crs=WGS84,
    ).to_crs(UTM14N)

    gdf_mi = gpd.GeoDataFrame(
        mi_tx[["master_id"]].copy(),
        geometry=gpd.points_from_xy(mi_tx["_lon"], mi_tx["_lat"]),
        crs=WGS84,
    ).to_crs(UTM14N)

    # Nearest join — one master row per R3 plant
    joined = gpd.sjoin_nearest(
        gdf_r3,
        gdf_mi,
        how="left",
        distance_col="r3_match_distance_m",
    ).reset_index(drop=True)

    joined = joined.drop(columns=["geometry", "index_right"], errors="ignore")

    # Discard matches beyond the distance threshold
    joined.loc[
        joined["r3_match_distance_m"] > SPATIAL_THRESHOLD_M, "master_id"
    ] = None

    matched   = int(joined["master_id"].notna().sum())
    unmatched = int(joined["master_id"].isna().sum())
    log.info(
        "Spatial match (≤%dm): %d matched  |  %d beyond threshold",
        SPATIAL_THRESHOLD_M, matched, unmatched,
    )

    # Resolve master_id collisions: if two R3 plants both matched the same
    # master row, keep the closer plant and release the other as unmatched.
    serial_to_master = (
        joined[joined["master_id"].notna()]
        [["r3_serial_number", "master_id", "r3_match_distance_m"]]
        .sort_values("r3_match_distance_m")
        .drop_duplicates(subset="master_id", keep="first")   # one plant per master row
        .reset_index(drop=True)
    )
    after_dedup = len(serial_to_master)
    if after_dedup < matched:
        log.info(
            "Collision resolution: %d master rows claimed by >1 plant; "
            "%d plants lost their match (now unmatched).",
            matched - after_dedup, matched - after_dedup,
        )

    # Build the R3-feature slice to attach to master:
    # exclude coordinate columns (master has its own) and the validity flag
    r3_attach_cols = [
        c for c in r3_plants.columns
        if c not in {"r3_latitude", "r3_longitude", "r3_coords_valid"}
    ]
    r3_for_master = (
        serial_to_master
        .merge(r3_plants[r3_attach_cols], on="r3_serial_number", how="left")
        .drop(columns=["r3_serial_number"])
    )

    # Left-join R3 features onto master
    master_out = (
        master
        .drop(columns=["_lat", "_lon"])
        .merge(r3_for_master, on="master_id", how="left")
    )
    master_out["has_rrc_r3_data"] = master_out["r3_match_distance_m"].notna()

    stats = {
        "r3_plants_total":              len(r3_plants),
        "r3_plants_valid_coords":       len(r3_valid),
        "r3_plants_placeholder_coords": len(r3_invalid),
        "r3_plants_matched_to_master":  after_dedup,
        "r3_plants_unmatched":          len(r3_plants) - after_dedup,
        "master_rows_with_rrc_r3_data": int(master_out["has_rrc_r3_data"].sum()),
    }
    return master_out, stats


# ---------------------------------------------------------------------------
# Volume log
# ---------------------------------------------------------------------------

def append_volume_log(stats: dict) -> None:
    VOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not VOL_LOG.exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "tx_rrc_r3_plant_features",
        "row_count": stats["r3_plants_total"],
        "notes": (
            f"valid_coords={stats['r3_plants_valid_coords']}; "
            f"placeholder_coords={stats['r3_plants_placeholder_coords']}; "
            f"matched_to_master={stats['r3_plants_matched_to_master']}; "
            f"master_rows_with_rrc_r3={stats['master_rows_with_rrc_r3_data']}"
        ),
    }
    with open(VOL_LOG, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    log.info("Logged volume entry → %s", VOL_LOG)



def main() -> None:
    # --- Stage 1: aggregate monthly rows - plant features ---
    log.info("Loading RRC R3 interim data: %s", R3_INTERIM)
    raw = pd.read_csv(R3_INTERIM, dtype=str)
    log.info(
        "  %d monthly rows  |  %d unique serial numbers",
        len(raw), raw["serial_number"].nunique(),
    )

    log.info("Aggregating to plant level...")
    r3_plants = aggregate_r3_to_plants(raw)

    valid_ct   = int(r3_plants["r3_coords_valid"].sum())
    invalid_ct = int((~r3_plants["r3_coords_valid"]).sum())
    log.info(
        "  %d plants total  |  %d valid coords  |  %d placeholder coords",
        len(r3_plants), valid_ct, invalid_ct,
    )

    DATA_DIR.joinpath("processed").mkdir(parents=True, exist_ok=True)
    r3_plants.to_csv(R3_FEAT_OUT, index=False)
    log.info("Wrote %d plant feature rows → %s", len(r3_plants), R3_FEAT_OUT)

    # --- Stage 2: spatial join to master index ---
    log.info("Loading master facility index: %s", MASTER_IN)
    master = pd.read_csv(MASTER_IN, dtype=str)
    log.info("  %d rows  |  %d columns", len(master), len(master.columns))

    log.info(
        "Running spatial join (threshold=%dm, projection=%s)...",
        SPATIAL_THRESHOLD_M, UTM14N,
    )
    master_out, stats = spatial_join_to_master(r3_plants, master)

    master_out.to_csv(MASTER_OUT, index=False)
    log.info(
        "Wrote extended master index: %d rows  |  %d columns → %s",
        len(master_out), len(master_out.columns), MASTER_OUT,
    )

    append_volume_log(stats)

    log.info("Done. Summary:")
    for k, v in stats.items():
        log.info("  %-40s %s", k + ":", v)


if __name__ == "__main__":
    main()