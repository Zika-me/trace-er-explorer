# Duplicate ID Diagnostic Report

Checks whether duplicate keys exist in FRS, ECHO, TRI, or the master
index — originally triggered by the ECHO-only 440-row gap (which turned
out to be null IDs, not duplicates), extended to TRI after
a real 3-way master index build showed a 40-row gap unexplained by the
null-ID fix alone.

## FRS interim table (key: registry_id)

- total_rows: 526992
- null_id_count: 0
- unique_non_null_ids: 526992
- duplicate_id_count: 0
- extra_rows_from_duplicates: 0
- sample_duplicated_ids: {}

## ECHO interim table (key: registry_id)

- total_rows: 311717
- null_id_count: 441
- unique_non_null_ids: 311276
- duplicate_id_count: 0
- extra_rows_from_duplicates: 0
- sample_duplicated_ids: {}
  **441 rows have a BLANK/missing ID — these have no usable identifier at all, which is different from and likely more important than duplication.**

## TRI interim table (key: epa_registry_id)

- total_rows: 8361
- null_id_count: 0
- unique_non_null_ids: 8321
- duplicate_id_count: 34
- extra_rows_from_duplicates: 40
- sample_duplicated_ids: {'110067040703': 4, '110070736926': 3, '110000599406': 3, '110031267064': 3, '110010974320': 3, '110016706448': 2, '110020056464': 2, '110000619910': 2, '110027376293': 2, '110038017375': 2}
  **34 distinct IDs appear more than once, accounting for 40 extra rows.**

## Master facility index (key: master_id)

- total_rows: 527983
- null_id_count: 0
- unique_non_null_ids: 527943
- duplicate_id_count: 34
- extra_rows_from_duplicates: 40
- sample_duplicated_ids: {'110067040703': 4, '110000599406': 3, '110010974320': 3, '110031267064': 3, '110070736926': 3, '110000460885': 2, '110000463098': 2, '110000463178': 2, '110000464462': 2, '110000492351': 2}
  **34 distinct IDs appear more than once, accounting for 40 extra rows.**

## Sample duplicate rows (for visual inspection)


### TRI interim table (key: epa_registry_id) — all rows sharing ID 110067040703

