[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Jhoni1098/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Jhoni1098/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# gta6-twitch-ccu-forecast-01

Forecast GTA VI's launch-day Twitch viewers hour by hour, for the [make.fun](https://make.fun/bounty/gta6-twitch-ccu-forecast-01) gta6-twitch-ccu-forecast-01 competition. One entrypoint, `main.py` (Python 3.13, standard library only, deterministic, no network): it reads a case's hour-1 print plus the past launches in `comparables` and writes five quantiles of each hour 2–24.

## Model

A launch day has a shape, not a level: viewers dip in the small hours, jump at the US east coast's midnight unlock (05:00 UTC), climb through the day, peak in the US evening, then fall overnight. How steeply a day ramps depends on how much of the audience was already awake in hour 1, so the forecast is built in log space, anchored on the hour-1 print:

- Each comparable launch contributes its release day as log ratios to its own hour-1 print, `ln(v_h / v_1)`.
- The 8 comparables whose hour-1 print is nearest the case's (in log space) shape the forecast; per hour, the median log ratio across them is the centre and their cross-launch standard deviation (clamped to [0.25, 0.70]) is the log spread.
- `q_tau(h) = p1 * exp(median_h + z_tau * spread_h)`, with `z` the normal quantiles at 0.05, 0.25, 0.5, 0.75, 0.95.

Too few neighbours reporting an hour falls back to all comparables, then to a flat median with a wide spread. The GTA VI category's own pre-release curve has no release-day hour 1, so it never counts as a neighbour.

## Local practice score (SullyGnome hourly averages as answers)

| Case | Loss | Baseline |
|------|------|----------|
| p00 Marvel's Wolverine | 0.384 | 0.744 |
| p01 Red Dead Redemption 2 | 0.172 | 0.287 |
| p02 God of War Ragnarök | 0.171 | 0.215 |
| p03 Marvel's Spider-Man 2 | 0.189 | 0.303 |
| **Mean** | **0.229** | **0.387** |

Run it locally:

```
mkdir -p out && MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Two runs on the same case write byte-identical output.
