# India Environmental & Earth System Trend Analysis Report

**Project:** TerraShift — India-Exclusive Earth Observation & Trend Detective  
**Geographical Scope:** India (`6.0°N–37.5°N, 68.0°E–97.5°E`)  
**Temporal Window:** 1981–2025 (540 monthly observations per benchmark site; baseline climatology: 1991–2020)  
**Primary Notebook:** [`notebooks/india_environmental_trend_analysis.ipynb`](notebooks/india_environmental_trend_analysis.ipynb)

---

## 1. Executive Summary

TerraShift's analytical scope has been pivoted exclusively to India's geographical boundaries (`6.0°N–37.5°N, 68.0°E–97.5°E`), covering 10 major physiographic and climatic regions across all Indian states and Union Territories. Using real 1981–2025 monthly NASA POWER (MERRA-2 reanalysis & model hydrology) records across 12 benchmark locations and NASA Terra/MOPITT `MOP03JM` Carbon Monoxide NetCDF observations over India, we evaluated long-term trends and India Meteorological Department (IMD) four-season dynamics (`JF`, `MAM`, `JJAS`, `OND`) with Mann-Kendall testing, Theil-Sen slopes, OLS regression, lag-1 autocorrelation diagnostics, and Holm-Bonferroni multiple-hypothesis correction.

Key computed findings from the 1981–2025 record include:
- **Coastal & Post-Monsoon Warming:** Chennai / Coromandel Coast (`T2M`) exhibits a statistically significant overall warming trend of **`+0.0534 °C/decade`** (`p = 0.0009`), driven primarily by a highly significant Post-Monsoon (`OND`) warming of **`+0.1802 °C/decade`** (`Holm p = 0.00035`), with 2019 recording the highest positive annual anomaly (`+0.4621 °C` above the 1991–2020 baseline).
- **Northeast & Peninsular Monsoon Amplification:** Shillong / Meghalaya (`PRECTOTCORR`) shows the strongest precipitation increase in the benchmark suite at **`+1.3238 mm/day/decade`** (`p < 0.0001`), with statistically significant increases after Holm-Bonferroni correction across `MAM` (`+1.6945 mm/day/dec`, `Holm p = 0.00001`), `JJAS` (`+2.5122 mm/day/dec`, `Holm p < 0.0001`), and `OND` (`+0.4372 mm/day/dec`, `Holm p = 0.00083`). Aurangabad / Marathwada (`+0.4157 mm/day/dec` in `JJAS`, `Holm p = 0.01378`) and Nagpur / Central Indian Plateau (`+0.7552 mm/day/dec` in `JJAS`, `Holm p = 0.00132`) also show statistically significant `JJAS` monsoon precipitation increases.
- **Soil Moisture Dynamics:** Root-zone (`GWETROOT`) and profile (`GWETPROF`) soil wetness exhibit modest positive wetting trends across Lucknow (`+0.0225/dec`), Jaisalmer (`+0.0066/dec`), Sundarbans (`+0.0123/dec`), and Ludhiana (`+0.0158/dec`) in the MERRA-2 land-surface model, which must be interpreted alongside GRACE-FO groundwater depletion signals because MERRA-2 soil wetness represents surface/root-zone model state rather than deep confined aquifer storage.
- **Atmospheric Carbon Monoxide (`MOP03JM`):** Over Jan–Mar 2024, `CO_Total_Column` across the India spatial subset averaged `119.57` (range `90.30–179.12`), with elevated loading concentrated over the Indo-Gangetic Plains.

---

## 2. NASA Earth Observation & Contextual Datasets

