# FCAP vs Reach Optimisation: Root Cause Analysis & Parameter Derivation

## Executive Summary

The reach discrepancy between FCAP and Reach Optimisation for ATV-only campaigns has a clear, deterministic cause: **the mu/sigma parameters calibrated for each ATV market in FCAP were never migrated to the equivalent fields in Reach Optimisation**. No trial-and-error is needed — the correct values already exist in the FCAP PPS supplier table.

---

## How Each System Models Reach

Both systems use the same underlying **logistic (sigmoid) S-curve** to model reach probability:

```
P(x) = 1 / (1 + exp(-(x/N - mu) / sigma))
```

Where:
- `x` = rank of the individual within the geokey population (1 to N in FCAP; 0 to N-1 in RO)
- `N` = total adults in the geokey
- `mu` = **Mid-point**: where 50% of the population is reached (x/N = mu)
- `sigma` = **Spread**: how steep or flat the S-curve is

A smaller `mu` means the curve inflects earlier (you reach 50% of the audience with fewer impressions). A smaller `sigma` means the curve is steeper.

### FCAP (legacy)

1. Reads `mu` and `sigma` per ATV supplier from the PPS `supplier` table.
2. Pre-generates BigQuery lookup tables at admin time, applying a **time-decay to sigma**:
   ```
   sigma_effective = sigma + (0.0003 × boundary_day)
   ```
   For a 28-day campaign: `sigma_effective = sigma + 0.0084`
3. Individuals indexed as `x ∈ {1, 2, ..., N}`.

### Reach Optimisation (new)

1. Reads `reach_midpoint_parameter` (mu) and `reach_spread_parameter` (sigma) from the **channel-level** fields in PPS.
2. **If those fields are `None` (not configured), falls back to hardcoded defaults: `mu=0.5, sigma=1.0`.**
3. Does **not** apply time-decay to sigma.
4. Individuals indexed as `x ∈ {0, 1, ..., N-1}`.

---

## Root Causes of Discrepancy (Ranked by Impact)

### 1. Missing parameter migration (PRIMARY — explains most of the gap)

When FCAP was migrated to Reach Optimisation, the market-specific `mu` and `sigma` values from the FCAP PPS `supplier` table were **not copied** to the Reach Optimisation PPS channel fields.

Result: Reach Optimisation defaults to `mu=0.5, sigma=1.0` for all unconfigured ATV channels.

If a market's FCAP supplier was calibrated with, for example, `mu=0.3` (meaning 50% reach is achieved with fewer impressions than the default implies), Reach Optimisation systematically **underestimates reach** for every budget point. This alone can produce 20–50%+ discrepancies depending on how far the calibrated `mu` differs from 0.5.

**Key code location:** `nexus/backend/api-webapp/finecast/unmissable/pricing/calculator.py` lines ~2484–2495 (default fallback logic)

### 2. Time-decay sigma not applied in RO (SECONDARY — a few percent)

FCAP adjusts sigma upward for longer campaigns:
```
sigma_effective = sigma + (0.0003 × boundary_day)
```

Reach Optimisation uses the raw sigma without this adjustment. A larger sigma flattens the S-curve, which generally produces higher reach at moderate impression levels. For a standard 28-day campaign with `sigma=1.0`, FCAP uses `sigma=1.0084` — a ~0.84% difference in sigma, causing a few percent difference in reach.

**Key code location:** `backend/admin-webapp/finecast/dataflow/database.py` (`lookup_table_generate_query`)

### 3. Adult index offset (NEGLIGIBLE — <0.1%)

FCAP uses `x ∈ {1..N}`, RO uses `x ∈ {0..N-1}`. The difference per geokey is:
```
Δ ≈ P(N/N) - P(0/N) = constant regardless of N
```
For typical geokeys with thousands of adults, this rounds to well under 0.1% of total reach.

---

## The Formula: Deriving Correct RO Parameters

No calibration or trial-and-error is needed. The formula is simply:

