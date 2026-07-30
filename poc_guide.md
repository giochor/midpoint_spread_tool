# Reach Parameter Estimator — POC Guide

This tool derives the correct **Mid-point (mu)** and **Spread (sigma)** values for Reach Optimisation channels from observed campaign data. It replaces the current trial-and-error process with a deterministic curve-fitting approach.

---

## Files

| File | Purpose |
|------|---------|
| `reach_parameter_template.csv` | Template to fill in with your channel data — one row per data point |
| `fit_reach_params.py` | Python script that reads the CSV and outputs fitted parameters |
| `reach_analysis.md` | Full technical background on the FCAP vs RO discrepancy |

---

## How It Works

The script fits a logistic S-curve to your observed (impressions, reach) data:

```
Reach% = 1 / (1 + exp(-(impressions_per_adult − mu) / sigma))
```

Given enough data points per channel, it finds the `mu` and `sigma` values that best match your observed data. These values can then be written directly into the Reach Optimisation PPS channel table — no further tuning needed.

---

## Before You Start: Key Concepts

### What is a data point?

Each row in the CSV is one **(impressions delivered, reach achieved)** observation — the result of a single completed campaign or a single GRP measurement from a ratings body.

**Rows are not a time series.** You are not tracking the same campaign over time. You are collecting snapshots from different campaigns at different spend levels on the same channel. What the script needs is to see the reach curve at different points — low spend, medium spend, high spend — so it can fit the S-curve shape.

Think of it this way: if you ran three campaigns on ITV Hub — one small, one medium, one large — you would have three rows. Each row records the total impressions and total unique adults reached for that campaign.

A good set of rows looks like this:

| Impressions | Reach adults | What this tells the fitter |
|-------------|-------------|---------------------------|
| 5,000,000 | 3,200,000 | Where the curve starts (low end) |
| 15,000,000 | 8,900,000 | The rising middle of the S-curve |
| 30,000,000 | 16,500,000 | Where reach begins to saturate |

A bad set of rows (all at the same impression level) tells the fitter almost nothing:

| Impressions | Reach adults | Problem |
|-------------|-------------|---------|
| 15,000,000 | 8,900,000 | |
| 15,000,000 | 9,100,000 | Cannot fit a curve from one point |
| 15,000,000 | 8,700,000 | |

**Minimum 3 rows at different impression levels per channel (CT-mode requires 3 points above the 5% density threshold). 6+ is strongly recommended for a High-confidence result.**

---

### Channel type vs provider: which name to use?

In Reach Optimisation, **mu and sigma are configured at the channel type level** — one pair of values for ATV, one for DOOH, one for Video, and so on. They are not set per provider (not per ITV Hub, not per Spotify).

The `channel_name` column in the CSV is purely a grouping label used by the fitting script. It does not need to match any field in PPS. You have two valid approaches:

**Approach A — You have data from a specific provider and want to derive channel-type parameters from it:**

Use the provider name (e.g. `ITV Hub`) in `channel_name`. Run the script. Take the fitted mu and sigma and apply them to the ATV channel type in PPS.

If you have data from multiple ATV providers, fit each separately and average the mu and sigma values, or use the largest/most representative provider as a proxy for the whole channel type.

**Approach B — You have pooled data for the channel type (e.g. from a ratings body that covers all ATV):**

Use the channel type name directly as `channel_name` (e.g. `ATV`, `DOOH`). The output then maps directly to PPS with no translation step needed.

Either approach is valid. Approach B is simpler when you have market-level ratings data. Approach A is more practical when your data comes from campaign delivery reports for specific providers.

---

## Step 1: Fill in the CSV Template

Open `reach_parameter_template.csv`. Each row is one observed (impressions, reach) data point — a completed campaign or a GRP measurement. Replace the example rows with your real data.

The file has no market column — the tool is run per-market, so the market is implicit.

### CSV columns

#### Required