| Dataset / Mission | Physical Variable | Role in TerraShift India | Key Limitations & Distinctions |
| :--- | :--- | :--- | :--- |
| **NASA POWER / MERRA-2** | `T2M` (°C), `PRECTOTCORR` (mm/day), `GWETROOT`, `GWETPROF`, `QV2M` | Primary 1981–2025 monthly time series (0.5° × 0.625° grid) | Reanalysis/model assimilation, not direct station gauges; coarse 0.5° grid smooths sharp Western Ghats & Himalayan orography. |
| **NASA Terra / MOPITT (`MOP03JM`)** | `CO_Total_Column` | Spatial atmospheric composition subset over India (Jan–Mar 2024) | Thermal-IR + NIR retrievals affected by cloud cover and surface emissivity contrasts. |
| **MODIS (`MOD11C3`, `MOD13C2`)** | LST, NDVI / EVI | Vegetation health & urban/rural heat island discovery (CMR/AppEEARS) | Optical/thermal bands require cloud-masking (`QC` flags); LST ≠ 2m air temperature (`T2M`). |
| **GPM (`3IMERGDF` / `3IMERGM`) & TRMM** | Satellite Precipitation | High-resolution (0.1°) monsoon & extreme rainfall discovery | Post-1998/2014 record length; orographic underestimation in steep Himalayan valleys. |
| **SMAP (`SPL3SMP_E`) & GRACE-FO** | Surface Soil Moisture & Terrestrial Water Storage | Hydrological drought & Indo-Gangetic groundwater context | SMAP senses top ~5 cm only; GRACE-FO has coarse (~300 km) mascon resolution. |
| **IMD & ISRO / MOSDAC** | 4-Season Climatology (`JF`, `MAM`, `JJAS`, `OND`) | Contextual regional & seasonal framing | Reference framework; direct IMD gridded station files require separate institutional access. |

---

## 3. Methodology

1. **India Spatial Masking:** All investigation coordinates are validated against `6.0°N–37.5°N, 68.0°E–97.5°E` (`is_within_india_bounds`), and state/national GeoJSON boundaries (`data/boundaries/states/india_states.geojson`) are rendered on the interactive map.
2. **Quality Control & Gap Integrity:** Fill values (`< -990.0`) are removed without interpolating across long gaps (> 3 consecutive months).
3. **IMD Four-Season Stratification:** Monthly series are aggregated into annual seasonal means for:
   - `JF`: Winter (Jan–Feb)
   - `MAM`: Pre-Monsoon (Mar–May)
   - `JJAS`: Southwest Monsoon (Jun–Sep)
   - `OND`: Post-Monsoon (Oct–Dec)
4. **Statistical Trend & Significance Testing:**
   - **Theil-Sen Slope** (`sens_slope_per_decade`) and **OLS Linear Regression** (`ols_slope_per_decade`, `r_squared`).
   - **Mann-Kendall Non-Parametric Test** (with Hamed-Rao variance correction on full monthly series).
   - **Holm-Bonferroni Correction** across the 4 seasonal tests per site (`significant_holm` at $\alpha = 0.05$) to control family-wise Type I error.
   - **Lag-1 Autocorrelation (`r1`)** reported alongside seasonal metrics.
   - **Annual Anomalies:** Computed relative to the 1991–2020 climatological baseline.

---

## 4. Computed Results Across 12 Indian Benchmark Sites (1981–2025)

