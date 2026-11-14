"""FastAPI router for TerraShift — Earth System Trend Detective."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from stats_engine import analyze_series

app = FastAPI(
    title="TerraShift API",
    description="Earth System Trend Detective — STL decomposition, Mann-Kendall, Sen's slope, and NASA POWER integration.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    timestamps: list[str] = Field(..., description="Monthly YYYY-MM timestamps")
    values: list[float | None] = Field(..., description="Monthly observation values")
    comparison_values: list[float | None] | None = Field(
        default=None, description="Optional comparison region values for teleconnection cross-correlation"
    )
    comparison_timestamps: list[str] | None = Field(
        default=None, description="Optional timestamps for comparison series"
    )
    start_year: int | None = Field(default=None, ge=1981, le=2025)
    end_year: int | None = Field(default=None, ge=1981, le=2025)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Liveness check endpoint."""
    return {"status": "ok", "service": "TerraShift API"}


@app.post("/api/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> dict:
    """Run STL decomposition, Mann-Kendall, Sen's slope, Student's t-test, and horizon analysis."""
    timestamps = req.timestamps
    values = req.values
    comp_values = req.comparison_values
    comp_timestamps = req.comparison_timestamps

    if req.start_year is not None or req.end_year is not None:
        s_yr = req.start_year or 1900
        e_yr = req.end_year or 2100
        if s_yr >= e_yr:
            raise HTTPException(status_code=400, detail="start_year must be less than end_year.")
        filtered = [
            (ts, val, comp_values[i] if comp_values and i < len(comp_values) else None)
            for i, (ts, val) in enumerate(zip(timestamps, values))
            if s_yr <= int(ts[:4]) <= e_yr
        ]
        timestamps = [row[0] for row in filtered]
        values = [row[1] for row in filtered]
        if comp_values is not None:
            comp_values = [row[2] for row in filtered]
            comp_timestamps = timestamps

    try:
        return analyze_series(
            timestamps=timestamps,
            values=values,
            comparison_values=comp_values,
            comparison_timestamps=comp_timestamps,
            mk_variant=req.mk_variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
