"""Forecast GTA VI's launch-day Twitch viewers, hour by hour.

The program reads one case (makefun/twitch-ccu-case/v1): the first hour's
print of a big game's release day on Twitch, plus the hourly curves of past
big launches (the case's comparables). It writes, for hours 2 to 24, five
quantiles of each hour's concurrent-viewer count.

Model (log space, anchored on the hour-1 print)
-----------------------------------------------
A launch day on Twitch has a shape, not a level: viewers dip in the small
hours, jump when the US east coast wakes (its midnight unlock is 05:00 UTC),
climb through the day as more regions unlock and evening arrives, peak in
the US evening, then fall overnight. The shape is shared across launches,
but how steeply a day ramps depends on how much of the audience was already
awake in hour 1: a launch whose hour-1 print is small (only New Zealand and
Australia awake) ramps far harder than one whose hour 1 already holds a big
prime-time audience.

So for each comparable launch we take its release day's hourly curve and
express every hour as a log ratio to that launch's own hour-1 print,
ln(v_h / v_1). For the case at hand we keep the NEIGHBOURS comparables
whose hour-1 print is closest in log space to the case's hour-1 print, and
per hour we take the median log ratio across those neighbours as the
forecast's centre, and the neighbours' cross-launch standard deviation
(clamped to [0.25, 0.70]) as its log spread. Quantiles are then

    q_tau(h) = p1 * exp(median_h + z_tau * spread_h)

with p1 the case's hour-1 print and z the standard normal's quantiles at
0.05, 0.25, 0.5, 0.75 and 0.95. Where too few neighbours report an hour we
fall back to all comparables, then to a flat median with a wide spread.

Calibrated on the four practice cases (SullyGnome hourly averages as the
answers): mean pinball loss about 0.229, against the house persistence
baseline's 0.387. Per case: p00 0.384, p01 0.172, p02 0.171, p03 0.189.

Standard library only, no network, no randomness: two runs on the same
case write byte-identical output.
"""

import json
import math
import os
import statistics
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z_SCORES = [-1.645, -0.674, 0.0, 0.674, 1.645]

# How many nearest launches (by hour-1 print, in log space) shape a forecast.
NEIGHBOURS = 8
# A comparable only counts if it reports at least this many hours of its
# release day; sparser curves are pre-release noise, not launch days.
MIN_RATIOS_PER_CURVE = 15
# Below this many neighbours reporting an hour, fall back to all comparables.
MIN_NEIGHBOURS_PER_HOUR = 3
# The cross-launch log spread is clamped into this band.
SPREAD_FLOOR = 0.25
SPREAD_CAP = 0.70
# Spread used when no comparable reports an hour at all.
FALLBACK_SPREAD = 0.50
# The contest's cap on any single quantile.
MAX_VIEWERS = 1_000_000_000


def round_half_up_2(x: float) -> float | int:
    """Round x to 2 decimals, halves up, returning an int when whole."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if value.is_integer() else value


def clamp_quantile(q: float) -> float | int:
    """Keep a quantile inside the contest's (0, 1e9] band."""
    if not math.isfinite(q) or q <= 0:
        return 0.01
    if q > MAX_VIEWERS:
        return MAX_VIEWERS
    return round_half_up_2(q)


def release_day_ratios(comp: dict) -> tuple[float, dict[int, float]] | None:
    """A comparable's release day as (hour-1 print, {hour: log ratio}).

    Returns None when the comparable has no usable hour-1 print on its
    release day (for example the GTA VI category itself before release),
    or when it reports too few hours of that day to be a launch curve.
    """
    day = comp["day_start"][:10]
    by_hour: dict[int, float] = {}
    for point in comp.get("hourly", []):
        if point["from"][:10] != day:
            continue
        viewers = point.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        by_hour[int(point["from"][11:13]) + 1] = float(viewers)
    first = by_hour.get(1)
    if not first:
        return None
    ratios = {
        hour: math.log(viewers / first)
        for hour, viewers in by_hour.items()
        if hour >= 2
    }
    if len(ratios) < MIN_RATIOS_PER_CURVE:
        return None
    return first, ratios


def pick_neighbours(case: dict, p1: float) -> list[tuple[float, dict[int, float]]]:
    """The comparables whose hour-1 print is nearest the case's, in log space.

    Neighbours are taken in order of |ln(p1_comp) - ln(p1)|; the case file's
    order breaks ties, so the pick is deterministic for a given case.
    """
    log_p1 = math.log(p1)
    curves = []
    for comp in case.get("comparables", []):
        parsed = release_day_ratios(comp)
        if parsed is not None:
            curves.append(parsed)
    curves.sort(key=lambda item: abs(math.log(item[0]) - log_p1))
    return curves[:NEIGHBOURS]


def hour_centre_spread(
    neighbours: list[tuple[float, dict[int, float]]],
    everyone: list[tuple[float, dict[int, float]]],
    hour: int,
) -> tuple[float, float]:
    """A hour's (median log ratio, log spread) from its neighbours.

    Falls back to every comparable when too few neighbours report the
    hour, and to a flat median with a wide spread when nobody reports it.
    """
    ratios = [curve[hour] for _, curve in neighbours if hour in curve]
    if len(ratios) < MIN_NEIGHBOURS_PER_HOUR:
        ratios = [curve[hour] for _, curve in everyone if hour in curve]
    if len(ratios) < MIN_NEIGHBOURS_PER_HOUR:
        return 0.0, FALLBACK_SPREAD
    centre = statistics.median(ratios)
    spread = statistics.pstdev(ratios) if len(ratios) > 1 else FALLBACK_SPREAD
    spread = min(SPREAD_CAP, max(SPREAD_FLOOR, spread))
    return centre, spread


def forecast_case(case: dict, name: str) -> dict:
    """Forecast hours 2 to 24 of one case as five quantiles an hour."""
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    neighbours = pick_neighbours(case, p1)
    everyone: list[tuple[float, dict[int, float]]] = []
    for comp in case.get("comparables", []):
        parsed = release_day_ratios(comp)
        if parsed is not None:
            everyone.append(parsed)
    hours = []
    for row in case["forecast"]:
        hour = row["hour"]
        centre, spread = hour_centre_spread(neighbours, everyone, hour)
        quantiles = [
            clamp_quantile(p1 * math.exp(centre + z * spread))
            for z in Z_SCORES
        ]
        hours.append({"hour": hour, "q": quantiles})
    return {"hours": hours}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