| Column | Description |
|--------|-------------|
| `channel_name` | Channel or supplier name. Must be consistent across rows for the same channel (e.g. always `ITV Hub`, not sometimes `ITV`). |
| `channel_type` | One of: `ATV`, `DOOH`, `Video`, `Audio`, `Display`, `CTV`. Determines the fitting bounds used by the script. |
| `total_addressable_adults` | Total adults reachable by this channel (integer). This is a property of the channel footprint, not the campaign — it stays the same across all rows for a given channel. See notes below for how to define this per channel type. |
| `impressions_delivered` | Total ad impressions served in this campaign or measurement period (integer). |
| `reach_adults` | Unique adults reached in this campaign or measurement period (integer). If you only have a reach percentage, convert it: `reach_adults = reach_percentage × total_addressable_adults`. |

#### Optional

| Column | Description |
|--------|-------------|
| `campaign_length_days` | Number of days the campaign ran. Useful context; not used in the current fitting calculation. |
| `data_source` | Where the data came from. Suggested values: `post-campaign actuals`, `BARB`, `AGF`, `Auditel`, `SKO`, `OzTAM`, `Nielsen`, `vendor data`, `platform report`. |
| `notes` | Free text — campaign name, date, GRP level, caveats. |

### How to define `total_addressable_adults` per channel type

| Channel type | Definition |
|--------------|------------|
| ATV | All adults in the broadcast footprint (typically the full market adult population). |
| DOOH | Estimated unique daily adults passing the network's screens (from vendor measurement). |
| Video | Estimated unique adults online in the market (from platform or third-party estimate). |
| Audio | Unique monthly listeners on the platform in the market. |
| Display | Estimated unique adults addressable online (from DSP audience estimate). |
| CTV | Estimated unique adults with access to the platform/device in the market. |

### Tips for good data

- **Cover a range of impression levels.** The single most important thing is to have rows at different spend levels — one low, one high, and ideally some in between. Two rows at the same impression level are almost useless.
- **Minimum 3 rows per channel; 6+ is recommended.** In CT-mode, only rows above the 5% impression density threshold count toward the minimum. Six or more qualifying rows give a High-confidence, stable result.
- **Keep targeting consistent across rows.** Mixing a broad-audience campaign with a narrow-targeted campaign distorts the curve because the effective audience size changes between them.
- **Keep campaign length broadly similar across rows.** Avoid mixing 7-day and 90-day campaigns in the same fit — reach builds differently over time and this will introduce noise.
- **Do not mix channel types for the same channel name.** Each `(channel_name, channel_type)` pair is fitted independently. If ITV Hub runs on both ATV and CTV, use separate rows with different `channel_type` values.

### Where to get the data

| Channel type | Best source |
|--------------|-------------|
| ATV | BARB (UK), AGF/GfK (DE), Auditel (IT), SKO (NL), OzTAM (AU), Nielsen (US) — request a reach-vs-GRP table for the channel |
| DOOH | Network vendor (Ocean Outdoor, Clear Channel, JCDecaux) — audience measurement report |
| Video / CTV | Platform delivery report (Google Ads, Samsung Ads, Amazon) — unique reach column |
| Audio | Platform report (Spotify for Brands, Acast, Global) — unique listeners column |
| Display | DSP report (DV360, The Trade Desk) — unique reach / deduplicated audience column |

> For **ATV channels that previously ran on FCAP**, you can skip the CSV entirely. The correct parameters are already stored in the FCAP PPS supplier table — see `reach_analysis.md` Part 1 for the direct migration approach.

---

## Step 2: Set Up the Environment

System Python on Debian/Ubuntu blocks direct pip installs (PEP 668). Use a virtual environment.

**First-time only — install the venv package (requires sudo):**

```bash
sudo apt install python3.12-venv
```

**Then create and activate the environment:**