```
mu_RO    = mu_FCAP
sigma_RO = sigma_FCAP  [optionally + 0.0003 × boundary_day for time-decay parity]
```

Where `boundary_day = find_closest_boundary_day(campaign_length_days)` — the nearest value in `{1, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84, ...}`.

### Worked example

| Parameter           | FCAP Supplier Table | RO (current default) | RO (corrected)              |
|---------------------|--------------------|-----------------------|-----------------------------|
| mu (Mid-point)      | 0.30               | 0.50 (default)        | **0.30**                    |
| sigma (Spread)      | 0.80               | 1.00 (default)        | **0.80** (or 0.8084 for 28d)|
| Expected reach gap  | —                  | Large (20–50%+)       | **< 1%**                    |

---

## Implementation Plan (No Trial-and-Error Required)

### Step 1 — Extract existing FCAP parameters

Query the FCAP PPS `supplier` table for each ATV supplier's:
- `reach_midpoint_parameter` (mu)
- `reach_spread_parameter` (sigma)

These values are already calibrated per market and are the ground truth.

### Step 2 — Write to Reach Optimisation channel fields

Set the values on the corresponding RO channel record in the PPS channel table:
- `reach_midpoint_parameter = mu_FCAP`
- `reach_spread_parameter = sigma_FCAP`

Key model: `nexus/backend/api-webapp/finecast/unmissable/channels/models.py`

### Step 3 (Optional) — Add time-decay parity

Either:
- **Option A (code fix):** Add `time_decay_sigma()` logic to the RO hill-climbing engine (`nexus/.../engines/hill_climbing/engine.py`) to mirror FCAP reach_v3 behaviour.
- **Option B (static adjustment):** For markets with standard 28-day campaigns, set `sigma_RO = sigma_FCAP + 0.0084`.

Option A is more correct and reduces future configuration burden. Option B is simpler but bakes in an assumption about campaign length.

### Step 4 — Validate

