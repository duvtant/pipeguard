"""Sensor ids and plain-English labels (verify against Saxena et al., 2008).

Owner: Olise. Spec: docs/techstack.md section 5.2.
Raw column names (s2, s3, ...) are for charts and code only. The manager UI and the voice agent
use LABELS, never the raw ids.
"""

# All 21 C-MAPSS sensor columns, in file order.
ALL_SENSORS: list[str] = [f"s{i}" for i in range(1, 22)]

# The 14 informative sensors kept for FD001. Flat sensors (s1, s5, s10, s16, s18, s19) and the
# near-constant s6 are dropped, as are the three operating settings.
SENSORS: list[str] = ["s2", "s3", "s4", "s7", "s8", "s9", "s11", "s12", "s13", "s14", "s15", "s17", "s20", "s21"]

DROPPED_SENSORS: list[str] = ["s1", "s5", "s6", "s10", "s16", "s18", "s19"]
SETTINGS: list[str] = ["setting1", "setting2", "setting3"]

# Column names for the raw NASA files: unit, cycle, setting1..3, s1..s21.
RAW_COLUMNS: list[str] = ["unit", "cycle", *SETTINGS, *ALL_SENSORS]

# C-MAPSS symbol per sensor (Saxena et al., 2008, table 2).
SYMBOLS: dict[str, str] = {
    "s2": "T24", "s3": "T30", "s4": "T50", "s7": "P30", "s8": "Nf", "s9": "Nc", "s11": "Ps30",
    "s12": "phi", "s13": "NRf", "s14": "NRc", "s15": "BPR", "s17": "htBleed", "s20": "W31", "s21": "W32",
}

LABELS: dict[str, str] = {
    "s2": "Low-pressure compressor outlet temperature",
    "s3": "High-pressure compressor outlet temperature",
    "s4": "Low-pressure turbine outlet temperature",
    "s7": "High-pressure compressor outlet pressure",
    "s8": "Fan speed",
    "s9": "Core speed",
    "s11": "High-pressure compressor static pressure",
    "s12": "Fuel flow to pressure ratio",
    "s13": "Corrected fan speed",
    "s14": "Corrected core speed",
    "s15": "Bypass ratio",
    "s17": "Bleed enthalpy",
    "s20": "High-pressure turbine coolant bleed",
    "s21": "Low-pressure turbine coolant bleed",
}


def label(sensor: str) -> str:
    """Plain-English label for a sensor id. Unknown ids get a neutral label, never the raw id."""
    return LABELS.get(sensor, "Sensor reading")