```
      tri_facility_id                   facility_name                        address      city  county state_county_fips_code state_abbr postal_code region fac_closed_ind                       mail_name            mail_street_address mail_city mail_state_abbr mail_province   mail_country mail_zip_code asgn_federal_ind asgn_agency frs_id parent_co_db_num       parent_co_name latitude longitude pref_latitude pref_longitude coord_accuracy_value coord_collect_method pref_desc_category coord_datum pref_source_scale pref_qa_code asgn_partial_ind  asgn_public_contact asgn_public_phone     asgn_public_contact_email bia_code  standardized_parent_company asgn_public_phone_ext epa_registry_id asgn_technical_contact asgn_technical_phone asgn_technical_phone_ext mail asgn_technical_contact_email           foreign_parent_co_name foreign_parent_co_db_num standardized_foreign_parent_company
2862  77507BCGSS952BA     LINDE GAS NORTH AMERICA LLC             9502 BAY PORT BLVD  PASADENA  HARRIS                  48201         TX       77507      6              1                LINDE GAS NA LLC             9502 BAY PORT BLVD  PASADENA              TX           NaN  UNITED STATES         77507                C         NaN    NaN        001368141   LINDE GAS N.A. LLC   293732    950348           NaN            NaN                  NaN                  NaN                NaN         NaN               NaN          NaN                0         STANLEY CHIU        2814748075     STANLEY.CHIU@CELANESE.COM      NaN  LINDE GAS NORTH AMERICA LLC                   NaN    110067040703                    NaN                  NaN                      NaN  NaN                          NaN                              NaN                      NaN                                 NaN
2874  77507DWCHM952BB           ARKEMA INC CLEAR LAKE            9502 B BAYPORT BLVD  PASADENA  HARRIS                  48201         TX       77507      6              0           ARKEMA INC CLEAR LAKE            9502 B BAYPORT BLVD  PASADENA              TX           NaN            NaN         77507                C         NaN    NaN        622121697  ARKEMA DELAWARE INC   293717    950350           NaN            NaN                  NaN                  NaN                NaN         NaN               NaN          NaN                0  BARBARA C PARTRIDGE        7137517297  BARBARA.PARTRIDGE@ARKEMA.COM      NaN          ARKEMA DELAWARE INC                   NaN    110067040703                    NaN                  NaN                      NaN  NaN                          NaN  ARKEMA A SOCIETE ANONYME (S.A.)                      NaN       ARKEMA A SOCIETE ANONYME (SA)
2881  77507HCHST9502B   CELANESE LTD CLEAR LAKE PLANT              9502 BAYPORT BLVD  PASADENA  HARRIS                  48201         TX       77507      6              0   CELANESE LTD CLEAR LAKE PLANT              9502 BAYPORT BLVD  PASADENA              TX           NaN            NaN         77507                C         NaN    NaN        170204486        CELANESE CORP   293730    950353     29.621389      95.063889                80.00                   UN                 UN           1                 U         1010                0          JOSEPH ROSS        2814746322      JOSEPH.ROSS@CELANESE.COM      NaN                CELANESE CORP                   NaN    110067040703                    NaN                  NaN                      NaN  NaN                          NaN                              NaN                      NaN                                 NaN
2918  7750WCLRNT952BA  CLARIANT CORP CLEAR LAKE PLANT  9502 BAYPORT BLVD - ETOX UNIT  PASADENA  HARRIS                  48201         TX       77507      6              0  CLARIANT CORP CLEAR LAKE PLANT  9502 BAYPORT BLVD - ETOX UNIT  PASADENA              TX           NaN            NaN         77507                C         NaN    NaN        108706425        CLARIANT CORP      NaN       NaN           NaN            NaN                  NaN                  NaN                NaN         NaN               NaN          NaN                0        ANDRE POLLARD        7048222113    ANDRE.POLLARD@CLARIANT.COM      NaN                CLARIANT CORP                   NaN    110067040703                    NaN                  NaN                      NaN  NaN                          NaN       CLARIANT INTERNATIONAL LTD                      NaN          CLARIANT INTERNATIONAL LTD
```

### Master facility index (key: master_id) — all rows sharing ID 110067040703

