# TRACE-ER Explorer: Institutional Brief

**Environmental Risk Screening Across Federal and State Data**  
**September 2026**

---

## The Problem This Addresses

Federal and state agencies collect a substantial amount of environmental data on regulated facilities. EPA tracks compliance history and toxic chemical releases. State agencies maintain separate records on leaking petroleum tanks, oil and gas wells, and pipeline incidents. Each of these systems does its job, but they were not built to work together.

The result is that anyone trying to understand the environmental risk profile of a specific community or region has to pull data from multiple portals, reconcile different formats and geographic identifiers, and assemble the picture by hand. That process is time-consuming enough that it rarely happens at scale. Inspection priorities, remediation planning, and resource allocation often end up based on whichever data source is most convenient rather than the most complete picture available.

TRACE-ER Explorer is a prototype that demonstrates what becomes possible when those sources are integrated.

---

## What Was Built

The prototype links eight public data sources into a single facility-level index covering four states: Texas, Pennsylvania, New Mexico, and Maine. All data comes from government sources that are freely accessible to the public without licensing fees or special access agreements.

The final dataset contains records on 527,983 regulated facilities. For each facility, the dataset captures:

- **Compliance history** from EPA ECHO: inspection counts, formal enforcement actions, total penalties, and current compliance status.
- **Toxic chemical releases** from the EPA Toxics Release Inventory (2019-2024): release volumes, and flags for carcinogens, persistent bioaccumulative toxics, and PFAS compounds.
- **Pipeline incident context** from PHMSA (2019-2024): the number and severity of pipeline accidents in the facility's county, including fatalities and estimated costs.
- **State-specific context** for each state: Texas petroleum contamination sites from TCEQ's leak registry (26,884 cases); Pennsylvania oil and gas wells from the PA DEP (222,649 wells); New Mexico active wells from the OCD (55,572 wells); and gas plant throughput and critical infrastructure status for Texas facilities from the Railroad Commission.

Each facility receives a composite risk score reflecting what the public record shows about it and its surrounding county. Scores are assigned to three tiers. The top 10 percent of facilities by score are labeled HIGH, the next 40 percent MEDIUM, and the bottom 50 percent LOW. In this dataset, roughly 52,900 facilities fall into the HIGH tier.

The output is a structured data file ready for import into Power BI, where it supports facility mapping, filtering by tier or state, and side-by-side comparison of compliance history, release data, and contextual indicators for any facility in the index.

---

## What This Enables

The most direct application is prioritization. When inspection resources are limited, a ranked list of facilities that combines compliance violations with toxic release history and county-level infrastructure risk is more useful than any single source alone. A facility with a pattern of formal enforcement actions, carcinogen releases on the TRI, and located in a county with a high pipeline incident rate warrants a different level of attention than one with a clean record in a low-incident county, even if both are nominally in the same regulated category.

The geographic indicators also support community-level analysis. Counties with high concentrations of active petroleum contamination sites, dense unconventional well activity, and significant pipeline incident history can be identified and compared across states. That kind of cross-state view is not currently available from any single agency portal.

For institutional partners considering adoption or extension, the pipeline is open-source, reproducible, and designed so that individual data sources can be updated on their own schedules without rebuilding the entire dataset from scratch.

---

## Honest Limitations

This prototype reflects what government agencies have recorded, which is not the same as everything that has happened. Violations that were not detected, not inspected, or not yet entered into agency databases do not appear in the scores. A facility with a zero compliance score may be well-managed or may simply be below the inspection threshold.

Coverage is uneven across the four states. Texas is the most data-rich, with three state-specific sources integrated. Maine is the least supported, appearing only through federal datasets and two PHMSA incidents. The scores for Maine facilities carry less information than the scores for Texas facilities.

The pipeline context score is attached to facilities at the county level, not based on their distance from specific pipelines. A facility in Harris County, Texas gets the same county-level pipeline score as every other facility in that county. For small counties this is a reasonable approximation. For large counties it is a rougher one.

The scores reflect the primary analysis period of 2019 through 2024 for incident and release data. The contamination site registries (TCEQ, PA DEP, NM OCD) include older records because historical contamination remains material to current risk, but the pipeline and TRI data are bounded by that window.

---

## What Would Make This Stronger

Three additions would substantially increase the dataset's value.

Adding USGS Water Quality Portal data would connect upstream industrial activity to downstream water quality measurements at monitoring stations. The current dataset tracks what facilities emit and what incidents have occurred nearby; water quality data would show whether those activities are associated with measurable changes in surface or groundwater quality.

Integrating Maine DEP records would bring Maine to the same level of state-specific coverage as the other three states. Maine currently has no contamination site registry or well permit data in the index.

Extending coverage beyond four states would allow the scoring framework to serve as a national screening tool rather than a regional prototype. The architecture is designed to scale. Adding a new state requires identifying the relevant state agency data sources and writing a connector that follows the existing pattern.

---

## Contact and Documentation

Full technical documentation, including the data dictionary, validation report, methodology description, and the source code for all data connectors, is available in the project repository.

Questions about the dataset, scoring methodology, or potential applications should be directed to the project team.

---

*TRACE-ER Explorer v1.0 | September 2026*  
*Data sourced from EPA FRS, EPA ECHO, EPA TRI, PHMSA, Texas RRC, TCEQ, PA DEP, and NM OCD. All sources are public and freely accessible.*
