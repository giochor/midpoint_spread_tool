# Reach Parameter Estimator

A tool for the Campaign Tactics team to automatically calculate the correct **Mid-point** (`mu`) and **Spread** (`sigma`) parameters for Reach Optimisation — eliminating the current trial-and-error process.

## Running the app

The easiest way to use this tool is the Streamlit web app — no command line needed.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Your browser will open automatically at `http://localhost:8501`. Upload your campaign CSV (or tick **Use built-in sample data** to explore straight away), choose a fitting mode, and download the results.

---

## Background

**FCAP** (legacy platform) calculates reach for ATV channels only. **Reach Optimisation** (new platform) supports mixed channel allocation and was built to replace FCAP. However, with identical inputs, Reach Optimisation produces lower reach results than FCAP unless `reach_midpoint_parameter` and `reach_spread_parameter` are correctly configured per market and per channel.

These parameters govern a logistic S-curve model that describes how reach grows as impressions increase. They must be derived from observed campaign data — this tool does that automatically.

## How it works

The script fits a 3-parameter logistic curve to observed (impressions → reach) data points:

```
reach_fraction = k / (1 + exp(-(impression_density - mu) / sigma))
```

| Parameter | Meaning | Where it goes in Reach Optimisation |
|-----------|---------|--------------------------------------|
| `k` | Capacity — maximum reachable fraction of the addressable universe | Informational only |
| `mu` | Mid-point — impression density at which 50% of the reachable audience is reached | `reach_midpoint_parameter` |
| `sigma` | Spread — steepness of the S-curve | `reach_spread_parameter` |

Once fitted, `mu` and `sigma` can be set directly in the PPS channel table, replacing trial-and-error.

## Requirements

Python 3.10+ and the following packages:

```bash
pip install -r requirements.txt
```

`requirements.txt` covers: `numpy`, `pandas`, `scipy`, `matplotlib`

## Input data

Prepare a CSV file with one row per observed data point, per channel. A blank template is provided in `template.csv`. A worked example with multiple channels is in `reach_parameter_template.csv`.

### Required columns

| Column | Type | Description |
|--------|------|-------------|
| `channel_name` | string | Name of the channel (e.g. `ATV`, `Samsung TV Plus`) |
| `channel_type` | string | Channel category — must be one of: `ATV`, `CTV`, `Video`, `Audio`, `DOOH`, `Display` (or any string for a generic fit) |
| `total_addressable_adults` | integer | Total addressable adult universe for this market |
| `impressions_delivered` | integer | Impressions delivered in this campaign flight |
| `reach_adults` | integer | Unique adults reached in this campaign flight |

### Optional columns (ignored by the script but useful for your records)

| Column | Description |
|--------|-------------|
| `campaign_length_days` | Duration of the campaign |
| `data_source` | Where the data came from |
| `notes` | Any notes (e.g. spend level) |

### Data requirements

- **Minimum 3 data points per channel** to fit the 3-parameter model. More is better.
- Data points should cover a **range of spend levels** (low, mid, high) to capture the full S-curve shape. Points clustered at one spend level will produce unreliable fits.
- `reach_adults` must be ≤ `total_addressable_adults`.

### Example row

```
channel_name,channel_type,total_addressable_adults,impressions_delivered,reach_adults
ATV,ATV,52000000,7280000,6198551
ATV,ATV,52000000,19760000,26000000
ATV,ATV,52000000,32240000,45801448
```

## Usage

```bash
# Recommended — CT-mode: fits to the operational impression range only (density ≥ 5% of total adults)
# This minimises relative error across all real campaign impression levels
python fit_reach_params.py my_data.csv --ct-mode

# CT-mode with results written to CSV
python fit_reach_params.py my_data.csv --ct-mode --output results.csv

# Standard 3-parameter fit (fits all data points — use as a baseline reference)
python fit_reach_params.py reach_parameter_template.csv

# Fix k (capacity) to a known value and fit only mu and sigma (2-parameter mode)
python fit_reach_params.py my_data.csv --fixed-k 0.1189

# Show per-point predicted vs actual residuals (implied by --ct-mode)
python fit_reach_params.py my_data.csv --residuals

# Generate fitted curve plots (saved as reach_curves.png)
python fit_reach_params.py my_data.csv --ct-mode --output results.csv --plot
```

## Output

The script prints a summary table with the fitted parameters and a confidence rating:

```
================================================================================
  REACH PARAMETER ESTIMATION RESULTS
================================================================================

  FITTED PARAMETERS
  --------------------------------------------------------------------------------------
  Channel                      Type       k (cap)      mu   sigma      R²  Confidence
  --------------------------------------------------------------------------------------
  ATV                          ATV         0.1189  0.1819  0.1617  0.9955  High
  ...

  HOW TO USE THESE VALUES
  Set reach_midpoint_parameter = mu    in the PPS channel table
  Set reach_spread_parameter   = sigma in the PPS channel table
  k (capacity) is informational — it reflects the natural ceiling of the channel.
```

Confidence levels (CT-mode — recommended):

| Level | Meaning |
|-------|---------|
| High | 6+ operational data points |
| Medium | 4–5 operational data points |
| Low (few points) | 3 operational data points — provisional, collect more |

Confidence levels (standard mode):

| Level | Meaning |
|-------|---------|
| High | 8+ data points |
| Medium | 5–7 data points |
| Low | fewer than 5 data points — provisional, collect more data |

If `--output` is specified, results are also written to a CSV with standard errors and R² for each channel.

## Files

| File | Description |
|------|-------------|
| `app.py` | Streamlit web app (recommended entry point) |
| `fit_reach_params.py` | Core fitting script (also usable from the CLI) |
| `reach_parameter_template.csv` | Worked example with 6 channels and synthetic data |
| `template.csv` | Blank input template to fill in with real campaign data |
| `test_fcap_old.csv` | Real ATV data (8 rows) used to validate CT-mode — produces mu=0.1819, sigma=0.1617 |
| `test_fcap.csv` | Earlier ATV test data used during initial development |
| `requirements.txt` | Python dependencies |
| `reach_analysis.md` | Analysis notes and mathematical background |
| `poc_guide.md` | Guide to the proof-of-concept approach |
