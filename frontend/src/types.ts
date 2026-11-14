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

export interface SeriesStats {
  mann_kendall_tau: number;
  z_score: number;
  p_value: number;
  t_test_p_value: number;
  raw_p_value: number;
  is_significant: boolean;
  sens_slope_per_year: number;
  sens_slope_per_decade: number;
  ols_slope_per_year: number;
  years_to_significance: number;
  variance_reduction_pct: number;
  seasonal_amplitude: number;
  observation_months: number;
  observation_years: number;
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
    data_status: "live" | "cache" | "offline_fallback";
    fallback_note: string | null;
    primary_bounding_box: BoundingBox;
    comparison_bounding_box: BoundingBox | null;
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