```bash
# Create the virtual environment (one-time)
python3 -m venv .venv

# Activate it
source .venv/bin/activate        # macOS / Linux / WSL
# .venv\Scripts\activate         # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

`matplotlib` is only needed for the `--plot` flag. It is included in `requirements.txt` but the script works without it if you skip that flag.

> The virtual environment must be active whenever you run the script. You will see `(.venv)` at the start of your shell prompt when it is active. To deactivate, run `deactivate`.

---

## Step 3: Run the Script

Make sure the virtual environment is active (`source .venv/bin/activate`) before running.

### Recommended: CT-mode

CT-mode fits the logistic curve to the **operational impression range only** (impression density ≥ 5% of total adults). FCAP's formula is nearly linear at very low impression density — the logistic model diverges there and produces large errors if those points are included. CT-mode excludes them and produces mu/sigma calibrated to where Reach Optimisation actually evaluates reach in real campaigns.

```bash
# Recommended — CT-mode fit (implies --residuals)
python fit_reach_params.py my_data.csv --ct-mode

# CT-mode with results written to CSV
python fit_reach_params.py my_data.csv --ct-mode --output results.csv

# CT-mode with curve plots (saved as reach_curves.png)
python fit_reach_params.py my_data.csv --ct-mode --output results.csv --plot
```

To validate using the included real ATV data:

```bash
python fit_reach_params.py test_fcap_old.csv --ct-mode
# Expected output: mu=0.1819, sigma=0.1617, R²=0.9955, max error ±6%
```

### Other modes

```bash
# Standard 3-parameter fit (all data points — use as a baseline reference)
python fit_reach_params.py reach_parameter_template.csv

# Show per-point residuals without CT-mode
python fit_reach_params.py my_data.csv --residuals

# Fix k (capacity) to a known value and fit only mu and sigma
# Use when you already know the channel's saturation ceiling from CT output
python fit_reach_params.py my_data.csv --fixed-k 0.1189

# Without activating the venv — call Python directly
.venv/bin/python fit_reach_params.py my_data.csv --ct-mode
```

---

## Step 4: Read the Output

### Console output example

```
================================================================================
  REACH PARAMETER ESTIMATION RESULTS
================================================================================

  FITTED PARAMETERS
  ──────────────────────────────────────────────────────────────────────────────────
  Channel                      Type       k (cap)      mu   sigma      R²  Confidence
  ──────────────────────────────────────────────────────────────────────────────────
  ITV Hub                      ATV         0.1189  0.1819  0.1617  0.9955  High
  Sky AdSmart                  ATV         0.2960  0.6102  0.9874  0.9874  Medium
  Ocean Outdoor                DOOH        0.3100  0.6340  1.5200  0.9512  Low (!)
  Spotify                      Audio       0.3000  0.4280  0.7910  0.9963  Medium

  [F] = k was fixed by --fixed-k (not fitted from data)
  (!) = warnings present — see details below

  WARNING — Ocean Outdoor:
    • mu standard error is large — more data points would improve precision
