# TRACE-ER Explorer: A Multi-State Environmental Risk Screening Prototype Built on Public Data

**Technical Brief**  
**Version:** 1.0  
**Date:** September 2026  
**Project:** TRACE-ER Explorer Prototype Development  

---

## Abstract

Environmental risk screening in the United States is hampered less by a shortage of public data than by the effort required to combine it. Federal databases like EPA's Facility Registry Service and ECHO hold detailed compliance histories on hundreds of thousands of regulated sites, but they capture almost nothing about the broader industrial context surrounding those sites: the pipelines running through nearby counties, the petroleum storage tanks leaking into local soils, or the density of oil and gas wells that have been drilled within a county over the past decade. TRACE-ER Explorer is a proof-of-concept data integration prototype that links eight public federal and state data sources into a single facility-level index covering 527,983 regulated entities across Texas, Pennsylvania, New Mexico, and Maine. A composite risk scoring framework assigns each facility a score based on documented compliance violations, toxic chemical releases, county-level pipeline incident history, and state-specific resource extraction activity. The resulting dataset is structured for direct use in Power BI and supports geospatial facility mapping, tier-based filtering, and multi-state comparison. This brief describes the data sources, integration methodology, scoring approach, and the key limitations practitioners should understand before applying the results.

---

## 1. Background

The case for building tools like TRACE-ER starts with a simple observation. When an environmental analyst wants to understand the risk profile of a particular industrial facility, the data they need is usually spread across half a dozen agency portals with different formats, update cycles, and geographic conventions. EPA's ECHO database provides compliance history for federally regulated sites. The Toxics Release Inventory tracks chemical releases at facilities above a certain size threshold. State agencies maintain separate registries of underground storage tank leaks, oil and gas well permits, and pipeline incident reports. None of these systems were designed to talk to each other.

The practical result is that cross-source analysis remains a manual and time-intensive task. A researcher trying to understand whether a cluster of high-penalty facilities in a particular Texas county also happens to sit near active petroleum contamination sites and a history of pipeline ruptures has to pull data from multiple portals, reconcile different geographic identifiers, and stitch the results together by hand. The analysis is doable, but the friction means it rarely gets done at the scale that would be useful for prioritizing remediation or allocating inspection resources.

TRACE-ER Explorer does not solve this problem completely. What it does is demonstrate that a reasonably complete integration of the key public sources is achievable, reproducible, and open to extension. The prototype covers four states at different stages of oil and gas development: Texas, a state with the country's heaviest concentration of pipeline infrastructure and petroleum storage sites; Pennsylvania, where unconventional shale gas development has expanded rapidly over the past fifteen years; New Mexico, a major Permian Basin producer with concentrated extraction activity in a small number of counties; and Maine, included as a contrast case with lower industrial intensity and a profile more representative of northeastern states.

---

## 2. Data Sources

Eight public data sources feed the prototype. All are freely accessible without API keys or licensing agreements, and all were last retrieved in September 2026.

**EPA Facility Registry Service (FRS)** provides the backbone of the facility index. FRS is EPA's authoritative registry of regulated entities, containing address, coordinate, regulatory program affiliation, and NAICS/SIC classification for more than five million records nationally. Filtering to the four study states yields 526,992 records after removing duplicates introduced by blank registry IDs in the ECHO join.

**EPA ECHO Exporter** contributes compliance history: inspection counts, formal enforcement actions, cumulative penalties, quarters with non-compliance, and current compliance status. ECHO records are available for 311,316 of the 527,983 facilities in the master index. The remaining 41 percent are registered in FRS but have no ECHO record, typically because they are small operations below federal enforcement thresholds or were registered in FRS for a specific program without ever generating a compliance event.

**EPA Toxics Release Inventory (TRI)** adds chemical release data for facilities that meet TRI reporting thresholds, covering 2019 through 2024. TRI data is more selective than ECHO, reaching only 3,919 facilities (0.74 percent of the master index), but the facilities it covers are often the most consequential from a toxic exposure standpoint. The TRI records used here include total on-site and off-site releases in pounds, carcinogen and persistent bioaccumulative toxic (PBT) flags, and PFAS indicators for each facility-year combination.

