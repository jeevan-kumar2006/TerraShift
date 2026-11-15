export interface GeoPoint {
  name: string;
  lat: number;
  lon: number;
}

export interface BoundingBox {
  south: number;
  north: number;
  west: number;
  east: number;
}

export interface ParameterMeta {
  parameter_code: string;
  parameter_name: string;
  unit: string;
  mission_source: string;
  collection?: string;
  data_type?: string;
  temporal_resolution?: string;
  resolution: string;
  plain_definition: string;
  question: string;
  positive_label: string;
  negative_label: string;
}

export interface PresetCaseMeta {
  case_id: string;
  title: string;
  short_title: string;
  mechanism_teaser: string;
  parameter: string;
  parameter_name: string;
  unit: string;
  mission_label: string;
  primary_point: GeoPoint;
  comparison_point: GeoPoint | null;
  default_window: [number, number];
  data_source: string;
  cached: boolean;
}

export interface AnalyzedSeries {
  timestamps: string[];
  raw_values: (number | null)[];
  seasonal_cycle: (number | null)[];
  deseasonalized_anomalies: (number | null)[];
  trend_line: (number | null)[];
  ci_upper: (number | null)[];
  ci_lower: (number | null)[];
}

export interface SeriesProvenance {
  source_name: string;
  collection: string;
  parameter: string;
  data_type: string;
  dataset_tag: "live" | "cached" | "imported" | "synthetic" | "offline_fallback" | string;
  units: string;
  temporal_resolution: string;
  spatial_resolution: string;
  requested_lat: number;
  requested_lon: number;
  source_lat: number;
  source_lon: number;
  bounding_box: BoundingBox;
  start_date: string;
  end_date: string;
  retrieval_status: string;
  fallback_distance_km: number;
  access_url?: string | null;
  provenance_note?: string;
}

export interface SeriesStats {
  mann_kendall_s?: number;
  mann_kendall_tau: number;
  z_score: number;
  p_value: number;
  t_statistic?: number;
  degrees_of_freedom?: number;
  t_test_p_value: number;
  raw_p_value: number;
  is_significant: boolean;
  sens_slope_per_year: number;
  sens_slope_per_decade: number;
  sens_slope_ci_lower?: number;
  sens_slope_ci_upper?: number;
  ols_slope_per_year: number;
  ols_slope_per_decade?: number;
  ols_intercept?: number;
  lag1_autocorrelation?: number;
  autocorrelation_significant?: boolean;
  outlier_count?: number;
  years_to_significance: number;
  estimated_additional_observation_years?: number;
  variance_reduction_pct: number;
  seasonal_amplitude: number;
  observation_months: number;
  observation_years: number;
  valid_months?: number;
  missing_months?: number;
  missing_pct?: number;
  interpolated_months?: number;
  max_consecutive_missing?: number;
  duplicate_timestamps_merged?: number;
  ci_methodology?: string;
  horizon_assumptions?: string;
  mk_variant: string;
}

export interface TeleconnectionSummary {
  enabled: boolean;
  comparison_anomalies: (number | null)[];
  comparison_sens_slope_per_year: number | null;
  comparison_sens_slope_per_decade: number | null;
  comparison_is_significant: boolean;
  comparison_p_value: number | null;
  cross_correlation_r: number | null;
  cross_correlation_p_value: number | null;
}

export interface DetectiveBrief {
  verdict_headline: string;
  physical_mechanism: string;
  seasonality_note: string;
  horizon_note: string;
  reference: string;
  biome_zone: string;
  ai_enhanced: boolean;
  methodology_note?: string;
  limitations_note?: string;
}

export interface InvestigateRequestPayload {
  case_id: string | null;
  parameter: string;
  primary_point: GeoPoint;
  comparison_point: GeoPoint | null;
  start_year: number;
  end_year: number;
  mk_variant: "standard" | "hamed_rao";
}

export interface ImportSeriesRequestPayload {
  raw_text: string;
  source_hint?: string;
  region_name?: string;
  lat?: number;
  lon?: number;
  unit?: string | null;
  mk_variant?: "standard" | "hamed_rao";
  start_year?: number | null;
  end_year?: number | null;
}

