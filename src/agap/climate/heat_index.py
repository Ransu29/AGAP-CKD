"""Heat index from air temperature and relative humidity (NWS algorithm, as used by PAGASA)."""
from __future__ import annotations

import numpy as np


def heat_index_c(temperature_c, humidity_pct):
    """NWS heat index (Rothfusz 1990 with the NWS low/high humidity adjustments), in degrees Celsius.

    Below 80 F the simple Steadman form is used, as in the NWS algorithm."""
    t = np.asarray(temperature_c, float) * 9 / 5 + 32
    rh = np.asarray(humidity_pct, float)
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    full = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
            - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
    low_rh = (rh < 13) & (t >= 80) & (t <= 112)
    full = np.where(low_rh, full - ((13 - rh) / 4) * np.sqrt(np.clip((17 - np.abs(t - 95)) / 17, 0, None)), full)
    high_rh = (rh > 85) & (t >= 80) & (t <= 87)
    full = np.where(high_rh, full + ((rh - 85) / 10) * ((87 - t) / 5), full)
    hi_f = np.where((simple + t) / 2 >= 80, full, simple)
    return (hi_f - 32) * 5 / 9