**PHMSA Pipeline Safety Flagged Incidents** provides county-level pipeline incident context for all four states, covering gas distribution, gas transmission and gathering, hazardous liquid, and LNG pipeline systems from 2019 through 2024. The dataset includes 1,230 qualifying incidents, of which the hazardous liquid system type accounts for 962, with Texas contributing 894 of those. Pipeline incidents are attributed to facilities at the county level rather than by spatial proximity, because incidents happen along linear infrastructure and cannot be reliably assigned to a specific nearby facility.

**Texas Railroad Commission R-3 Gas Processing Plants** data covers gas plant throughput and venting for the 13 months from August 2025 through August 2026. This dataset is one of the few self-service downloads from the Texas RRC; the main production data archive requires a manual email request to agency staff. The R-3 connector matched 410 gas plants to master index facilities using a 500-meter spatial join, providing throughput and critical infrastructure designation for those sites.

**TCEQ Leaking Petroleum Storage Tanks (LPST)** is a registry maintained by the Texas Commission on Environmental Quality documenting all petroleum storage tank leak cases since the mid-1980s. The database contains 26,884 cases statewide, of which 3,332 are currently active (corrective action not yet complete). This source adds ground-level contamination context that EPA federal databases do not capture.

**PA DEP Oil and Gas Well Locations** from PASDA contains 222,649 wells spanning both conventional and unconventional drilling activity across Pennsylvania, with records current as of September 2025. The dataset is joined to the master index at the county level and provides indicators for active well counts, unconventional well density, and recent permit activity (2019-2025), which serves as a proxy for ongoing drilling pressure.

**NM OCD Active Wells** were retrieved from the University of New Mexico's NHNM ArcGIS endpoint, which mirrors the New Mexico Oil Conservation Division permitting database. The dataset covers 55,572 active wells distributed across 12 of New Mexico's 33 counties, with the bulk concentrated in Eddy, Lea, and San Juan counties. The NM OCD FTP server was inaccessible at time of ingestion; the UNM endpoint is the documented public-access alternative.

---

## 3. Integration Methodology

The integration follows a strict left-join chain. The master facility index is established in a single step by joining FRS and ECHO on the shared EPA registry ID, producing 527,983 rows. Every subsequent data source is attached through a left join, so the row count never changes. This is not just a coding convention; it is what makes the dataset queryable as a flat table without surprise duplicates or dropped records.

The join strategy differs by data type. Facility-level sources (EPA TRI, Texas RRC R-3) are joined on registry identifiers when available, or by nearest-neighbor spatial match when registry IDs are absent. The RRC R-3 spatial join uses UTM Zone 14N, which provides meter-accurate distances suitable for the 500-meter threshold used there. County-level sources (PHMSA, TCEQ LPST, PA DEP, NM OCD) are joined on a normalized county name, produced by uppercasing the county string and stripping administrative suffixes like "County" and "Parish." The normalization is applied to both sides of the join to prevent mismatches from formatting differences between sources.

All source files are cached to disk after download. Re-running any connector after a successful first run is a no-operation unless the user explicitly forces a refresh. This design makes the pipeline practical to run incrementally as individual sources are updated on their own schedules.

---

## 4. Risk Scoring Framework

The risk score is designed to answer one question: given everything the public record shows about a facility and its surrounding county, how should it rank relative to other facilities for environmental screening purposes?

The answer comes from four components.

**Compliance risk (weight 35 percent)** is derived entirely from ECHO data. It combines the number of quarters with non-compliance in the past three years, the count of formal enforcement actions, cumulative penalties paid, and binary flags for significant non-compliance and Clean Air Act high-priority violator status. Each numeric input is log-transformed before normalization to reduce the outsized influence of a small number of extreme outliers. A facility with no formal enforcement actions scores zero on this component regardless of how many inspections it has had.