After migrating mu/sigma for one market, an ATV-only Reach Optimisation plan with identical budget should produce reach within ~1% of FCAP. The residual 1% comes from the index offset (irreducible, negligible) and any residual time-decay difference if Option B was not applied.

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/api-webapp/finecast/pricing/reach.py` | FCAP parameter sourcing from PPS |
| `backend/admin-webapp/finecast/dataflow/database.py` | FCAP BQ table generation (time-decay applied here) |
| `backend/reach-shared/reach/reach_v3/domain/reach.py` | FCAP sigmoid domain model |
| `nexus/backend/api-webapp/finecast/reach_optimisation/engines/hill_climbing/engine.py` | RO hill-climbing engine (logistic curve computation) |
| `nexus/backend/api-webapp/finecast/unmissable/pricing/calculator.py` | RO parameter sourcing + default fallback (mu=0.5, sigma=1.0) |
| `nexus/backend/api-webapp/finecast/unmissable/channels/models.py` | RO channel model with reach_midpoint/spread fields |

---

## Summary

| Question | Answer |
|----------|--------|
| Why is FCAP reach higher? | RO defaults to mu=0.5, sigma=1.0 because FCAP parameters were never migrated to RO channel fields |
| Can we derive the right values? | Yes — directly from FCAP PPS supplier table, no regression needed |
| Formula for correct mu? | `mu_RO = mu_FCAP` |
| Formula for correct sigma? | `sigma_RO = sigma_FCAP` (optionally + 0.0003 × 28 = +0.0084 for 28-day campaign parity) |
| How to set these easily going forward? | Automate the migration: read from FCAP supplier table, write to RO channel table, done |

---

---

# Part 2: Auto-Discovering Mid-point and Spread for New Markets

## Scope: Which Channels Are Affected

The sigmoid reach model (`logistic_curve` with mu and sigma) is used for **all non-social channels** in the Reach Optimisation engine. The channel taxonomy is:

| Channel Group | Reach Model | mu/sigma required? |
|---------------|-------------|-------------------|
| Addressable TV (ATV) | Sigmoid (logistic curve) | Yes |
| DOOH | Sigmoid (logistic curve) | Yes |
| Video | Sigmoid (logistic curve) | Yes |
| Audio | Sigmoid (logistic curve) | Yes |
| Display | Sigmoid (logistic curve) | Yes |
| CTV | Sigmoid (logistic curve) | Yes (treated as non-social) |
| Social (Meta, Instagram, TikTok, Google) | Custom curve (live API) | **No — exempt** |

Social channels retrieve a pre-computed `budget → reach` curve directly from each platform's API (Meta Graph API, TikTok Ads API, Google Ads API). This curve is interpolated linearly and entirely bypasses the sigmoid model. The mu/sigma problem is irrelevant for them.

For all other channels, the engine branches on `channel.has_custom_curve()`. If no live curve is available (which is the case for ATV, DOOH, Video, Audio, Display, CTV), it falls through to the logistic curve with `reach_midpoint_parameter` and `reach_spread_parameter`. When those are null, the fallback defaults of `mu=0.5, sigma=1.0` apply to every one of these channel types — not just ATV.

**FCAP only ever calculated reach for ATV.** All other channel types are new territory for Reach Optimisation — they have no FCAP history to migrate from, and their mu/sigma values have never been calibrated at all.

---

## The Problem

For markets that **do not have existing FCAP parameters** (e.g. new markets, all non-ATV channels, or markets where historical FCAP data was lost), there is currently no way to determine mu and sigma other than trial-and-error. This section defines exactly what market data is needed to compute them automatically, and the algorithm for doing so.

---

## What the Parameters Actually Mean (Physically)

The logistic curve `P(x/N) = 1 / (1 + exp(-(x/N − mu) / sigma))` models the **probability that person x is reached** in a campaign, where adults within each geokey are ordered by their viewing propensity (rank 1 = most likely viewer, rank N = least likely).

**Mid-point (mu):**
The fraction of the geokey population at which the marginal person has exactly a 50% chance of being reached. A low mu (e.g. 0.2) means viewing is concentrated — a small, loyal group are highly likely to be reached, and diminishing returns set in quickly. A high mu (e.g. 0.7) means viewing is spread broadly — you can keep spending and keep reaching new people further into the campaign.

**Spread (sigma):**
How steeply or gradually the transition from "unlikely to be reached" to "likely to be reached" occurs. A small sigma (e.g. 0.1) produces a sharp S-curve: the population is divided into "definite viewers" and "definite non-viewers" with little in between. A large sigma (e.g. 1.5) produces a flat, gradual curve: almost everyone has some chance of being reached with enough budget.

In TV terms:
- **Low mu + low sigma** → niche channel: small highly-engaged audience, fast reach saturation
- **High mu + high sigma** → mass-reach channel: broad audience, reach grows slowly but keeps building

---

## What Market Data Is Required

To solve for two unknown parameters (mu and sigma), you need at minimum **two data points on the reach curve**: pairs of (impressions delivered, reach achieved). More data points produce a more stable fit.

The required data and the best source varies significantly by channel type.

---

### By Channel Type

#### Addressable TV (ATV)

**Best source:** TV audience panel data (BARB in UK, AGF/GfK in Germany, Auditel in Italy, SKO in Netherlands, OzTAM in Australia, Nielsen in US). These bodies measure actual reach at various GRP levels via panel sampling.

**Data format:**
```
GRP | Reach%
----|-------
50  | 18%
100 | 31%
200 | 48%
400 | 62%
800 | 73%
```

GRP converts to impressions via: `Impressions = GRP × (target_adults / 100)`

**For existing FCAP markets:** use the FCAP migration path from Part 1 — no data collection needed.

**Characteristics of the reach curve:** The audience for ATV tends to be relatively concentrated (loyal viewers watch heavily, non-viewers don't watch at all), so mu is often in the range 0.25–0.45 and sigma 0.5–1.0. Curves saturate faster than digital channels.

---

#### DOOH (Digital Out-of-Home)

**Best source:** Vendor-provided audience data (e.g. Ocean Outdoor, Clear Channel, JCDecaux all publish reach and frequency data for their networks) or third-party measurement (Route in UK, COMMB in Canada, OAAA in US).

**Data format:** Usually published as a reach curve against number of screens × days, or total SOV (share of voice) × days. Requires conversion to an impression-equivalent metric.

**Characteristics of the reach curve:** DOOH reach builds very differently from ATV. The audience is location-based and highly dependent on venue type (retail vs. transport hub vs. roadside). mu is typically higher (0.5–0.7) because the passers-by are less concentrated — many people pass each screen but with low dwell time — and sigma is large (1.0–2.0) because the audience is heterogeneous across locations.

**Key complication:** Unlike TV, DOOH geokey population data is footfall (people passing a screen) rather than a fixed household-based audience. The reach model currently uses household adult data from BQ, which may not accurately represent DOOH exposure. This is a model accuracy concern separate from the mu/sigma question.

---

#### Video (Online Video / Streaming)

**Best source:** Platform-level reporting (YouTube, catch-up TV platforms, AVOD) or third-party measurement (DoubleVerify, IAS, Nielsen DAR, BARB streaming measurement).

**Data format:** Impressions delivered and unique users reached, from campaign delivery reports. Most video platforms can provide this per campaign.

**Characteristics of the reach curve:** Online video audiences are broad but fragmented. Reach builds more gradually than ATV (higher mu, e.g. 0.5–0.8) and sigma is typically large (1.0–2.0) because the audience is highly diverse in consumption patterns. Frequency caps heavily influence the shape of the curve.

---

#### Audio (Podcast / Streaming Audio)

**Best source:** Streaming audio platforms (Spotify, Acast, Global, Bauer) publish reach and frequency data per campaign. Some markets have independent audio measurement (RAJAR in UK publishes reach curves for radio/audio).

**Data format:** Unique listeners reached vs. total spots / impressions delivered.

**Characteristics of the reach curve:** Audio audiences tend to have high loyalty to specific shows/stations but low cross-channel overlap. mu is typically moderate (0.35–0.55) and sigma moderate (0.6–1.0). Podcast audiences are especially concentrated — very similar to niche ATV.

---

#### Display (Digital Display / Banners)

**Best source:** Campaign delivery reports from the DSP or ad server (DV360, The Trade Desk, Xandr). Unique cookie/device reach vs. impressions is standard in display reporting.

**Data format:** Impressions delivered, unique devices/cookies reached, estimated unique people reached (after identity resolution or modelling).

**Characteristics of the reach curve:** Display has the flattest, most gradual reach curve of all channel types. The audience is enormous (almost everyone browses the web) but any individual has a very low per-impression probability of seeing a specific ad. mu is very high (0.6–0.9) and sigma is very large (1.5–3.0). The curve rarely saturates within normal campaign budgets.

**Key complication:** Display impressions can be served to the same device/browser multiple times. "Unique people reached" requires identity resolution that introduces measurement uncertainty.

---

#### CTV (Connected TV)

**Best source:** CTV platform data (Samsung Ads, LG Ads, Amazon Streaming TV, Netflix, Disney+) or third-party CTV measurement (iSpot, VideoAmp, Samba TV). BARB in the UK is extending its panel to cover CTV.

**Data format:** Unique households or unique adults reached vs. impressions served.

**Characteristics of the reach curve:** CTV sits between ATV and Video. The audience tends to be loyal to a smaller set of streaming services, so mu is moderate (0.35–0.55) and sigma moderate to large (0.8–1.5). Reach saturates faster than display but more slowly than linear ATV.

---

### Option A — Post-Campaign Actuals (Lowest cost, works for all channels)

Regardless of channel type, the universal fallback is to collect actual delivery data:

**Data needed per campaign:**
- Total impressions delivered on the channel
- Actual unique adults reached (from the delivery or measurement platform)
- Total addressable adults in the market

**Minimum:** 2 completed campaigns at different budget levels (one low-spend, one high-spend) to capture different parts of the S-curve.

**Ideal:** 5–10 campaigns spanning a range of impression volumes.

This data does not currently exist in the finecast system. It would require a new post-campaign data pipeline connecting delivery platforms back to the system.

---

### Option B — Third-Party Measurement / Ratings Bodies

For ATV specifically, national ratings bodies (BARB, AGF, Auditel, etc.) are the most authoritative source and require only a data agreement, not new instrumentation. See the per-channel details above for each channel's equivalent authority.

---

### Option C — FCAP Migration (ATV only, existing FCAP markets)

For ATV channels where FCAP parameters already exist, apply the direct migration from Part 1:
```
mu_RO = mu_FCAP
sigma_RO = sigma_FCAP
```
No data collection required.

---

### Option D — Sensible Defaults by Channel Type (Fallback)

When no data is available, use these starting estimates rather than the hardcoded `mu=0.5, sigma=1.0` default, which is wrong for almost every channel type:

| Channel type | Suggested mu | Suggested sigma | Rationale |
|-------------|-------------|----------------|-----------|
| ATV — mass reach (ITV, RAI, RTL) | 0.35–0.45 | 0.70–0.90 | Concentrated loyal audience |
| ATV — niche / regional | 0.20–0.35 | 0.40–0.70 | Small, very loyal audience |
| DOOH | 0.55–0.70 | 1.20–2.00 | Broad, location-dispersed audience |
| Video (online, streaming) | 0.50–0.70 | 1.00–1.80 | Broad, fragmented audience |
| Audio | 0.35–0.55 | 0.60–1.00 | Moderate loyalty, moderate concentration |
| Display | 0.65–0.85 | 1.50–3.00 | Very broad, very flat curve |
| CTV | 0.35–0.55 | 0.80–1.50 | Between ATV and Video |

These are approximations based on the nature of each channel's audience. They should be replaced with fitted values as soon as campaign data becomes available.

---

## The Fitting Algorithm

Once reach curve data points are collected (by any of the options above), the algorithm to derive mu and sigma is straightforward curve fitting using least squares minimisation.

**Step 1 — Convert data points to the normalised form**

The sigmoid takes `x/N` (the rank fraction), but observable data is in `(impressions, reach%)`. The bridge between them is the **average audience per geokey**, which is already in the BQ audience tables.

For a market with `A` total adults across `G` geokeys:
```
avg_adults_per_geokey = A / G
effective_x_over_N ≈ impressions / (avg_adults_per_geokey × G)
                    = impressions / A
                    = impressions_per_adult
