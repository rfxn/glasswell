# FracFocus disclosure fixture

The header and timestamp shapes are copied from `DisclosureList_1.csv` in the official
`https://www.fracfocusdata.org/digitaldownload/FracFocusCSV.zip` archive measured on
2026-08-26. The bundled data dictionary defines `JobEndDate` as the date the hydraulic
fracturing job completed, excluding site teardown.

Rows are synthetic around those source-faithful formats so tests can exercise duplicate
disclosures, hyphenated and compact API-14, malformed dates, reversed chronology, an OGD
orphan, and a non-ND row without redistributing source records. The ZIP is assembled in the
test with fixed member timestamps so its manifest identity is deterministic.
