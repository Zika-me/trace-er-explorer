#!/usr/bin/env python3
"""
scripts/generate_release_manifest.py

Computes file sizes and SHA-256 checksums

Run from the repository root with the virtual environment active:
    python scripts/generate_release_manifest.py
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---- Files included in the v1.0 release ----
RELEASE_FILES: dict[str, list[str]] = {
    "Processed data outputs": [
        "data/processed/master_risk_scores.csv",
        "data/processed/facility_risk_summary.csv",
        "data/processed/tri_release_features.csv",
        "data/processed/rrc_r3_plant_features.csv",
        "data/processed/phmsa_county_features.csv",
        "data/processed/tceq_lpst_county_features.csv",
        "data/processed/padep_county_features.csv",
        "data/processed/nmocd_county_features.csv",
    ],
    "Cleaned interim tables": [
        "data/interim/phmsa_incidents.csv",
        "data/interim/tceq_lpst_sites.csv",
        "data/interim/rrc_r3_gas_plants.csv",
        "data/interim/padep_wells.csv",
        "data/interim/nmocd_wells.csv",
    ],
    "Documentation": [
        "docs/TRACE_ER_Explorer_Data_Dictionary_v1_0.md",
        "docs/TRACE_ER_Explorer_Validation_Report_v1_0.md",
        "docs/TRACE_ER_Explorer_Technical_Implementation_Guide_v1_0.md",
        "docs/TRACE_ER_Explorer_White_Paper_v1_0.md",
        "docs/TRACE_ER_Explorer_Institutional_Brief_v1_0.md",
        "docs/TRACE_ER_Explorer_Power_BI_Dashboard_Guide_v1_0.md",
    ],
    "Source code — ingest connectors": [
        "src/ingest/fetch_frs.py",
        "src/ingest/fetch_echo.py",
        "src/linkage/build_master_index.py",
        "src/ingest/fetch_tri.py",
        "src/ingest/fetch_tri_releases.py",
        "src/features/aggregate_tri_release_features.py",
        "src/features/join_tri_features_to_master_index.py",
        "src/ingest/fetch_rrc_r3_gas_plants.py",
        "src/ingest/join_rrc_r3_to_master.py",
        "src/ingest/fetch_phmsa_incidents.py",
        "src/ingest/fetch_tceq_lpst.py",
        "src/ingest/fetch_padep_wells.py",
        "src/ingest/fetch_nmocd_wells.py",
    ],
    "Source code — linkage scripts": [
        "src/linkage/build_master_index.py",
        "src/linkage/join_tri_releases_to_facility.py",
    ],
    "Source code — features": [
        "src/features/build_risk_scores.py",
    ],
    "Validation and audit": [
        "validation/source_volume_log.csv",
        "outreach/TRACE_ER_outreach_feedback_log.csv",
    ],
    "Release metadata": [
        "scripts/generate_release_manifest.py",
        "TRACE_ER_Explorer_v1_0_Release_Manifest.md",
    ],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# TRACE-ER Explorer — Release Manifest",
        "",
        "**Release:** v1.0  ",
        f"**Generated:** {now}  ",
        "**States:** TX, PA, NM, ME  ",
        "**Master index rows:** 527,983  ",
        "**Master index columns:** 111  ",
        "",
        "---",
        "",
        "## Release Contents",
        "",
        "SHA-256 checksums and file sizes are computed at manifest generation time.  ",
        "Verify a file with: `shasum -a 256 <filename>` (macOS/Linux) or "
        "`Get-FileHash <filename> -Algorithm SHA256` (PowerShell).",
        "",
    ]

    total_size = 0
    total_files = 0
    missing: list[str] = []

    for section, paths in RELEASE_FILES.items():
        lines.append(f"### {section}")
        lines.append("")
        lines.append("| File | Size | SHA-256 |")
        lines.append("|---|---|---|")

        for rel in paths:
            full = BASE_DIR / rel
            if full.exists():
                size = full.stat().st_size
                checksum = sha256(full)
                lines.append(f"| `{rel}` | {human_size(size)} | `{checksum[:16]}...` |")
                total_size += size
                total_files += 1
                print(f"  OK  {rel}  ({human_size(size)})")
            else:
                lines.append(f"| `{rel}` | NOT FOUND | — |")
                missing.append(rel)
                print(f"  --  {rel}  (NOT FOUND)")

        lines.append("")

    lines += [
        "---",
        "",
        "## Summary",
        "",
        f"| Item | Value |",
        f"|---|---|",
        f"| Total files | {total_files} |",
        f"| Total size | {human_size(total_size)} |",
        f"| Missing files | {len(missing)} |",
        f"| Generated | {now} |",
        "",
    ]

    if missing:
        lines += [
            "## Missing Files",
            "",
            "The following files were not found at manifest generation time:",
            "",
        ]
        for m in missing:
            lines.append(f"- `{m}`")
        lines.append("")

    lines += [
        "---",
        "",
        "*TRACE-ER Explorer v1.0 | September 2026*  ",
        "*All source data is public and freely accessible.*",
    ]

    out = BASE_DIR / "TRACE_ER_Explorer_v1_0_Release_Manifest.md"
    out.write_text("\n".join(lines))
    print(f"\nManifest written to: {out}")
    print(f"Total: {total_files} files | {human_size(total_size)}")
    if missing:
        print(f"WARNING: {len(missing)} file(s) not found — see manifest for details")


if __name__ == "__main__":
    main()