export interface InvestigateResponse {
  request: InvestigateRequestPayload;
  response: {
    metadata: ParameterMeta;
    data_status: "live" | "cache" | "offline_fallback" | "imported" | "synthetic";
    dataset_tag?: "live" | "cached" | "imported" | "synthetic" | "offline_fallback" | string;
    fallback_note: string | null;
    primary_bounding_box: BoundingBox;
    comparison_bounding_box: BoundingBox | null;
    primary_provenance?: SeriesProvenance | null;
    comparison_provenance?: SeriesProvenance | null;
    primary_series: AnalyzedSeries;
    primary_stats: SeriesStats;
    comparison_series: AnalyzedSeries | null;
    comparison_stats: SeriesStats | null;
    teleconnection: TeleconnectionSummary;
    detective_brief: DetectiveBrief;
  };
}

export interface PartnerDeepLink {
  id: string;
  agency: string;
  title: string;
  category: string;
  description: string;
  url: string;
}

export interface CmrCollection {
  short_name: string;
  title: string;
  data_center: string;
  summary: string;
}

export interface AppeearsProduct {
  product_id: string;
  platform: string;
  description: string;
  resolution: string;
}

export interface CsaStation {
  type: string;
  station_name: string;
  station_id: string;
  province: string;
  sample_date: string;
  sample_metric: string;
}

export interface PartnerIntelResponse {
  coordinates: { lat: number; lon: number; bounding_box: BoundingBox };
  cmr_collections: CmrCollection[];
  appeears_products: AppeearsProduct[];
  csa_geomet_stations: CsaStation[];
  noaa_cdo_status: string;
  deep_links: PartnerDeepLink[];
}

export interface ApiHealthResponse {
  status: string;
  service: string;
  version: string;
  cache_available: boolean;
  timestamp?: string;
}

export interface ApiStatusResponse {
  status: string;
  service: string;
  version: string;
  cache_available: boolean;
  cases_count: number;
  live_cache_count: number;
  parameters: string[];
  environment: string;
}

export interface ApiErrorDetail {
  loc?: (string | number)[];
  msg: string;
  type?: string;
}

export interface ApiErrorResponse {
  detail: string | ApiErrorDetail[];
  error?: boolean;
  error_type?: string;
  status_code?: number;
}

export type AcquisitionDomain = "atmospheric" | "climate" | "hydrology" | "vegetation";

export interface AcquisitionVariableSpec {
  variable_code: string;
  variable_name: string;
  domain: AcquisitionDomain;
  primary_dataset_id: string;
  secondary_dataset_ids: string[];
  scientific_justification: string;
  physical_distinction_note: string;
  canonical_units: string;
}

export interface AcquisitionCatalogEntry {
  dataset_id: string;
  dataset_name: string;
  scientific_variable: string;
  variable_code: string;
  domain: AcquisitionDomain;
  collection_concept_id: string | null;
  product_version: string;
  data_provider: string;
  variable_names: string[];
  units: string;
  spatial_resolution: string;
  temporal_resolution: string;
  first_available_date: string;
  last_available_date: string;
  geographic_coverage: string;
  file_format: string;
  quality_flags: string[];
  authentication_required: boolean;
  auth_provider: string;
  download_mechanism: string;
  supports_spatial_subset: boolean;
  supports_temporal_subset: boolean;
  official_docs_url: string;
  data_limitations: string;
  scientific_justification: string;
}

export interface AcquisitionMatrixRow {
  variable_code: string;
  variable_name: string;
  domain: AcquisitionDomain;
  primary_dataset: string;
  primary_provider: string;
  auth_required: boolean;
  supports_spatial_subset: boolean;
  canonical_units: string;
  physical_distinction_note: string;
}

export interface AcquisitionAuthStatus {
  earthdata_authenticated: boolean;
  earthdata_method: string;
  netrc_present: boolean;
  earthaccess_available: boolean;
  copernicus_configured: boolean;
  copernicus_method: string;
  appeears_ready: boolean;
  missing_credentials: string[];
  setup_instructions: string[];
}

export interface AcquisitionRegion {
  region_id: string;
  name: string;
  zone: string;
  level: string;
  vertex_count: number;
  bbox: [number, number, number, number];
}

export interface AcquisitionGranule {
  granule_id: string;
  title: string;
  collection_concept_id: string;
  time_start: string | null;
  time_end: string | null;
  size_mb: number | null;
  download_url: string | null;
  opendap_url: string | null;
}

export interface AcquisitionValidationReport {
  file_path: string;
  file_format: string;
  file_size_bytes: number;
  passed: boolean;
  dimensions: Record<string, number>;
  variables: string[];
  units: Record<string, string>;
  duplicate_timestamps_count: number;
  missing_timestamps_count: number;
  missing_value_pct: number;
  quality_flags_detected: string[];
  errors: string[];
  warnings: string[];
}

