import {
  Activity,
  ArrowUpRight,
  BarChart3,
  ChevronRight,
  Crosshair,
  Database,
  Globe2,
  Orbit,
  Radar,
  Satellite,
  ShieldCheck,
  Target,
} from "lucide-react";
import type { InvestigateResponse, PresetCaseMeta } from "./types";

export type NavSection =
  | "home"
  | "explore"
  | "india"
  | "acquisition"
  | "analysis"
  | "results"
  | "about"
  | "help";

interface HomePageProps {
  cases: PresetCaseMeta[];
  activeInvestigation: InvestigateResponse | null;
  onNavigate: (section: NavSection) => void;
  onSelectCaseAndExplore: (caseId: string, targetSection: NavSection) => void;
  onStartDemo?: () => void;
}

const signalCards = [
  {
    index: "01",
    icon: Crosshair,
    title: "Locate the Indian signal",
    description: "Drop a marker across India's 10 physiographic regions (6.0°N–37.5°N, 68.0°E–97.5°E) and choose a variable.",
  },
  {
    index: "02",
    icon: Activity,
    title: "Separate the noise",
    description: "Remove seasonal cycles so the long-term movement becomes impossible to miss.",
  },
  {
    index: "03",
    icon: ShieldCheck,
    title: "Verify the shift",
    description: "Use robust statistical tests and uncertainty intervals before drawing a conclusion.",
  },
];

const nasaImages = [
  {
    src: "/images/nasa/pia11066.jpg",
    alt: "Curved Earth limb and clouds photographed from orbit",
    title: "The orbital horizon",
    credit: "NASA / PIA11066",
  },
  {
    src: "/images/nasa/iss045e013851.jpg",
    alt: "Night-side Earth observation from the International Space Station",
    title: "Observation at night",
    credit: "NASA / ISS045-E-013851",
  },
  {
    src: "/images/nasa/sl4-143-4707.jpg",
    alt: "Skylab space station cluster above a cloud-covered Earth",
    title: "Infrastructure in orbit",
    credit: "NASA / SL4-143-4707",
  },
];

