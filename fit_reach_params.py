#!/usr/bin/env python3
"""
Reach Parameter Estimator
=========================
Reads a CSV of observed (impressions, reach) data points per channel and fits
the logistic S-curve parameters Mid-point (mu) and Spread (sigma) for each.

These parameters can then be set directly in Reach Optimisation's
reach_midpoint_parameter and reach_spread_parameter channel fields,
replacing the current trial-and-error process.

Usage:
    python fit_reach_params.py reach_parameter_template.csv
    python fit_reach_params.py reach_parameter_template.csv --output results.csv
    python fit_reach_params.py reach_parameter_template.csv --output results.csv --plot

Requirements:
    pip install numpy pandas scipy matplotlib
"""

import argparse
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.optimize import OptimizeWarning

warnings.filterwarnings("ignore", category=OptimizeWarning)


# ---------------------------------------------------------------------------
# Sigmoid model
# ---------------------------------------------------------------------------

def logistic_reach(impression_density: np.ndarray, k: float, mu: float, sigma: float) -> np.ndarray:
    """
    Logistic S-curve reach model with capacity parameter.

    impression_density : impressions_delivered / total_addressable_adults
    k                  : capacity — maximum reachable fraction of the total
                         addressable universe (0.0 – 1.0). Captures that
                         channels like ATV can only ever reach a sub-set of
                         the total adult population regardless of spend.
    mu                 : midpoint — the impression density at which 50% of
                         the *reachable* audience (k) is reached
    sigma              : spread — controls the steepness of the S-curve

    Returns reach as a fraction of total_addressable_adults (0.0 – 1.0).
    """
    return k / (1.0 + np.exp(-(impression_density - mu) / sigma))


# ---------------------------------------------------------------------------
# Per-channel type sensible parameter bounds and initial guesses
# ---------------------------------------------------------------------------

# p0 = [k, mu, sigma]  |  bounds = ([k_min, mu_min, sigma_min], [k_max, mu_max, sigma_max])
# k bounds: (0, 1] — ATV/DOOH typically saturate well below 50% of total adults
CHANNEL_DEFAULTS = {
    "ATV":     {"p0": [0.20, 0.40, 0.20], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 5.0])},
    "CTV":     {"p0": [0.25, 0.45, 0.25], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 5.0])},
    "Video":   {"p0": [0.50, 0.60, 0.30], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 8.0])},
    "Audio":   {"p0": [0.30, 0.45, 0.20], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 5.0])},
    "DOOH":    {"p0": [0.30, 0.62, 0.30], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 8.0])},
    "Display": {"p0": [0.60, 0.75, 0.40], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 10.0])},
}
GENERIC_DEFAULTS = {"p0": [0.40, 0.50, 0.25], "bounds": ([0.01, 0.01, 0.01], [1.0, 2.0, 10.0])}


# ---------------------------------------------------------------------------
# Fit result
# ---------------------------------------------------------------------------

@dataclass
class FitResult:
    channel_name: str
    channel_type: str
    k: float | None
    mu: float | None
    sigma: float | None
    k_std_err: float | None
    mu_std_err: float | None
    sigma_std_err: float | None
    r_squared: float | None
    data_points: int
    confidence: str
    warning: str


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 1.0