**TRI release risk (weight 40 percent)** applies only to the 3,919 facilities with TRI release records. It weighs total release tonnage most heavily, followed by whether any of the reported chemicals are carcinogens, persistent bioaccumulative toxics, or PFAS compounds. For the 99-plus percent of facilities with no TRI data, this component contributes zero to the composite. This is a deliberate design choice: TRI non-reporting does not indicate zero chemical risk, but the available public data cannot support any other inference.

**Pipeline context (weight 25 percent)** is a county-level score derived from PHMSA incident data. It captures total incident count, the subset classified as significant, and cumulative fatalities and injuries. Every facility in a county with pipeline incidents inherits this score, which means it reflects local infrastructure risk rather than anything specific to the facility itself.

**State resource context** is computed separately and excluded from the composite. It captures the industrial extraction burden within each state: active petroleum contamination sites and gas plant throughput for Texas, unconventional well density and recent permit counts for Pennsylvania, and well density with recent spud activity for New Mexico. This score is normalized within each state independently, so a Texas facility in Harris County and a New Mexico facility in Eddy County are scored against their respective in-state distributions rather than against each other. Maine receives a zero on this component because no state-specific source was integrated in this release.

The composite score is a weighted average of the first three components. For facilities with TRI data, the weights apply directly. For the majority without TRI records, the compliance and pipeline weights are renormalized to sum to one, so that TRI absence does not artificially cap scores at 60 percent of the possible range.

Risk tiers are assigned by percentile. The top 10 percent of facilities by composite score are labeled HIGH. The next 40 percent are MEDIUM. The bottom half are LOW. In the September 2026 dataset, HIGH corresponds to a composite score of roughly 20.5 or above, which at first sounds low on a 0-to-100 scale. That reflects the actual distribution of the data: most facilities have no enforcement history and sit in counties with modest pipeline incident counts, so the practical range of composite scores runs from 0 to about 72, not 0 to 100. The maximum observed score is 71.9, belonging to a facility in a high-incident Texas county with documented compliance violations and carcinogen releases.

---

## 5. Results

The integrated dataset covers 527,983 facility records with at least one regulatory program affiliation in EPA's system. Texas accounts for 64 percent of those records (339,304 facilities), reflecting its size and the density of its industrial activity. Pennsylvania has 125,029 facilities, New Mexico 44,142, and Maine 19,508.

Source coverage varies considerably across the dataset. Pipeline county indicators are the most broadly populated, reaching 74 percent of all facilities. TCEQ contamination site data covers 64 percent of the index (nearly all Texas facilities). PA DEP well data covers 61 percent of Pennsylvania facilities, concentrated in counties with active drilling. NM OCD data reaches 40 percent of New Mexico facilities. TRI release records are the narrowest, at 0.74 percent.

The composite score distribution is right-skewed, as expected for a population that includes everything from major petrochemical complexes to small water utilities. The median composite score is 5.2. The 90th percentile is 20.5. The distribution's shape reflects the underlying data: most facilities do not have formal enforcement actions, most do not meet TRI reporting thresholds, and many sit in counties without recent pipeline incidents. Facilities that score into the HIGH tier typically share at least two of the three conditions that drive the composite: a county with significant pipeline incident history, some documented compliance violations, and in many cases TRI releases of hazardous chemicals.

Texas accounts for 94 percent of HIGH-tier facilities in the dataset, largely because PHMSA hazardous liquid pipeline incidents are concentrated there. This is not a scoring artifact. The state genuinely has the highest pipeline incident count across the study period, and the county join means a substantial share of Texas facilities inherit that county-level context.

---

## 6. Limitations

Several limitations bear directly on how these results should be used.

The pipeline context score applies at the county level. A facility sitting in Harris County, Texas inherits the same pipeline context score as every other facility in that county, regardless of its actual proximity to pipeline infrastructure. For large counties with concentrated industrial clusters and scattered rural areas, this can produce scores that misrepresent individual site conditions. Spatial matching of pipeline incidents to facilities by distance would reduce this problem but would also require decisions about what distance threshold is appropriate for linear infrastructure.