export interface AcquisitionQCReport {
  dataset_id: string;
  qc_profile: string;
  raw_file_path: string;
  validated_file_path: string | null;
  total_observations: number;
  valid_after_qc: number;
  filtered_fill_count: number;
  filtered_out_of_range_count: number;
  filtered_qc_flag_count: number;
  applied_filters: string[];
  units_verified: string | null;
  passed: boolean;
}

export interface AcquisitionSpatialSubset {
  region_id: string;
  region_name: string;
  region_level: string;
  boundary_file: string;
  polygon_vertex_count: number;
  grid_cells_total: number;
  grid_cells_inside_mask: number;
  original_resolution_preserved: boolean;
  weighting_method: string;
  output_file: string;
  variable_name: string;
  units: string;
  regional_mean: number | null;
  regional_min: number | null;
  regional_max: number | null;
  valid_fraction: number;
  time_series: { timestamp: string; area_weighted_mean: number | null }[];
}

export interface AcquisitionDownloadResponse {
  status: string;
  dataset_id: string;
  retrieval_mode?: string;
  auth_required?: boolean;
  message?: string;
  estimated_months?: number;
  estimated_granules?: number;
  estimated_size_mb?: number;
  cmr_granules_discovered?: number;
  granules?: AcquisitionGranule[];
  validation?: AcquisitionValidationReport;
  qc?: AcquisitionQCReport;
  spatial_subset?: AcquisitionSpatialSubset | null;
  pilot_inspection?: {
    retrieval_mode: string;
    validation: AcquisitionValidationReport;
    qc: AcquisitionQCReport;
    spatial_subset: AcquisitionSpatialSubset | null;
  } | null;
}

export interface AcquisitionManifestData {
  manifest: Record<string, string>[];
  validations: Record<string, string>[];
  storage: Record<string, unknown>;
}

export interface IndiaBounds {
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
}

export interface IndiaSeasonSpec {
  code: string;
  name: string;
  months: number[];
  description: string;
}

export interface IndiaPhysiographicRegion {
  id: string;
  name: string;
  lat: number;
  lon: number;
  focus: string;
}

export interface IndiaRegionsResponse {
  bounds: IndiaBounds;
  seasons: Record<string, IndiaSeasonSpec>;
  physiographic_regions: IndiaPhysiographicRegion[];
}

export interface IndiaSeasonResult {
  name: string;
  months: number[];
  n_years: number;
  mean_value: number | null;
  std_value: number | null;
  ols_slope_per_decade: number | null;
  ols_p_value: number | null;
  r_squared: number | null;
  sen_slope_per_decade: number | null;
  mk_tau: number | null;
  mk_p_value: number | null;
  holm_adjusted_p: number | null;
  significant_holm: boolean;
  lag1_autocorr: number | null;
  direction: string;
}

export interface IndiaSeasonalAnalysisResponse {
  meta: {
    case_id?: string;
    case_title?: string;
    location?: string;
    lat?: number;
    lon?: number;
    parameter: string;
    units?: string;
    source_mode?: string;
  };
  analysis: {
    eda: {
      n_total: number;
      n_valid: number;
      missing_pct: number;
      mean: number | null;
      std: number | null;
      min: number | null;
      max: number | null;
      start_year: number | null;
      end_year: number | null;
    };
    baseline_period: string;
    seasons: Record<string, IndiaSeasonResult>;
    annual_anomalies: {
      year: number;
      annual_mean: number;
      anomaly: number;
      z_score: number | null;
    }[];
    top_positive_years: { year: number; anomaly: number; annual_mean: number }[];
    top_negative_years: { year: number; anomaly: number; annual_mean: number }[];
    warnings?: string[];
  };
}

export interface IndiaRegionalComparisonRow {
  case_id: string;
  case_title: string;
  role: "primary" | "compare";
  location: string;
  lat: number;
  lon: number;
  parameter: string;
  units: string;
  source_mode: string;
  n_months: number;
  mean_value: number | null;
  std_value: number | null;
  sen_slope_per_decade: number | null;
  mk_p_value: number | null;
  mk_significant: boolean | null;
  seasons: Record<
    string,
    {
      name: string;
      sen_slope_per_decade: number | null;
      ols_slope_per_decade: number | null;
      mk_p_value: number | null;
      holm_adjusted_p: number | null;
      significant_holm: boolean;
    }
  >;
}

export interface IndiaRegionalComparisonResponse {
  start_year: number;
  end_year: number;
  baseline_period: string;
  count: number;
  rows: IndiaRegionalComparisonRow[];
}