def fit_channel(
    channel_name: str,
    channel_type: str,
    group: pd.DataFrame,
) -> FitResult:
    n = len(group)
    base = FitResult(
        channel_name=channel_name,
        channel_type=channel_type,
        k=None,
        mu=None,
        sigma=None,
        k_std_err=None,
        mu_std_err=None,
        sigma_std_err=None,
        r_squared=None,
        data_points=n,
        confidence="Insufficient data",
        warning="",
    )

    if n < 3:
        base.warning = "Need at least 3 data points for the 3-parameter model — skipped" if n < 2 else "Need at least 3 data points for the 3-parameter model — skipped"
        return base

    x = (group["impressions_delivered"] / group["total_addressable_adults"]).values
    y = (group["reach_adults"] / group["total_addressable_adults"]).values

    # Clamp y to [0, 1] — protect against data entry errors
    y = np.clip(y, 0.0, 1.0)

    defaults = CHANNEL_DEFAULTS.get(channel_type, GENERIC_DEFAULTS)

    # Seed k initial guess from the data: use observed max reach fraction
    p0 = list(defaults["p0"])
    p0[0] = min(float(np.max(y)) * 1.2, 1.0)

    try:
        (k, mu, sigma), cov = curve_fit(
            logistic_reach,
            x,
            y,
            p0=p0,
            bounds=defaults["bounds"],
            maxfev=20000,
        )
    except RuntimeError:
        base.warning = "Curve fitting did not converge — try adding more data points at varied impression levels"
        return base
    except Exception as exc:
        base.warning = f"Fitting error: {exc}"
        return base

    y_pred = logistic_reach(x, k, mu, sigma)
    r2 = _r_squared(y, y_pred)
    perr = np.sqrt(np.diag(cov))

    if n < 5:
        confidence = "Low (few points — provisional, add more data)"
    elif n < 8:
        confidence = "Medium"
    else:
        confidence = "High"

    warnings_list = []
    if r2 < 0.90:
        warnings_list.append(f"R²={r2:.3f} is below 0.90 — the logistic model may not fit this data well")
    if perr[0] > 0.10:
        warnings_list.append("k (capacity) standard error is large — more data points would improve precision")
    if perr[1] > 0.15:
        warnings_list.append("mu standard error is large — more data points would improve precision")
    if perr[2] > 0.50:
        warnings_list.append("sigma standard error is large — more data points would improve precision")

    return FitResult(
        channel_name=channel_name,
        channel_type=channel_type,
        k=round(float(k), 4),
        mu=round(float(mu), 4),
        sigma=round(float(sigma), 4),
        k_std_err=round(float(perr[0]), 4),
        mu_std_err=round(float(perr[1]), 4),
        sigma_std_err=round(float(perr[2]), 4),
        r_squared=round(r2, 4),
        data_points=n,
        confidence=confidence,
        warning="; ".join(warnings_list),
    )


# ---------------------------------------------------------------------------
# CSV loading and validation
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "channel_name",
    "channel_type",
    "total_addressable_adults",
    "impressions_delivered",
    "reach_adults",
]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#")
    df.columns = df.columns.str.strip()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"ERROR: CSV is missing required columns: {', '.join(missing)}", file=sys.stderr)
        print(f"Required columns: {', '.join(REQUIRED_COLUMNS)}", file=sys.stderr)
        sys.exit(1)

    for col in ["total_addressable_adults", "impressions_delivered", "reach_adults"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    invalid = df[df[["total_addressable_adults", "impressions_delivered", "reach_adults"]].isna().any(axis=1)]
    if not invalid.empty:
        print(f"WARNING: {len(invalid)} row(s) have non-numeric values and will be skipped:")
        print(invalid[["channel_name"] + REQUIRED_COLUMNS[2:]].to_string(index=False))

    df = df.dropna(subset=["total_addressable_adults", "impressions_delivered", "reach_adults"])
    df = df[df["total_addressable_adults"] > 0]
    df = df[df["impressions_delivered"] >= 0]
    df = df[df["reach_adults"] >= 0]

    return df


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_results(results: list[FitResult]) -> None:
    print()
    print("=" * 80)
    print("  REACH PARAMETER ESTIMATION RESULTS")
    print("=" * 80)

    succeeded = [r for r in results if r.mu is not None]
    skipped = [r for r in results if r.mu is None]

    if succeeded:
        print()
        print("  FITTED PARAMETERS")
        print("  " + "-" * 82)
        print(f"  {'Channel':<28} {'Type':<10} {'k (cap)':>8} {'mu':>7} {'sigma':>7} {'R²':>7} {'Confidence'}")
        print("  " + "-" * 82)
        for r in succeeded:
            flag = " !" if r.warning else ""
            print(
                f"  {r.channel_name:<28} {r.channel_type:<10}"
                f" {r.k:>8.4f} {r.mu:>7.4f} {r.sigma:>7.4f} {r.r_squared:>7.4f}"
                f"  {r.confidence}{flag}"
            )
        print()
        print("  (!) = warnings present — see details below")

        for r in succeeded:
            if r.warning:
                print()
                print(f"  WARNING — {r.channel_name}:")
                for w in r.warning.split(";"):
                    print(f"    • {w.strip()}")

    if skipped:
        print()
        print("  SKIPPED (insufficient or invalid data)")
        print("  " + "-" * 72)
        for r in skipped:
            print(f"  {r.channel_name:<28} {r.channel_type:<10}  {r.warning}")

    print()
    print("=" * 80)
    print(f"  {len(succeeded)} channel(s) fitted  |  {len(skipped)} skipped")
    print("=" * 80)
    print()
    print("  HOW TO USE THESE VALUES")
    print("  Set reach_midpoint_parameter = mu    in the PPS channel table")
    print("  Set reach_spread_parameter   = sigma in the PPS channel table")
    print("  k (capacity) is informational — it reflects the natural ceiling of")
    print("  the channel within the total addressable universe provided.")
    print()


def results_to_df(results: list[FitResult]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "channel_name": r.channel_name,
            "channel_type": r.channel_type,
            "k (capacity)": r.k,
            "mu (midpoint)": r.mu,
            "sigma (spread)": r.sigma,
            "k_std_err": r.k_std_err,
            "mu_std_err": r.mu_std_err,
            "sigma_std_err": r.sigma_std_err,
            "r_squared": r.r_squared,
            "data_points": r.data_points,
            "confidence": r.confidence,
            "warnings": r.warning,
        }
        for r in results
    ])