TRI non-coverage is substantial. The 99.3 percent of facilities with a TRI release score of zero includes both facilities that genuinely release no reportable quantities of covered chemicals and facilities that release chemicals at levels below TRI thresholds or that are in exempted industry categories. The score cannot distinguish between these cases. Users evaluating specific facilities should verify TRI coverage status independently before treating a zero TRI score as evidence of low chemical risk.

RRC R-3 spatial matching reached only 410 of 1,451 identified gas plants. The 38.7 percent of plants with placeholder coordinates in the RRC system could not participate in the spatial join. Those plants appear in the interim plant features file but contribute nothing to the master index.

The NM OCD data covers active wells only. Plugged and abandoned wells, which can be significant sources of methane leakage and groundwater contamination, are not available through the public-access API endpoint used here. New Mexico has a large legacy of older wells in various stages of abandonment, and this analysis does not capture them.

Maine is the weakest of the four states in the dataset. The only contextual data available for Maine facilities comes from PHMSA, which recorded two incidents there in the analysis period. There is no state-specific contamination registry, well registry, or equivalent source integrated in this release.

Finally, the dataset reflects what public agencies have recorded, which is not the same as what has occurred. Environmental violations that were not detected, not reported, or not yet entered into federal or state databases are invisible here.

---

## 7. Applications

The dataset is designed to support two primary use cases. The first is prioritizing facilities for further investigation. The HIGH tier contains roughly 53,000 facilities that score above the 90th percentile on the composite. Within that group, the compliance and TRI sub-scores identify which facilities have documented violation histories and chemical release patterns, and the state resource score adds local extraction context. That combination is more informative than any single-source ranking.

The second use case is geographic analysis. The county-level indicators for PHMSA incidents, TCEQ contamination, and well density are designed for map visualization. A county with a high pipeline incident count, a substantial number of active LPST sites, and dense unconventional well activity presents a different risk profile than a county where only one of those factors is elevated, and the data supports that distinction.

The Power BI summary table (`facility_risk_summary.csv`) contains 53 columns covering facility identity, all score components, risk tier, source coverage flags, and the key underlying indicators. It is structured for direct import without preprocessing.

---

## 8. Future Development

The most impactful near-term extension would be integrating USGS Water Quality Portal data. Surface and groundwater monitoring stations in proximity to industrial facilities provide direct environmental outcome measurements that all of the current sources only approximate through activity and compliance indicators. Adding water quality data would allow the scoring framework to connect upstream industrial activity with downstream observed impacts.

Maine DEP data would bring Maine to the same level of state-specific coverage as Texas, Pennsylvania, and New Mexico. Maine's environmental data portal includes facility-level spill and remediation records that would substantially improve the utility of the Maine subset.

The RRC placeholder coordinate problem is worth solving before scaling the Texas analysis. The Texas RRC publishes GIS layers with well and facility locations through its mapping portal; cross-referencing gas plant serial numbers against those layers would recover coordinates for a substantial share of the 561 plants currently excluded from spatial matching.

---

## Data Citations

All sources are public and freely accessible. The versions used in this prototype were retrieved in September 2026.

- EPA Facility Registry Service: https://www.epa.gov/frs
- EPA ECHO Exporter: https://echo.epa.gov/tools/data-downloads
- EPA Toxics Release Inventory (Envirofacts): https://data.epa.gov/efservice/
- PHMSA Pipeline Safety Flagged Incidents: https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data
- Texas RRC R-3 Gas Processing Plants: https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/r-3-gas-processing-plants-report
- TCEQ Leaking Petroleum Storage Tanks: https://www.tceq.texas.gov/assets/public/admin/data/docs/lpst.txt
- PA DEP Well Locations via PASDA: https://www.pasda.psu.edu/uci/DataSummary.aspx?dataset=1088
- NM OCD via UNM NHNM: https://nhnm-gisweb.unm.edu/arcgis/rest/services/NMEDB/ActiveOilandGasWells/MapServer/3

---

*End of Technical Brief v1.0*
