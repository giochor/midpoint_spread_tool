# Reach Parameter Estimator

A tool for the Campaign Tactics team to automatically calculate the correct **Mid-point** (`mu`) and **Spread** (`sigma`) parameters for Reach Optimisation — eliminating the current trial-and-error process.

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
# Basic — print results to terminal
python fit_reach_params.py reach_parameter_template.csv

# Save results to a CSV
python fit_reach_params.py my_data.csv --output results.csv

# Also generate fitted curve plots (saved as reach_curves.png)
python fit_reach_params.py my_data.csv --output results.csv --plot
```

## Output

The script prints a summary table with the fitted parameters and a confidence rating:

```
================================================================================
  REACH PARAMETER ESTIMATION RESULTS
================================================================================

  FITTED PARAMETERS
  ----------------------------------------------------------------------------------
  Channel                      Type        k (cap)      mu   sigma      R²  Confidence
  ----------------------------------------------------------------------------------
  ATV                          ATV          0.1234  0.4500  0.2100  0.9800  High
  ...

  HOW TO USE THESE VALUES
  Set reach_midpoint_parameter = mu    in the PPS channel table
  Set reach_spread_parameter   = sigma in the PPS channel table
```

Confidence levels:

| Level | Meaning |
|-------|---------|
| High | 8+ data points |
| Medium | 5–7 data points |
| Low | 3–4 data points — provisional, collect more data |

If `--output` is specified, results are also written to a CSV with standard errors and R² for each channel.

## Files

| File | Description |
|------|-------------|
| `fit_reach_params.py` | Main script |
| `reach_parameter_template.csv` | Worked example with 6 channels and synthetic data |
| `template.csv` | Blank input template to fill in with real campaign data |
| `test_fcap.csv` | Real ATV data used during development |
| `requirements.txt` | Python dependencies |
| `reach_analysis.md` | Analysis notes and mathematical background |
| `poc_guide.md` | Guide to the proof-of-concept approach |