```

In CT-mode, a **PER-POINT RESIDUALS** section is also printed, showing impressions, actual reach, model reach, and percentage error for each data point.

### Confidence levels

CT-mode (recommended):

| Level | Meaning |
|-------|---------|
| High | 6+ operational data points |
| Medium | 4–5 operational data points |
| Low (few points) | 3 operational data points — provisional, collect more |

Standard mode:

| Level | Meaning |
|-------|---------|
| High | 8+ data points |
| Medium | 5–7 data points |
| Low (few points) | fewer than 5 data points — provisional, collect more |

### Output CSV columns

| Column | Description |
|--------|-------------|
| `k (capacity)` | Fitted capacity — maximum reachable fraction of total addressable adults. Informational only. |
| `k_fixed` | `True` if k was fixed via `--fixed-k`, `False` if fitted from data |
| `mu (midpoint)` | Fitted Mid-point — write this to `reach_midpoint_parameter` in PPS |
| `sigma (spread)` | Fitted Spread — write this to `reach_spread_parameter` in PPS |
| `k_std_err` | Standard error on k — lower is better |
| `mu_std_err` | Standard error on mu — lower is better |
| `sigma_std_err` | Standard error on sigma — lower is better |
| `r_squared` | Goodness of fit. 1.0 = perfect match. Above 0.95 is good; below 0.90 means more data is needed |
| `confidence` | See confidence levels above |
| `warnings` | Any fit quality issues to review |

---

## Step 5: Apply the Parameters in PPS

In Reach Optimisation, mu and sigma are stored at the **channel type level** in the PPS channel table — one pair of values for ATV, one for DOOH, and so on. They are not stored per provider.

Set the fitted values on the corresponding channel type record:

```
reach_midpoint_parameter = mu     (from the output)
reach_spread_parameter   = sigma  (from the output)
```

**If you fitted a specific provider (e.g. ITV Hub → ATV):** Apply the fitted mu/sigma to the ATV channel type in PPS. If you also fitted other ATV providers (e.g. Sky AdSmart), you can average the mu and sigma values across providers, or use the one with the most data points and highest R².

**If you fitted using a channel type name directly (e.g. `ATV`):** The output maps directly to the matching PPS channel type — no translation needed.

After this, Reach Optimisation plans for that channel type will use the calibrated curve — reach estimates will align with your observed historical data, with no further adjustment needed.

---

## Understanding the Parameters

### Mid-point (mu)

The impression density (impressions ÷ total addressable adults) at which 50% of the audience has been reached. A lower mu means the audience is concentrated — you reach the first half quickly. A higher mu means the audience is broadly spread — reach builds more gradually.

| Channel type | Typical mu range |
|--------------|-----------------|
| ATV (mass-reach) | 0.30 – 0.50 |
| ATV (niche) | 0.15 – 0.35 |
| DOOH | 0.50 – 0.70 |
| Video / CTV | 0.45 – 0.70 |
| Audio | 0.35 – 0.55 |
| Display | 0.65 – 0.85 |

### Spread (sigma)

How steeply the transition from "unlikely reached" to "likely reached" occurs. A small sigma means a sharp S-curve — the audience is split between loyal viewers and non-viewers. A large sigma means a flat, gradual curve — diminishing returns are slow and broad.

| Channel type | Typical sigma range |
|--------------|---------------------|
| ATV | 0.50 – 1.00 |
| DOOH | 1.00 – 2.00 |
| Video / CTV | 0.80 – 1.80 |
| Audio | 0.60 – 1.00 |
| Display | 1.50 – 3.00 |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Only N data point(s) above density threshold — need at least 3" | CT-mode: fewer than 3 rows have impression density ≥ 5% of total adults | Add rows at higher impression levels, or check that `total_addressable_adults` is not too high |
| "Need at least 2/3 data points — skipped" | Too few rows for this channel | Add at least 3 rows at different impression levels |
| "Curve fitting did not converge" | All rows at the same impression level, or extreme outliers | Ensure rows span a range of impression volumes; check for data entry errors |
| R² below 0.90 | Noisy data or the logistic model is a poor fit for this channel | Add more rows; check that `impressions_delivered` and `reach_adults` are from the same campaign |
| Large standard errors | Too few points, or points clustered at one end of the curve | Add a point at the opposite end (e.g. a high-spend campaign if all current rows are low-spend) |
| mu or sigma at the edge of its range | Optimiser hit a boundary constraint | Check whether `total_addressable_adults` is correct; inspect the raw data for outliers |

---

## Limitations

1. **Simplified population model.** The script treats the whole market as one population (`impression_density = impressions / total_adults`). The Reach Optimisation engine distributes adults across geographic geokeys. For markets with very uneven geographic targeting the fitted parameters may need a small manual check.

2. **No time-decay correction.** FCAP widens sigma slightly for longer campaigns (`+0.0003 × days`). This POC fits raw data without that correction. For campaigns of similar length (e.g. all 28-day), the effect is negligible.

3. **CT-mode requires 3 operational points.** Points below 5% impression density are excluded from the fit (they are shown in the residuals as approximate only). If fewer than 3 points remain above the threshold, the channel is skipped — add rows at higher spend levels.

4. **Social channels are not supported.** Meta, TikTok, and Google channels use live API reach curves and do not use mu/sigma. Do not include them in the CSV.
