#!/usr/bin/env python3
"""
src/features/build_risk_scores.py

Computes composite environmental risk scores for every facility in the master
index and produces a lean Power BI-ready summary table.

Scoring architecture (all components 0-100):

  1. compliance_risk_score  — ECHO-based: violations, penalties, SNC, HPV flags
  2. tri_release_score      — TRI-based: release totals, carcinogen/PBT/PFAS hazards
  3. pipeline_context_score — PHMSA county-level: incident count, severity, casualties
  4. state_resource_score   — state-specific, within-state normalised:
       TX → TCEQ LPST contamination burden
       PA → PA DEP unconventional wells + recent permits
       NM → NM OCD well density + recent spud activity
       ME → 0 (no state-specific data ingested)

  composite_risk_score = weighted average of 1, 2, 3
    Weights: compliance 35%, TRI 40%, pipeline 25%
    For facilities without TRI data, weights are renormalised to 58%/42%
    (compliance/pipeline) so that TRI absence does not artificially cap scores.

  risk_tier: HIGH (≥ 60) | MEDIUM (20-59) | LOW (< 20)

State resource score is intentionally excluded from the composite to preserve
cross-state comparability. It is reported as a separate column.

Inputs:
    data/processed/master_facility_index_with_nmocd_features.csv

Outputs:
    data/processed/master_risk_scores.csv          full 104 cols + 6 score cols
    data/processed/facility_risk_summary.csv       lean ~35-col Power BI table
    validation/source_volume_log.csv               appended
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

MASTER_IN   = DATA_DIR / "processed" / "master_facility_index_with_nmocd_features.csv"
SCORED_OUT  = DATA_DIR / "processed" / "master_risk_scores.csv"
SUMMARY_OUT = DATA_DIR / "processed" / "facility_risk_summary.csv"
VOL_LOG     = BASE_DIR / "validation" / "source_volume_log.csv"

# Composite weights (must sum to 1.0)
W_COMPLIANCE = 0.35
W_TRI        = 0.40
W_PIPELINE   = 0.25

# Risk tier thresholds (absolute, not percentile — intentional)
TIER_HIGH   = 60.0
TIER_MEDIUM = 20.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)



def to_num(series: pd.Series) -> pd.Series:
    """Parse string values to float, NaN → 0."""
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def yn_flag(series: pd.Series) -> pd.Series:
    """'Y'/'N' string → 1.0/0.0. NaN → 0.0."""
    return (series.fillna("").astype(str).str.strip().str.upper() == "Y").astype(float)


def bool_flag(series: pd.Series) -> pd.Series:
    """'True'/'False' string → 1.0/0.0. NaN → 0.0."""
    return (series.fillna("").astype(str).str.strip().str.lower() == "true").astype(float)


def log_minmax(series: pd.Series) -> pd.Series:
    """
    log1p-transform then min-max scale to [0, 1] across the full dataset.
    NaN treated as 0 before transform. Constant series → all zeros.
    """
    s = to_num(series)
    log_s = np.log1p(s)
    mn, mx = log_s.min(), log_s.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (log_s - mn) / (mx - mn)


def log_minmax_within(series: pd.Series) -> pd.Series:
    """
    Same as log_minmax but normalises only within the provided slice.
    Used for state-specific features so that each state fills the full
    0-100 range independently.
    """
    s = to_num(series)
    log_s = np.log1p(s)
    mn, mx = log_s.min(), log_s.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (log_s - mn) / (mx - mn)



def compute_compliance_score(df: pd.DataFrame) -> pd.Series:
    """
    0-100 score derived from ECHO enforcement and compliance fields.

    Weights:
      fac_qtrs_with_nc        30 — quarters with non-compliance (frequency)
      fac_formal_action_count 25 — formal enforcement actions (severity signal)
      fac_total_penalties     20 — cumulative penalties (financial consequence)
      fac_snc_flag == Y       15 — significant non-compliance flag
      caa_hpv_flag == Y       10 — Clean Air Act high priority violator
    """
    score = (
        log_minmax(df["fac_qtrs_with_nc"])        * 30 +
        log_minmax(df["fac_formal_action_count"]) * 25 +
        log_minmax(df["fac_total_penalties"])     * 20 +
        yn_flag(df["fac_snc_flag"])               * 15 +
        yn_flag(df["caa_hpv_flag"])               * 10
    )
    # Facilities with no ECHO record at all have no evidence of violations —
    # zero their score rather than imputing from log-transformed zeros.
    has_echo = (
        df["fac_formal_action_count"].notna() |
        df["fac_qtrs_with_nc"].notna()
    )
    return score.where(has_echo, 0.0)



def compute_tri_score(df: pd.DataFrame) -> pd.Series:
    """
    0-100 score for facilities with TRI release data (3,919 of 527,983 rows).
    Facilities without TRI data receive 0 — absence of evidence, not evidence
    of absence, but we cannot infer releases from non-reporting.

    Weights:
      total_releases_sum      35 — total on+off-site releases (lbs)
      any_carcinogen          25 — releases IARC/EPA carcinogen
      any_pbt                 20 — releases persistent bioaccumulative toxic
      any_pfas                15 — releases PFAS compound
      distinct_chemical_count  5 — breadth of chemical hazard profile
    """
    score = (
        log_minmax(df["total_releases_sum"])      * 35 +
        bool_flag(df["any_carcinogen"])           * 25 +
        bool_flag(df["any_pbt"])                  * 20 +
        bool_flag(df["any_pfas"])                 * 15 +
        log_minmax(df["distinct_chemical_count"]) * 5
    )
    has_tri = bool_flag(df["has_tri_release_data"]).astype(bool)
    return score.where(has_tri, 0.0)



def compute_pipeline_score(df: pd.DataFrame) -> pd.Series:
    """
    0-100 county-level pipeline incident burden score.
    Facilities in counties with no PHMSA data receive 0.

    Weights:
      phmsa_incident_count    40 — total incidents (volume)
      phmsa_significant_count 35 — significant incidents (severity)
      phmsa_fatalities_total  15 — fatalities (consequence)
      phmsa_injuries_total    10 — injuries (consequence)
    """
    score = (
        log_minmax(df["phmsa_incident_count"])    * 40 +
        log_minmax(df["phmsa_significant_count"]) * 35 +
        log_minmax(df["phmsa_fatalities_total"])  * 15 +
        log_minmax(df["phmsa_injuries_total"])    * 10
    )
    has_phmsa = bool_flag(df["has_phmsa_incidents"]).astype(bool)
    return score.where(has_phmsa, 0.0)



def compute_state_resource_score(df: pd.DataFrame) -> pd.Series:
    """
    0-100 state-specific resource extraction and contamination burden.
    Normalised WITHIN each state so that TX, PA, and NM each span 0-100
    independently. ME receives 0 (no state-specific source ingested).

    TX weights:
      tceq_lpst_active_sites        50 — active petroleum contamination sites
      tceq_lpst_high_priority_sites 30 — high-priority contamination
      r3_net_gas_total_mcf          20 — gas plant throughput (RRC R-3)

    PA weights:
      padep_unconventional_wells    55 — unconventional (shale) well density
      padep_recent_permit_count     45 — recent drilling activity (2019-2025)

    NM weights:
      nmocd_total_wells             55 — total well density
      nmocd_recent_spud_count       45 — recent drilling activity (2019-2025)
    """
    score = pd.Series(0.0, index=df.index)

    # TX
    tx = df["state"].str.strip().str.upper() == "TX"
    if tx.sum() > 0:
        tx_score = (
            log_minmax_within(df.loc[tx, "tceq_lpst_active_sites"])        * 50 +
            log_minmax_within(df.loc[tx, "tceq_lpst_high_priority_sites"]) * 30 +
            log_minmax_within(df.loc[tx, "r3_net_gas_total_mcf"])          * 20
        )
        score.loc[tx] = tx_score.values

    # PA
    pa = df["state"].str.strip().str.upper() == "PA"
    if pa.sum() > 0:
        pa_score = (
            log_minmax_within(df.loc[pa, "padep_unconventional_wells"]) * 55 +
            log_minmax_within(df.loc[pa, "padep_recent_permit_count"])  * 45
        )
        score.loc[pa] = pa_score.values

    # NM
    nm = df["state"].str.strip().str.upper() == "NM"
    if nm.sum() > 0:
        nm_score = (
            log_minmax_within(df.loc[nm, "nmocd_total_wells"])        * 55 +
            log_minmax_within(df.loc[nm, "nmocd_recent_spud_count"]) * 45
        )
        score.loc[nm] = nm_score.values

    # ME stays 0
    return score


def compute_composite(
    compliance: pd.Series,
    tri: pd.Series,
    pipeline: pd.Series,
) -> pd.Series:
    """
    Weighted average of three cross-state components.
    For facilities without TRI data (tri == 0 because has_tri_release_data
    is False), weights are renormalised so compliance and pipeline together
    still fill the full 0-100 range.
    """
    has_tri = tri > 0

    w_other = W_COMPLIANCE + W_PIPELINE   # 0.60 — weight of non-TRI components

    composite = pd.Series(0.0, index=compliance.index)

    # Facilities WITH TRI evidence
    composite.loc[has_tri] = (
        W_COMPLIANCE * compliance.loc[has_tri] +
        W_TRI        * tri.loc[has_tri] +
        W_PIPELINE   * pipeline.loc[has_tri]
    )

    # Facilities WITHOUT TRI evidence — renormalise compliance + pipeline
    no_tri = ~has_tri
    composite.loc[no_tri] = (
        (W_COMPLIANCE / w_other) * compliance.loc[no_tri] +
        (W_PIPELINE   / w_other) * pipeline.loc[no_tri]
    )

    return composite.clip(0, 100)


def assign_tier(score: pd.Series) -> pd.Series:
    tiers = pd.Series("LOW", index=score.index)
    tiers[score >= TIER_MEDIUM] = "MEDIUM"
    tiers[score >= TIER_HIGH]   = "HIGH"
    return tiers



IDENTITY_COLS = [
    "master_id", "facility_name", "address", "city", "state", "county",
    "latitude", "longitude", "naics_codes_raw_frs", "sic_codes_raw_frs",
    "site_type", "source_count", "sources_present", "linkage_confidence",
]

ECHO_COLS = [
    "fac_compliance_status", "fac_inspection_count",
    "fac_formal_action_count", "fac_total_penalties", "fac_qtrs_with_nc",
    "fac_snc_flag", "caa_hpv_flag",
    "air_flag", "npdes_flag", "rcra_flag", "tri_flag",
]

TRI_COLS = [
    "has_tri_release_data", "total_releases_sum", "distinct_chemical_count",
    "any_carcinogen", "any_pbt", "any_pfas", "any_metal",
    "most_recent_reporting_year",
]

SOURCE_FLAG_COLS = [
    "has_rrc_r3_data", "has_phmsa_incidents", "has_tceq_lpst_data",
    "has_padep_well_data", "has_nmocd_well_data",
]

CONTEXT_COLS = [
    "phmsa_incident_count", "phmsa_significant_count",
    "tceq_lpst_active_sites", "tceq_lpst_high_priority_sites",
    "padep_unconventional_wells", "padep_recent_permit_count",
    "nmocd_total_wells", "nmocd_recent_spud_count",
]

SCORE_COLS = [
    "compliance_risk_score", "tri_release_score",
    "pipeline_context_score", "state_resource_score",
    "composite_risk_score", "risk_tier",
]


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    keep = [
        c for c in (
            IDENTITY_COLS + ECHO_COLS + TRI_COLS +
            SOURCE_FLAG_COLS + CONTEXT_COLS + SCORE_COLS
        )
        if c in df.columns
    ]
    return df[keep].copy()


def append_volume_log(n_rows: int, stats: dict) -> None:
    VOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not VOL_LOG.exists()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    "risk_scores",
        "row_count": n_rows,
        "notes": (
            f"high={stats['high_count']}; "
            f"medium={stats['medium_count']}; "
            f"low={stats['low_count']}; "
            f"composite_mean={stats['composite_mean']:.2f}; "
            f"composite_p90={stats['composite_p90']:.2f}"
        ),
    }
    with open(VOL_LOG, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)



def main() -> None:
    log.info("Loading master index: %s", MASTER_IN)
    df = pd.read_csv(MASTER_IN, dtype=str, low_memory=False)
    log.info("  %d rows  |  %d columns", len(df), len(df.columns))

    # ---- Compute components ----
    log.info("Computing compliance risk score...")
    df["compliance_risk_score"] = compute_compliance_score(df).round(2)

    log.info("Computing TRI release score...")
    df["tri_release_score"] = compute_tri_score(df).round(2)

    log.info("Computing pipeline context score...")
    df["pipeline_context_score"] = compute_pipeline_score(df).round(2)

    log.info("Computing state resource context score...")
    df["state_resource_score"] = compute_state_resource_score(df).round(2)

    # ---- Composite ----
    log.info("Computing composite risk score...")
    df["composite_risk_score"] = compute_composite(
        df["compliance_risk_score"],
        df["tri_release_score"],
        df["pipeline_context_score"],
    ).round(2)

    # ---- Tier ----
    df["risk_tier"] = assign_tier(df["composite_risk_score"])

    # ---- Statistics ----
    comp = df["composite_risk_score"]
    high_ct   = (df["risk_tier"] == "HIGH").sum()
    med_ct    = (df["risk_tier"] == "MEDIUM").sum()
    low_ct    = (df["risk_tier"] == "LOW").sum()
    stats = {
        "high_count":    int(high_ct),
        "medium_count":  int(med_ct),
        "low_count":     int(low_ct),
        "composite_mean": float(comp.mean()),
        "composite_p90":  float(comp.quantile(0.90)),
    }

    log.info("Score distribution:")
    log.info("  HIGH   (≥ %.0f):  %d  (%.1f%%)", TIER_HIGH,   high_ct, 100*high_ct/len(df))
    log.info("  MEDIUM (%.0f-%.0f): %d  (%.1f%%)", TIER_MEDIUM, TIER_HIGH-1, med_ct, 100*med_ct/len(df))
    log.info("  LOW    (<  %.0f):  %d  (%.1f%%)", TIER_MEDIUM, low_ct, 100*low_ct/len(df))
    log.info("  Mean composite: %.2f  |  P90: %.2f  |  P99: %.2f",
             comp.mean(), comp.quantile(0.90), comp.quantile(0.99))
    log.info("  Compliance  — mean %.2f  P90 %.2f",
             df["compliance_risk_score"].mean(), df["compliance_risk_score"].quantile(0.90))
    log.info("  TRI release — mean %.2f  P90 %.2f",
             df["tri_release_score"].mean(), df["tri_release_score"].quantile(0.90))
    log.info("  Pipeline    — mean %.2f  P90 %.2f",
             df["pipeline_context_score"].mean(), df["pipeline_context_score"].quantile(0.90))
    log.info("  State res.  — mean %.2f  P90 %.2f",
             df["state_resource_score"].mean(), df["state_resource_score"].quantile(0.90))

    # ---- Save full scored index ----
    DATA_DIR.joinpath("processed").mkdir(parents=True, exist_ok=True)
    df.to_csv(SCORED_OUT, index=False)
    log.info("Wrote scored master index: %d rows  |  %d cols → %s",
             len(df), len(df.columns), SCORED_OUT)

    # ---- Save lean Power BI summary ----
    summary = build_summary(df)
    summary.to_csv(SUMMARY_OUT, index=False)
    log.info("Wrote Power BI summary: %d rows  |  %d cols → %s",
             len(summary), len(summary.columns), SUMMARY_OUT)

    append_volume_log(len(df), stats)
    log.info("Done.")


if __name__ == "__main__":
    main()