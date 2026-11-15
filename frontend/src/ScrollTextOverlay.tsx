import React, { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Sparkles } from "lucide-react";

interface ScrollTextOverlayProps {
  onExplore?: () => void;
}

export const ScrollTextOverlay: React.FC<ScrollTextOverlayProps> = ({ onExplore }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0); // 0 (top of viewport) to 1 (scrolled through)

  useEffect(() => {
    let ticking = false;

    const handleScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          if (containerRef.current) {
            const rect = containerRef.current.getBoundingClientRect();
            const windowHeight = window.innerHeight;
            
            // Calculate progress through viewport:
            // when top enters bottom: rect.top = windowHeight -> 0
            // when bottom leaves top: rect.bottom = 0 -> 1
            const totalDistance = windowHeight + rect.height;
            const currentDistance = windowHeight - rect.top;
            const clamped = Math.max(0, Math.min(1, currentDistance / totalDistance));
            setProgress(clamped);
          }
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll, { passive: true });
    handleScroll();

    return () => {
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
    };
  }, []);

  // Centered progress (-0.5 to 0.5 where 0 is when the component is vertically centered)
  const centeredProgress = progress - 0.5;

  // Background drift at 0.5x speed:
  // Drift horizontally and softly vertically
  const bgDriftX1 = centeredProgress * 120; // 0.5x horizontal drift
  const bgDriftX2 = -centeredProgress * 140;
  const bgDriftY = centeredProgress * 50; // soft vertical drift

  // Foreground scale smoothly from 0.9x to 1.1x:
  // progress goes 0 -> 1, so 0.9 + 0.2 * progress
  const foregroundScale = 0.9 + 0.2 * progress;

  // Soft vertical parallax float for foreground:
  // moves in subtle counter-balance for depth
  const fgParallaxY = -centeredProgress * 38;

  return (
    <section 
      ref={containerRef} 
      className="scroll-overlay-section" 
      aria-label="Scroll-driven signal observatory experiment"
    >
      <div className="scroll-overlay-backdrop" aria-hidden="true">
        {/* Row 1: drifting background words */}
        <div 
          className="scroll-bg-row scroll-bg-row-top"
          style={{
            transform: `translate3d(${bgDriftX1}px, ${bgDriftY}px, 0)`,
          }}
        >
          <span>MONSOON DYNAMICS</span>
          <span>•</span>
          <span>MODIS NDVI</span>
          <span>•</span>
          <span>GPM PRECIPITATION</span>
          <span>•</span>
          <span>HIMALAYAN CRYOSPHERE</span>
        </div>

        {/* Row 2: drifting background words in counter-direction */}
        <div 
          className="scroll-bg-row scroll-bg-row-bottom"
          style={{
            transform: `translate3d(${bgDriftX2}px, ${-bgDriftY * 0.8}px, 0)`,
          }}
        >
          <span>TROPOSPHERIC OMI NO2</span>
          <span>•</span>
          <span>NASA EARTHDATA</span>
          <span>•</span>
          <span>SEN SEN'S SLOPE</span>
          <span>•</span>
          <span>BENJAMINI-HOCHBERG FDR</span>
        </div>

        <div className="scroll-overlay-glow" />
      </div>

      <div 
        className="scroll-fg-card"
        style={{
          transform: `translate3d(0, ${fgParallaxY}px, 0) scale(${foregroundScale})`,
        }}
      >
        <div className="scroll-card-badge">
          <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
          <span>EXPERIMENTAL SCROLL-DRIVEN OVERLAY</span>
        </div>

        <h2 className="scroll-fg-title">
          Watch Earth Systems <br />
          <span className="scroll-fg-gradient">Unfold In Real Time</span>
        </h2>

        <p className="scroll-fg-desc">
          Continuous planetary sensing across 36 Indian states and union territories.
          Background satellite streams drift at orbital velocities while foreground climate signals align to your gaze.
        </p>

        {onExplore && (
          <button 
            type="button" 
            className="button button-primary scroll-fg-button"
            onClick={onExplore}
          >
            Explore live parameters
            <ArrowUpRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </section>
  );
};