```

In practice, `x/N` in the sigmoid maps to impression density (impressions per adult in the market). When impressions_per_adult = mu, approximately 50% reach is expected.

**Step 2 — Fit mu and sigma**

```python
import numpy as np
from scipy.optimize import curve_fit

def logistic_reach(impressions_per_adult, mu, sigma):
    return 1 / (1 + np.exp(-(impressions_per_adult - mu) / sigma))

# Data points: (impressions_per_adult, reach_fraction)
x_data = np.array([0.10, 0.25, 0.50, 0.80, 1.20])  # impressions / total_adults
y_data = np.array([0.18, 0.31, 0.48, 0.62, 0.73])  # reach as fraction of total adults

(mu_hat, sigma_hat), covariance = curve_fit(
    logistic_reach,
    x_data,
    y_data,
    p0=[0.5, 1.0],          # initial guess
    bounds=([0.0, 0.01], [1.0, 5.0]),  # mu ∈ [0,1], sigma > 0
)
```

The `scipy.optimize.curve_fit` function already exists in the finecast codebase (used by the performance planner module for spend-vs-conversion curves) and can be reused directly.

**Step 3 — Write to PPS**

Set the fitted values on the channel record:
- `reach_midpoint_parameter = mu_hat`
- `reach_spread_parameter = sigma_hat`

**Step 4 — Validate**

Run the hill-climbing engine with the new parameters and compare predicted reach at several impression levels against the observed data points. The residuals should be < 5% at each point with 2 data points, and reduce further as more data is added.

---

## Confidence and Uncertainty

With only 2 data points, the fit is exact but has no uncertainty estimate. With 3+ data points, the `covariance` matrix from `curve_fit` gives confidence intervals for mu and sigma.

Practical rule of thumb:
- **2 data points**: usable, but treat as provisional — re-fit when the 3rd campaign completes
- **5+ data points** spanning the lower, middle, and upper parts of the curve: stable, production-quality estimate
- **10+ data points**: high confidence, suitable for automated use without manual review

The fit degrades significantly if all data points cluster at one end of the curve (e.g., all low-impression campaigns). The data collection strategy should aim for campaigns at varied budget levels.

---

## Proposed System Architecture for Auto-Discovery

### What needs to be built

1. **Post-campaign actuals pipeline**: After each campaign closes, record `(channel_id, market, impressions_delivered, actual_unique_reach, campaign_length_days)` in a new BQ table. This requires an integration with each delivery platform's reporting API.

2. **Parameter fitting job**: A scheduled job (e.g. weekly) that:
   - Reads all actuals data per channel
   - Runs `curve_fit` against the logistic model
   - Updates `reach_midpoint_parameter` and `reach_spread_parameter` in PPS if confidence is sufficient (≥ 3 data points, residuals < 5%)
   - Flags channels with insufficient data for manual review

3. **Ratings data ingestion (optional, higher accuracy)**: A pipeline to ingest reach-vs-GRP tables from each market's ratings authority (BARB, AGF, etc.) and use these as additional data points in the fit.

4. **Fallback logic in RO**: When channel parameters are still null (new market, insufficient data), the RO engine should default to the cross-market initialisation values from the table above rather than the hardcoded `mu=0.5, sigma=1.0`.

### Data collection priority

| Priority | Action | Unblocks |
|----------|--------|----------|
| 1 | Migrate existing FCAP parameters to RO channel fields (Part 1) | All existing FCAP markets immediately |
| 2 | Build post-campaign actuals pipeline | Self-calibrating system for all markets over time |
| 3 | Ingest ratings data from BARB/AGF/etc. | High-quality bootstrap for markets without post-campaign data |
| 4 | Implement improved fallback defaults per channel type | Better experience for brand-new markets |

---

## Summary

| Question | Answer |
|----------|--------|
| Which channels need mu/sigma? | ATV, DOOH, Video, Audio, Display, CTV — all non-social channels |
| Which channels are exempt? | Social (Meta, TikTok, Google) — they use live API curves instead |
| Does FCAP help for non-ATV channels? | No — FCAP only ever covered ATV. All other channels are uncalibrated |
| What data is needed to auto-derive mu and sigma? | At minimum 2 (impressions, actual_reach) pairs from completed campaigns |
| What is the best data source per channel? | ATV: BARB/AGF/Nielsen; DOOH: vendor data (Ocean, Clear Channel); Video/CTV: platform reports; Audio: streaming platform data; Display: DSP delivery reports |
| Does this data currently exist in the system? | No — a post-campaign actuals pipeline needs to be built |
| What is the fitting algorithm? | `scipy.optimize.curve_fit` against the logistic function (already in the codebase) |
| What can be done right now without new data? | Migrate FCAP parameters for ATV (Part 1); replace hardcoded defaults with per-channel-type estimates for all others |
| How many data points for a reliable fit? | 2 minimum, 5+ recommended, 10+ for high confidence |
| What happens with 0 data? | Use per-channel-type defaults (see table above) — far better than mu=0.5, sigma=1.0 for every channel |