```
           master_id            facility_name            address      city postal_code state  county   latitude  longitude coord_accuracy_value coord_accuracy_value.1 coord_source sources_present source_count linkage_confidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           programs_raw   site_type  huc_code tri_facility_id_tri region_tri   parent_co_name_tri fac_closed_ind_tri
320153  110067040703  ARKEMA- CLEARLAKE PLANT  9502 BAYPORT BLVD  PASADENA       77507    TX  HARRIS   29.62139  -95.06389                  NaN                    NaN          frs    FRS,ECHO,TRI            3           EXACT_ID  AIR:TX0000004820100003, AIR:TX0000004820101556, AIR:TX0000004820101588, AIR:TX0000004820101897, AIR:TX0000004820102063, AIRS/AFS:4820100003, AIRS/AFS:4820101556, AIRS/AFS:4820101588, AIRS/AFS:4820101897, BR:TXR000057414, CEDRI:CEDRI10020962, CEDRI:CEDRI10037431, CEDRI:CEDRI10105920, CEDRI:CEDRI10220808, E-GGRT:1003049, E-GGRT:1006797, E-GGRT:1006867, E-GGRT:1015570, ICIS:30466, NPDES:TXR05CV42, NPDES:TXR05CX45, NPDES:TXR05DU84, NPDES:TXR05EP13, NPDES:TXR05FI21, NPDES:TXR05GI76, NPDES:TXR05V084, NPDES:TXR15294J, OSHA-OIS:342007085, RCRAINFO:TXD07843245, RCRAINFO:TXD078432457, RCRAINFO:TXR000052175, RCRAINFO:TXR000057414, RCRAINFO:TXR000080054, RCRAINFO:TXR000086609, SFDW:TX1011168, SFDW:TX1011168 12011, SFDW:TX1011168 63020, TRIS:77507BCGSS952BA, TRIS:77507DWCHM952BB, TRIS:77507HCHST9502B, TRIS:7750WCLRNT952BA, TSCA:100604695, TSCA:100605289, TSCA:100605290, TSCA:TSCA10057210, TSCA:TSCA122144, TSCA:TSCA123946, TSCA:TSCA4855, TSCA:TSCA4936, TSCA:TSCA7249, TX-TCEQ ACR:RN100227016, TX-TCEQ ACR:RN103080487, TX-TCEQ ACR:RN104150123, TX-TCEQ ACR:RN104541743, TX-TCEQ ACR:RN105499420, TX-TCEQ ACR:RN105922876, TX-TCEQ ACR:RN109503698  STATIONARY  12040204     77507BCGSS952BA          6   LINDE GAS N.A. LLC                  1
320154  110067040703  ARKEMA- CLEARLAKE PLANT  9502 BAYPORT BLVD  PASADENA       77507    TX  HARRIS   29.62139  -95.06389                  NaN                    NaN          frs    FRS,ECHO,TRI            3           EXACT_ID  AIR:TX0000004820100003, AIR:TX0000004820101556, AIR:TX0000004820101588, AIR:TX0000004820101897, AIR:TX0000004820102063, AIRS/AFS:4820100003, AIRS/AFS:4820101556, AIRS/AFS:4820101588, AIRS/AFS:4820101897, BR:TXR000057414, CEDRI:CEDRI10020962, CEDRI:CEDRI10037431, CEDRI:CEDRI10105920, CEDRI:CEDRI10220808, E-GGRT:1003049, E-GGRT:1006797, E-GGRT:1006867, E-GGRT:1015570, ICIS:30466, NPDES:TXR05CV42, NPDES:TXR05CX45, NPDES:TXR05DU84, NPDES:TXR05EP13, NPDES:TXR05FI21, NPDES:TXR05GI76, NPDES:TXR05V084, NPDES:TXR15294J, OSHA-OIS:342007085, RCRAINFO:TXD07843245, RCRAINFO:TXD078432457, RCRAINFO:TXR000052175, RCRAINFO:TXR000057414, RCRAINFO:TXR000080054, RCRAINFO:TXR000086609, SFDW:TX1011168, SFDW:TX1011168 12011, SFDW:TX1011168 63020, TRIS:77507BCGSS952BA, TRIS:77507DWCHM952BB, TRIS:77507HCHST9502B, TRIS:7750WCLRNT952BA, TSCA:100604695, TSCA:100605289, TSCA:100605290, TSCA:TSCA10057210, TSCA:TSCA122144, TSCA:TSCA123946, TSCA:TSCA4855, TSCA:TSCA4936, TSCA:TSCA7249, TX-TCEQ ACR:RN100227016, TX-TCEQ ACR:RN103080487, TX-TCEQ ACR:RN104150123, TX-TCEQ ACR:RN104541743, TX-TCEQ ACR:RN105499420, TX-TCEQ ACR:RN105922876, TX-TCEQ ACR:RN109503698  STATIONARY  12040204     77507DWCHM952BB          6  ARKEMA DELAWARE INC                  0
320155  110067040703  ARKEMA- CLEARLAKE PLANT  9502 BAYPORT BLVD  PASADENA       77507    TX  HARRIS  29.621389  95.063889                  NaN                  80.00          tri    FRS,ECHO,TRI            3           EXACT_ID  AIR:TX0000004820100003, AIR:TX0000004820101556, AIR:TX0000004820101588, AIR:TX0000004820101897, AIR:TX0000004820102063, AIRS/AFS:4820100003, AIRS/AFS:4820101556, AIRS/AFS:4820101588, AIRS/AFS:4820101897, BR:TXR000057414, CEDRI:CEDRI10020962, CEDRI:CEDRI10037431, CEDRI:CEDRI10105920, CEDRI:CEDRI10220808, E-GGRT:1003049, E-GGRT:1006797, E-GGRT:1006867, E-GGRT:1015570, ICIS:30466, NPDES:TXR05CV42, NPDES:TXR05CX45, NPDES:TXR05DU84, NPDES:TXR05EP13, NPDES:TXR05FI21, NPDES:TXR05GI76, NPDES:TXR05V084, NPDES:TXR15294J, OSHA-OIS:342007085, RCRAINFO:TXD07843245, RCRAINFO:TXD078432457, RCRAINFO:TXR000052175, RCRAINFO:TXR000057414, RCRAINFO:TXR000080054, RCRAINFO:TXR000086609, SFDW:TX1011168, SFDW:TX1011168 12011, SFDW:TX1011168 63020, TRIS:77507BCGSS952BA, TRIS:77507DWCHM952BB, TRIS:77507HCHST9502B, TRIS:7750WCLRNT952BA, TSCA:100604695, TSCA:100605289, TSCA:100605290, TSCA:TSCA10057210, TSCA:TSCA122144, TSCA:TSCA123946, TSCA:TSCA4855, TSCA:TSCA4936, TSCA:TSCA7249, TX-TCEQ ACR:RN100227016, TX-TCEQ ACR:RN103080487, TX-TCEQ ACR:RN104150123, TX-TCEQ ACR:RN104541743, TX-TCEQ ACR:RN105499420, TX-TCEQ ACR:RN105922876, TX-TCEQ ACR:RN109503698  STATIONARY  12040204     77507HCHST9502B          6        CELANESE CORP                  0
320156  110067040703  ARKEMA- CLEARLAKE PLANT  9502 BAYPORT BLVD  PASADENA       77507    TX  HARRIS   29.62139  -95.06389                  NaN                    NaN          frs    FRS,ECHO,TRI            3           EXACT_ID  AIR:TX0000004820100003, AIR:TX0000004820101556, AIR:TX0000004820101588, AIR:TX0000004820101897, AIR:TX0000004820102063, AIRS/AFS:4820100003, AIRS/AFS:4820101556, AIRS/AFS:4820101588, AIRS/AFS:4820101897, BR:TXR000057414, CEDRI:CEDRI10020962, CEDRI:CEDRI10037431, CEDRI:CEDRI10105920, CEDRI:CEDRI10220808, E-GGRT:1003049, E-GGRT:1006797, E-GGRT:1006867, E-GGRT:1015570, ICIS:30466, NPDES:TXR05CV42, NPDES:TXR05CX45, NPDES:TXR05DU84, NPDES:TXR05EP13, NPDES:TXR05FI21, NPDES:TXR05GI76, NPDES:TXR05V084, NPDES:TXR15294J, OSHA-OIS:342007085, RCRAINFO:TXD07843245, RCRAINFO:TXD078432457, RCRAINFO:TXR000052175, RCRAINFO:TXR000057414, RCRAINFO:TXR000080054, RCRAINFO:TXR000086609, SFDW:TX1011168, SFDW:TX1011168 12011, SFDW:TX1011168 63020, TRIS:77507BCGSS952BA, TRIS:77507DWCHM952BB, TRIS:77507HCHST9502B, TRIS:7750WCLRNT952BA, TSCA:100604695, TSCA:100605289, TSCA:100605290, TSCA:TSCA10057210, TSCA:TSCA122144, TSCA:TSCA123946, TSCA:TSCA4855, TSCA:TSCA4936, TSCA:TSCA7249, TX-TCEQ ACR:RN100227016, TX-TCEQ ACR:RN103080487, TX-TCEQ ACR:RN104150123, TX-TCEQ ACR:RN104541743, TX-TCEQ ACR:RN105499420, TX-TCEQ ACR:RN105922876, TX-TCEQ ACR:RN109503698  STATIONARY  12040204     7750WCLRNT952BA          6        CLARIANT CORP                  0
```