export default function HomePage({
  cases,
  activeInvestigation,
  onNavigate,
  onSelectCaseAndExplore,
  onStartDemo,
}: HomePageProps) {
  const featuredCases = cases.slice(0, 4);
  const activeStats = activeInvestigation?.response.primary_stats;
  const activeMeta = activeInvestigation?.response.metadata;
  const activePoint = activeInvestigation?.request.primary_point;

  return (
    <div className="home-page">
      <section className="home-hero">
        <img
          className="hero-nasa-image"
          src="/images/nasa/pia11066.jpg"
          alt="Earth's cloud-covered horizon photographed from orbit"
        />
        <div className="hero-grid" aria-hidden="true" />
        <div className="hero-orbit hero-orbit-one" aria-hidden="true" />
        <div className="hero-orbit hero-orbit-two" aria-hidden="true" />
        <div className="hero-glow hero-glow-one" aria-hidden="true" />
        <div className="hero-glow hero-glow-two" aria-hidden="true" />

        <div className="hero-copy">
          <div className="eyebrow eyebrow-light hero-anim-eyebrow">
            <span className="eyebrow-mark" />
            India Orbital Observatory / 01
          </div>
          <h1 className="hero-anim-title">
            Read India&apos;s signal
            <br />
            <span>before it moves.</span>
          </h1>
          <p className="hero-lede hero-anim-lede">
            TerraShift turns long-running NASA Earth observation over India into a clear, defensible
            view of monsoon, Himalayan, and soil-moisture trends.
          </p>
          <div className="hero-actions hero-anim-actions">
            <button type="button" className="button button-primary" onClick={() => onNavigate("explore")}>
              Begin an investigation
              <ArrowUpRight className="h-4 w-4" />
            </button>
            {onStartDemo && (
              <button type="button" className="button button-quiet" onClick={onStartDemo}>
                Start demo
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
            <button type="button" className="button button-quiet" onClick={() => onNavigate("about")}>
              How the science works
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <div className="hero-proof hero-anim-proof">
            <div className="proof-item">
              <span className="proof-value">{activeStats?.observation_years ? `${activeStats.observation_years.toFixed(0)}+` : "LIVE"}</span>
              <span className="proof-label">{activeStats ? "years in view" : "NASA data path"}</span>
            </div>
            <div className="proof-rule" />
            <div className="proof-item">
              <span className="proof-value">{cases.length ? String(cases.length).padStart(2, "0") : "—"}</span>
              <span className="proof-label">open case files</span>
            </div>
            <div className="proof-rule" />
            <div className="proof-item">
              <span className="proof-value">STL</span>
              <span className="proof-label">seasonality removed</span>
            </div>
          </div>
        </div>

        <div className="hero-instrument hero-anim-instrument" aria-label="Live investigation summary">
          <div className="instrument-header">
            <div className="instrument-label">
              <Radar className="h-4 w-4" />
              Live signal monitor
            </div>
            <span className="instrument-status">
              <span className="status-dot" />
              {activeInvestigation ? "connected" : "standby"}
            </span>
          </div>
          <div className="instrument-visual">
            <div className="instrument-earth" aria-hidden="true">
              <div className="earth-land earth-land-one" />
              <div className="earth-land earth-land-two" />
              <div className="earth-land earth-land-three" />
              <span className="earth-point" />
              <span className="earth-scan" />
            </div>
            <div className="instrument-readout instrument-readout-top">
              <span>ORBITAL FEED</span>
              <strong>NASA / MERRA-2</strong>
            </div>
            <div className="instrument-readout instrument-readout-bottom">
              <span>LAT / LONG</span>
              <strong>{activePoint ? `${activePoint.lat.toFixed(2)}° / ${activePoint.lon.toFixed(2)}°` : "28.61° / 77.21°"}</strong>
            </div>
          </div>
          <div className="instrument-data">
            <div>
              <span className="data-label">Current focus</span>
              <strong>{activePoint?.name ?? "New Delhi, India"}</strong>
            </div>
            <div>
              <span className="data-label">Variable</span>
              <strong>{activeMeta?.parameter_name ?? "Surface temperature"}</strong>
            </div>
            <div className="instrument-divider" />
            <div className="instrument-trend">
              <span className="data-label">Trend direction</span>
              <strong className={activeStats?.is_significant ? "trend-positive" : "trend-neutral"}>
                {activeStats
                  ? activeStats.sens_slope_per_year >= 0
                    ? "Rising signal"
                    : "Falling signal"
                  : "Awaiting signal"}
              </strong>
            </div>
          </div>
          <button type="button" className="instrument-link" onClick={() => onNavigate("analysis")}>
            Open active chart <ArrowUpRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </section>

      <section className="nasa-archive" aria-labelledby="nasa-archive-title">
        <div className="nasa-archive-heading">
          <div className="section-index">02 / Orbital archive</div>
          <div>
            <p className="eyebrow">NASA imagery / public domain source</p>
            <h2 id="nasa-archive-title">The view is part of the evidence.</h2>
            <p>
              TerraShift works from Earth observation records. These NASA archive images ground the
              interface in the same orbital perspective without standing in for computed results.
            </p>
          </div>
        </div>
        <div className="nasa-archive-grid">
          {nasaImages.map((image) => (
            <figure className="nasa-image-card" key={image.src}>
              <div className="nasa-image-frame">
                <img src={image.src} alt={image.alt} loading="lazy" />
              </div>
              <figcaption>
                <strong>{image.title}</strong>
                <span>{image.credit}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="home-intro section-grid">
        <div className="section-index">03 / The mission</div>
        <div className="intro-content">
          <p className="eyebrow">From raw observation to clear direction</p>
          <h2>
            The planet is always
            <br />
            <em>sending a signal.</em>
          </h2>
          <p className="intro-body">
            Seasonal swings, weather events, and noisy measurements can hide the slow changes that
            matter most. TerraShift gives researchers, students, and decision-makers a rigorous
            starting point for finding those changes and understanding their confidence.
          </p>
          <button type="button" className="text-link" onClick={() => onNavigate("help")}>
            Read the field guide <ArrowUpRight className="h-4 w-4" />
          </button>
        </div>
        <div className="intro-orbit-card">
          <Orbit className="h-6 w-6" />
          <span className="orbit-card-label">Mission readout</span>
          <div className="orbit-lines" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <strong>Make the orbital record legible.</strong>
        </div>
      </section>

      <section className="home-process">
        <div className="process-heading section-grid">
          <div className="section-index">04 / The method</div>
          <div>
            <p className="eyebrow">A disciplined path to evidence</p>
            <h2>Every investigation starts with a better question.</h2>
          </div>
        </div>
        <div className="process-grid">
          {signalCards.map((card) => {
            const Icon = card.icon;
            return (
              <article className="process-card" key={card.index}>
                <div className="process-card-top">
                  <span>{card.index}</span>
                  <Icon className="h-5 w-5" />
                </div>
                <h3>{card.title}</h3>
                <p>{card.description}</p>
                <span className="process-card-line" />
              </article>
            );
          })}
        </div>
      </section>

      {featuredCases.length > 0 && (
        <section className="home-cases">
          <div className="cases-heading section-grid">
            <div className="section-index">05 / Open case files</div>
            <div className="cases-heading-content">
              <div>
                <p className="eyebrow">Start from a known signal</p>
                <h2>Questions worth zooming in on.</h2>
              </div>
              <button type="button" className="text-link" onClick={() => onNavigate("explore")}>
                Explore all variables <ArrowUpRight className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="case-grid">
            {featuredCases.map((caseFile, index) => (
              <article className="case-card" key={caseFile.case_id}>
                <div className={`case-card-art case-art-${index + 1}`} aria-hidden="true">
                  <span className="case-art-grid" />
                  <span className="case-art-signal" />
                </div>
                <div className="case-card-content">
                  <div className="case-card-meta">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <span>{caseFile.parameter_name}</span>
                  </div>
                  <h3>{caseFile.title}</h3>
                  <p>{caseFile.mechanism_teaser}</p>
                  <div className="case-card-actions">
                    <button type="button" className="case-card-link" onClick={() => onSelectCaseAndExplore(caseFile.case_id, "analysis")}>
                      View signal <ArrowUpRight className="h-3.5 w-3.5" />
                    </button>
                    <span>{caseFile.default_window[0]}–{caseFile.default_window[1]}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="home-cta">
        <div className="cta-stars" aria-hidden="true" />
        <div className="cta-copy">
          <div className="eyebrow eyebrow-light">
            <span className="eyebrow-mark" />
            Your next observation
          </div>
          <h2>Look closer. Decide earlier.</h2>
          <p>Choose a place, choose a variable, and let the evidence lead the way.</p>
        </div>
        <div className="cta-actions">
          <button type="button" className="button button-primary" onClick={() => onNavigate("explore")}>
            Launch an investigation
            <ArrowUpRight className="h-4 w-4" />
          </button>
          <div className="cta-utility">
            <Satellite className="h-4 w-4" />
            <span>Powered by NASA Earth observation data</span>
          </div>
        </div>
      </section>

      <section className="home-footer-signals" aria-label="TerraShift platform capabilities">
        <div className="footer-signal">
          <Globe2 className="h-4 w-4" />
          <span>All-India coverage</span>
        </div>
        <div className="footer-signal">
          <Database className="h-4 w-4" />
          <span>Open scientific sources</span>
        </div>
        <div className="footer-signal">
          <BarChart3 className="h-4 w-4" />
          <span>Transparent statistics</span>
        </div>
        <div className="footer-signal">
          <Target className="h-4 w-4" />
          <span>Decision-ready evidence</span>
        </div>
      </section>
    </div>
  );
}
