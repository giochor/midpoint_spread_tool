"""
Reach Parameter Estimator — Streamlit UI
=========================================
Wraps fit_reach_params.py with an interactive interface for the Campaign Tactics team.
"""

import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from fit_reach_params import (
    REQUIRED_COLUMNS,
    FitResult,
    fit_channel,
    fit_channel_ct,
    load_csv,
    logistic_reach,
    results_to_df,
    _CT_DENSITY_THRESHOLD,
)

st.set_page_config(
    page_title="Reach Parameter Estimator",
    page_icon="📡",
    layout="wide",
)

st.title("Reach Parameter Estimator")
st.caption(
    "Fits logistic S-curve parameters (Mid-point **μ** and Spread **σ**) from campaign data, "
    "so markets can set PPS values without trial-and-error."
)

# ---------------------------------------------------------------------------
# Sidebar — settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    mode = "CT-mode (recommended)"
    fixed_k = None

    show_residuals = st.checkbox(
        "Show per-point residuals",
        value=False,
        help=(
            "For each data point, shows actual reach vs. what the fitted model predicts, "
            "plus the percentage error. Useful for checking fit quality at each spend level."
        ),
    )

    st.divider()
    st.markdown(
        "**Required CSV columns**\n"
        "- `channel_name`\n"
        "- `channel_type`\n"
        "- `total_addressable_adults`\n"
        "- `impressions_delivered`\n"
        "- `reach_adults`\n\n"
        "Extra columns (e.g. `data_source`, `notes`) are ignored."
    )

# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

uploaded = st.file_uploader(
    "Upload campaign data CSV",
    type="csv",
    help="Upload a CSV with at least the five required columns listed in the sidebar.",
)

if not uploaded:
    st.info("Upload a CSV to begin.")
    st.stop()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

@st.cache_data
def _load_bytes(raw: bytes) -> pd.DataFrame:
    return load_csv(io.StringIO(raw.decode("utf-8", errors="replace")))  # type: ignore[arg-type]


try:
    df = _load_bytes(uploaded.read())
    source_label = uploaded.name
except SystemExit:
    st.error("The file could not be loaded. Check that all required columns are present.")
    st.stop()

if df.empty:
    st.error("No valid rows found after filtering. Check your data.")
    st.stop()

channels = df.groupby(["channel_name", "channel_type"]).ngroups
st.success(
    f"Loaded **{len(df)}** data points across **{channels}** channel(s)  ·  source: `{source_label}`"
)

with st.expander("Preview raw data"):
    st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Fitting curves…")
def run_fit(
    df_json: str,
    mode: str,
    fixed_k: float | None,
) -> list[FitResult]:
    df_inner = pd.read_json(io.StringIO(df_json), orient="split")
    results = []
    for (channel_name, channel_type), group in df_inner.groupby(
        ["channel_name", "channel_type"], sort=False
    ):
        if mode == "CT-mode (recommended)":
            result = fit_channel_ct(str(channel_name), str(channel_type), group)
        else:
            result = fit_channel(str(channel_name), str(channel_type), group, fixed_k=fixed_k)
        results.append(result)
    return results


results = run_fit(df.to_json(orient="split"), mode, fixed_k)

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

st.subheader("Fitted parameters")

succeeded = [r for r in results if r.mu is not None]
skipped = [r for r in results if r.mu is None]

if succeeded:
    summary_rows = []
    for r in succeeded:
        k_display = f"{r.k:.4f} (fixed)" if r.k_fixed else f"{r.k:.4f}"
        conf_icon = {"High": "🟢", "Medium": "🟡"}.get(r.confidence.split(" ")[0], "🔴")
        summary_rows.append(
            {
                "Channel": r.channel_name,
                "Type": r.channel_type,
                "k (capacity)": k_display,
                "μ (midpoint)": r.mu,
                "σ (spread)": r.sigma,
                "R²": r.r_squared,
                "Points": r.data_points,
                "Confidence": f"{conf_icon} {r.confidence}",
                "Warnings": r.warning or "—",
            }
        )

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.info(
        "**How to use:** Set `reach_midpoint_parameter = μ` and `reach_spread_parameter = σ` "
        "in the PPS channel table.  `k` is informational only."
    )

    # Download button
    results_df = results_to_df(results)
    csv_bytes = results_df.to_csv(index=False).encode()
    st.download_button(
        "⬇️ Download results CSV",
        data=csv_bytes,
        file_name="reach_parameters.csv",
        mime="text/csv",
    )
else:
    st.warning("No channels were successfully fitted.")