| Case & Location | Param | Mean | Overall Sen (/dec) | Overall p | JF Sen (/dec) | MAM Sen (/dec) | JJAS Sen (/dec) | OND Sen (/dec) | Peak Anomaly Year |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| Thrissur / Kerala Coast | `PRECTOTCORR` | 5.9821 | +0.2795* | 0.000017 | +0.0462 | **+0.4826\*** | +0.0788 | +0.4412 | 2007 (+1.904) |
| Aurangabad / Marathwada | `PRECTOTCORR` | 2.1058 | +0.1913* | <0.0001 | -0.0067 | +0.0384 | **+0.4157\*** | +0.0672 | 2006 (+1.201) |
| Leh / Ladakh (W. Himalaya) | `T2M` | -2.8823 | +0.0211 | 0.6271 | -0.3311 | +0.0177 | +0.1695 | +0.1178 | 1998 (+1.316) |
| Chennai / Coromandel Coast | `T2M` | 27.8597 | +0.0534* | 0.0009 | +0.0604 | -0.0364 | +0.0447 | **+0.1802\*** | 2019 (+0.462) |
| Lucknow / Central IGP | `GWETROOT` | 0.4700 | +0.0225* | <0.0001 | +0.0125 | **+0.0033\*** | **+0.0299\*** | **+0.0285\*** | 2008 (+0.121) |
| Jaisalmer / Thar Desert | `GWETROOT` | 0.3205 | +0.0066* | <0.0001 | **+0.0048\*** | **+0.0030\*** | **+0.0107\*** | **+0.0077\*** | 2022 (+0.060) |
| Shillong / Meghalaya | `PRECTOTCORR` | 7.2239 | +1.3238* | <0.0001 | +0.0241 | **+1.6945\*** | **+2.5122\*** | **+0.4372\*** | 2020 (+7.356) |
| Nagpur / Central Plateau | `PRECTOTCORR` | 3.2852 | +0.2003* | <0.0001 | -0.0631 | +0.0507 | **+0.7552\*** | -0.0566 | 1981 (+1.542) |
| Akola / Vidarbha | `T2M` | 26.6009 | -0.0795* | 0.0073 | -0.0011 | +0.0293 | -0.1233 | -0.2572 | 1986 (+0.730) |
| Bhubaneswar / E. Ghats Coast | `T2M` | 26.4626 | -0.0908* | 0.000002 | **-0.4012\*** | -0.1248 | +0.0869 | -0.0414 | 1982 (+0.712) |
| Sundarbans / Bengal Delta | `GWETPROF` | 0.7685 | +0.0123* | <0.0001 | **+0.0087\*** | +0.0038 | **+0.0110\*** | **+0.0222\*** | 2020 (+0.057) |
| Ludhiana / Punjab Basin | `GWETPROF` | 0.3913 | +0.0158* | <0.0001 | **+0.0083\*** | +0.0024 | **+0.0230\*** | **+0.0173\*** | 2023 (+0.102) |

*\* denotes statistical significance at α = 0.05 (Holm-Bonferroni adjusted for seasonal columns; Hamed-Rao / MK for overall series).*

---

## 5. Generated Visualizations

All figures were generated by executing `notebooks/india_environmental_trend_analysis.ipynb`:
- `notebooks/outputs/01_india_temperature_anomalies.png`
- `notebooks/outputs/02_india_seasonal_trends_heatmap.png`
- `notebooks/outputs/03_india_monsoon_soil_moisture.png`
- `notebooks/outputs/04_india_mopitt_co_spatial.png`

---

## 6. Conclusions & Next Scientific Steps

1. **Seasonal Specificity Matters:** Aggregating India's climate into annual means obscures critical seasonal dynamics—such as Chennai's `OND` post-monsoon warming (`+0.1802 °C/dec`) and Thrissur's `MAM` pre-monsoon rainfall increase (`+0.4826 mm/day/dec`)—which are only revealed through IMD 4-season stratification and Holm-Bonferroni correction.
2. **Grid vs. Station Caveat:** Negative or near-zero `T2M` slopes in MERRA-2 grid cells (e.g., Akola, Bhubaneswar winter `JF`) reflect 0.5° reanalysis assimilation and irrigation/aerosol feedbacks; pairing these with high-resolution MODIS `MOD11C3` LST and IMD station records is recommended for urban heat-island and valley-scale studies.
3. **Soil Wetness vs. Groundwater:** Positive `GWETROOT`/`GWETPROF` trends in Punjab (`+0.0158/dec`) reflect surface irrigation and monsoon soil moisture in MERRA-2, whereas deep aquifer depletion requires `GRACE-FO` Terrestrial Water Storage anomaly cross-checking.
