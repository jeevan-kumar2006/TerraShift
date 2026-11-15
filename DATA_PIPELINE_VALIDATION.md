# Data Pipeline Validation

## Ingestion

NASA POWER requests use the official monthly point endpoint with explicit parameter, community, latitude, longitude, format, and year bounds. The parser reads the returned parameter map, preserves API headers, rejects malformed timestamps, and converts POWER fill values to missing observations.

External CSV/ASCII imports are parsed by `parse_external_timeseries`; they are labeled `imported` or `synthetic` and do not inherit NASA provenance.

## Units

Configured units are explicit in `PARAMETER_METADATA`:

- `T2M`: °C
- `PRECTOTCORR`: mm/day
- `GWETROOT` / `GWETPROF`: fraction 0–1
- `QV2M`: g/kg
- `PS`: kPa

The acquisition QC layer applies variable-aware physical bounds. A remaining limitation is that imported files cannot be unit-verified without authoritative file metadata.

## Spatial processing

Point investigations are grid-cell analyses. The requested coordinate and actual/source coordinate are both retained. Offline fallback is rejected beyond 500 km and reports the source distance.

Acquisition polygon processing:

- normalizes 0–360 longitudes to -180–180;
- sorts latitude ascending;
- masks grid-cell centers against the actual GeoJSON polygon;
- computes cosine-latitude weighted means;
- reports region ID, boundary file, vertex count, grid-cell count, and valid observations.

A bounding box is not treated as an administrative boundary.

Known limitation: center-point masking can exclude a coarse grid cell whose area overlaps a polygon but whose center lies outside it. This is disclosed by the subset result and should be addressed before claiming exact boundary-integrated totals.

## Temporal processing

Monthly timestamps are parsed into a period index, sorted, deduplicated by mean, and completed. Missing values are never converted to zero. Interior gaps up to three months are linearly interpolated and reported; longer gaps reject the analysis.

India seasonal analysis aggregates monthly values by calendar year and IMD-style seasons (`JF`, `MAM`, `JJAS`, `OND`). Annual anomalies use a declared 1991–2020 baseline when at least ten baseline years are available; otherwise the full available period is used and the returned baseline period makes that fallback visible.

## Quality and manifest

Acquisition validators preserve raw files, write validated copies, apply product-specific fill/QC/range filters, and append manifest and validation records. The raw source is not modified.

## Validation evidence

- Live NASA POWER request: HTTP 200, API `v2.10.0`, T2M units `C`, 24 monthly values for 2020–2021.
- Backend regression suite: 39 passed.
- Frontend production build: passed.
- CMR live discovery remains dependent on external service availability and is not treated as a local validity prerequisite.