if skipped:
    with st.expander(f"Skipped channels ({len(skipped)})"):
        for r in skipped:
            st.error(f"**{r.channel_name}** ({r.channel_type}): {r.warning}")

# ---------------------------------------------------------------------------
# Plots — one per channel
# ---------------------------------------------------------------------------

if succeeded:
    st.subheader("Fitted curves")

    n = len(succeeded)
    cols_per_row = min(3, n)
    rows = (n + cols_per_row - 1) // cols_per_row

    fig = make_subplots(
        rows=rows,
        cols=cols_per_row,
        subplot_titles=[f"{r.channel_name} ({r.channel_type})" for r in succeeded],
        horizontal_spacing=0.08,
        vertical_spacing=0.12,
    )

    for idx, result in enumerate(succeeded):
        row = idx // cols_per_row + 1
        col = idx % cols_per_row + 1

        group = df[
            (df["channel_name"] == result.channel_name)
            & (df["channel_type"] == result.channel_type)
        ]
        N = float(group["total_addressable_adults"].values[0])
        x_obs = (group["impressions_delivered"] / N).values
        y_obs = (group["reach_adults"] / N).values

        x_line = np.linspace(0, max(x_obs) * 1.3, 400)
        y_line = logistic_reach(x_line, result.k, result.mu, result.sigma)

        # Distinguish sub-threshold points in CT-mode
        if mode == "CT-mode (recommended)":
            density = group["impressions_delivered"] / N
            mask_fit = (density >= _CT_DENSITY_THRESHOLD).values
            x_op = x_obs[mask_fit]
            y_op = y_obs[mask_fit]
            x_sub = x_obs[~mask_fit]
            y_sub = y_obs[~mask_fit]

            fig.add_trace(
                go.Scatter(
                    x=x_sub, y=y_sub, mode="markers",
                    marker=dict(color="lightgrey", size=8, symbol="circle-open", line=dict(color="grey", width=1.5)),
                    name="Sub-threshold (excluded)",
                    showlegend=(idx == 0),
                ),
                row=row, col=col,
            )
            fig.add_trace(
                go.Scatter(
                    x=x_op, y=y_op, mode="markers",
                    marker=dict(color="steelblue", size=9),
                    name="Observed (operational)",
                    showlegend=(idx == 0),
                ),
                row=row, col=col,
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=x_obs, y=y_obs, mode="markers",
                    marker=dict(color="steelblue", size=9),
                    name="Observed",
                    showlegend=(idx == 0),
                ),
                row=row, col=col,
            )

        fig.add_trace(
            go.Scatter(
                x=x_line, y=y_line, mode="lines",
                line=dict(color="tomato", width=2),
                name="Fitted curve",
                showlegend=(idx == 0),
            ),
            row=row, col=col,
        )

        # Midpoint reference lines
        fig.add_vline(x=result.mu, line=dict(color="grey", dash="dash", width=1), row=row, col=col)
        fig.add_hline(y=result.k / 2, line=dict(color="grey", dash="dash", width=1), row=row, col=col)

        # Annotation with params
        fig.add_annotation(
            text=f"μ={result.mu}  σ={result.sigma}  R²={result.r_squared}",
            xref=f"x{idx + 1}", yref=f"y{idx + 1}",
            x=max(x_obs) * 1.25, y=0.02,
            showarrow=False, font=dict(size=10, color="grey"),
            xanchor="right",
        )

    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    fig.update_xaxes(tickformat=".2f")
    fig.update_layout(
        height=380 * rows,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Residuals
# ---------------------------------------------------------------------------

if show_residuals and succeeded:
    st.subheader("Per-point residuals")

    tab_labels = [r.channel_name for r in succeeded]
    tabs = st.tabs(tab_labels)

    for tab, result in zip(tabs, succeeded):
        with tab:
            if not result.residuals:
                st.info("No residual data.")
                continue

            N = df[df["channel_name"] == result.channel_name]["total_addressable_adults"].values[0]
            threshold_imps = _CT_DENSITY_THRESHOLD * N

            rows_data = []
            for imps, actual, predicted, rel_err in result.residuals:
                excluded = mode == "CT-mode (recommended)" and imps < threshold_imps
                err_pct = rel_err * 100 if not np.isnan(rel_err) else None
                rows_data.append(
                    {
                        "Impressions": f"{imps:,}",
                        "Actual reach": f"{actual:,}",
                        "Model reach": f"{predicted:,}",
                        "Error %": f"{err_pct:+.1f}%" if err_pct is not None else "—",
                        "Note": "sub-threshold (excluded from fit)" if excluded else "",
                    }
                )

            st.dataframe(pd.DataFrame(rows_data), use_container_width=True, hide_index=True)