# ---------------------------------------------------------------------------
# Optional: plot the fitted curves
# ---------------------------------------------------------------------------

def plot_curves(df: pd.DataFrame, results: list[FitResult]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plot. Run: pip install matplotlib")
        return

    succeeded = [r for r in results if r.mu is not None]
    if not succeeded:
        return

    n_plots = len(succeeded)
    cols = min(3, n_plots)
    rows = (n_plots + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 4 * rows))
    axes = np.array(axes).flatten() if n_plots > 1 else [axes]

    for ax, result in zip(axes, succeeded):
        group = df[
            (df["channel_name"] == result.channel_name)
            & (df["channel_type"] == result.channel_type)
        ]

        x_obs = (group["impressions_delivered"] / group["total_addressable_adults"]).values
        y_obs = (group["reach_adults"] / group["total_addressable_adults"]).values

        x_line = np.linspace(0, max(x_obs) * 1.2, 300)
        y_line = logistic_reach(x_line, result.k, result.mu, result.sigma)

        ax.scatter(x_obs, y_obs, color="steelblue", zorder=5, label="Observed")
        ax.plot(x_line, y_line, color="tomato", linewidth=2, label="Fitted curve")
        ax.axvline(result.mu, color="grey", linestyle="--", linewidth=1, alpha=0.7)
        ax.axhline(0.5, color="grey", linestyle="--", linewidth=1, alpha=0.7)

        ax.set_xlabel("Impressions per adult")
        ax.set_ylabel("Reach fraction")
        ax.set_ylim(0, 1)
        ax.set_title(
            f"{result.channel_name} ({result.channel_type})\n"
            f"k={result.k}  mu={result.mu}  sigma={result.sigma}  R²={result.r_squared}"
        )
        ax.legend(fontsize=8)
        ax.text(
            0.97, 0.05,
            f"Confidence: {result.confidence.split(' ')[0]}",
            transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8, color="grey"
        )

    for ax in axes[len(succeeded):]:
        ax.set_visible(False)

    plt.tight_layout()
    out_path = "reach_curves.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"  Plot saved to {out_path}")
    plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit logistic reach curve parameters (mu, sigma) from campaign data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fit_reach_params.py reach_parameter_template.csv
  python fit_reach_params.py my_data.csv --output results.csv
  python fit_reach_params.py my_data.csv --output results.csv --plot
        """,
    )
    parser.add_argument("input_csv", help="Path to the CSV file with campaign data")
    parser.add_argument("--output", "-o", help="Optional path to write results CSV")
    parser.add_argument("--plot", action="store_true", help="Generate fitted curve plots (requires matplotlib)")
    args = parser.parse_args()

    if not Path(args.input_csv).exists():
        print(f"ERROR: file not found: {args.input_csv}", file=sys.stderr)
        sys.exit(1)

    print(f"\nLoading data from: {args.input_csv}")
    df = load_csv(args.input_csv)
    print(f"Loaded {len(df)} valid data point(s) across {df.groupby(['channel_name','channel_type']).ngroups} channel(s)")

    results = []
    for (channel_name, channel_type), group in df.groupby(
        ["channel_name", "channel_type"], sort=False
    ):
        result = fit_channel(str(channel_name), str(channel_type), group)
        results.append(result)

    print_results(results)

    if args.output:
        out_df = results_to_df(results)
        out_df.to_csv(args.output, index=False)
        print(f"  Results written to: {args.output}\n")

    if args.plot:
        plot_curves(df, results)


if __name__ == "__main__":
    main()
