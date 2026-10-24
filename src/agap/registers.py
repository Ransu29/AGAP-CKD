"""PhilHealth facility registers: parse the published lists and record clinic locations honestly.

Both registers (freestanding dialysis clinics; YAKAP primary-care clinics) list names, contacts,
street and municipality, not coordinates. A clinic's position comes from a matching OpenStreetMap
feature when one exists, otherwise from its barangay or municipality centre, and every row says
which. Accreditation does not establish current capacity, opening hours, cost, test capability
or acceptance of new patients.
"""
from __future__ import annotations

import math
import re
import unicodedata

import pandas as pd

REGISTERS = {
    "dialysis": dict(
        register_id="FDC-20260930", raw="data/raw/dialysis/FDC_093026.pdf",
        osm="data/raw/dialysis/osm/laguna_dialysis_overpass.json", output="dialysis_clinics",
        title="List of Accredited Freestanding Dialysis Clinics for CY 2026, updated as of September 30, 2026",
        url="https://www.philhealth.gov.ph/partners/providers/facilities/accredited/FDC_093026.pdf"),
    "yakap": dict(
        register_id="YAKAP-20260930", raw="data/raw/philhealth/YAKAP.pdf",
        osm="data/raw/philhealth/osm/laguna_health_overpass.json", output="yakap_clinics",
        title="List of Accredited YAKAP Clinics for CY 2026, updated as of September 30, 2026",
        url="https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf"),
}
REGISTER_ID = REGISTERS["dialysis"]["register_id"]
REGISTER_TITLE = REGISTERS["dialysis"]["title"]
REGISTER_URL = REGISTERS["dialysis"]["url"]
COLUMNS = ["entry", "province", "name", "telephone", "email", "street", "municipality", "accreditation_expiry", "sector"]
LOCATION_PRECISION = {
    "osm": "Mapped building or point (OpenStreetMap)",
    "barangay": "Approximate: barangay centre",
    "municipality": "Approximate: municipality centre",
}
_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_ENTRY = re.compile(r"^\s*(\d{1,4})\s+(\S.*)$")  # entry lines must also carry an expiry date
_SKIP = ("List of Accredited", "NAME OF HEALTH FACILITY", "Page ")
_BARANGAY = re.compile(r"\b(?:BRGY|BGY|BARANGAY)\.?\s*([A-ZÑ0-9 .'()-]+?)(?:,|$)", re.IGNORECASE)


def _fields(line):
    return [(match.start(), match.group()) for match in re.finditer(r"\S+(?: \S+)*", line)]


def _is_heading(line):
    text = line.strip()
    return bool(text) and text == text.upper() and not any(ch.isdigit() for ch in text) and "@" not in text \
        and len(line) - len(line.lstrip()) <= 6 and not text.startswith(_SKIP)


def parse_register(lines):
    """Rows from layout-extracted register text; wrapped street/email lines join their entry."""
    rows, province, current = [], None, None
    for line in lines:
        if not line.strip() or line.strip().startswith(_SKIP):
            continue
        # Keep the expiry date its own field even when the layout leaves one space before it.
        line = re.sub(r"(?<=\S) (\d{1,2}/\d{1,2}/\d{4})\b", r"  \1", line)
        entry = _ENTRY.match(line)
        parts = _fields(line) if entry else []
        texts = [text for _, text in parts]
        date_index = next((i for i, text in enumerate(texts) if _DATE.match(text)), None)
        if entry and date_index is not None and date_index >= 2:
            sector = texts[date_index + 1] if date_index + 1 < len(texts) else ""
            municipality = texts[date_index - 1]
            # The entry number may share a field with the name ("607 NAME") or stand alone ("610", "NAME").
            if re.fullmatch(r"\d+", texts[0]):
                name, middle = texts[1], parts[2:date_index - 1]
            else:
                name, middle = re.sub(r"^\d+\s+", "", texts[0]), parts[1:date_index - 1]
            email = next((text for _, text in middle if "@" in text), "")
            telephone = next((text for _, text in middle if "@" not in text and sum(c.isdigit() for c in text) >= 7), "")
            street_parts = [(start, text) for start, text in middle if text not in (email, telephone)]
            current = dict(entry=int(entry.group(1)), province=province, name=name, telephone=telephone, email=email,
                           street=" ".join(text for _, text in street_parts), municipality=municipality,
                           accreditation_expiry=texts[date_index], sector=sector,
                           _street_col=street_parts[0][0] if street_parts else None,
                           _email_col=next((start for start, text in middle if "@" in text), None))
            rows.append(current)
            continue
        if _is_heading(line):
            province, current = line.strip(), None
            continue
        if current is None:
            continue
        for start, text in _fields(line):
            near_street = current["_street_col"] is not None and start >= current["_street_col"] - 3
            if text.startswith(".") or (current["_email_col"] is not None and abs(start - current["_email_col"]) <= 3 and not near_street):
                current["email"] += text
            else:
                current["street"] = f"{current['street']} {text}".strip()
    frame = pd.DataFrame(rows, columns=COLUMNS + ["_street_col", "_email_col"])
    return frame[COLUMNS]


def barangay_name(street):
    match = _BARANGAY.search(str(street))
    return re.sub(r"\s+", " ", match.group(1)).strip(" .") if match else None


# Words shared by many facilities; matching on them pairs different clinics ("Paete RHU" with "Pangil RHU").
GENERIC_WORDS = frozenset("""rural health unit rhu center centre hospital hospitals medical clinic clinics city office
    inc incorporated corp corporation co the and of philippines dialysis municipal general diagnostic diagnostics
    laboratory laboratories care healthcare services service management""".split())
# Facility kinds; a register clinic only matches an OSM feature of a compatible kind when both names show one.
FACILITY_KINDS = {
    "primary": ("rural health", "rhu", "health center", "health centre", "health office", "health unit", "municipal health"),
    "hospital": ("hospital", "medical center", "medical centre"),
    "clinic": ("clinic", "diagnostic", "laboratory", "laboratories"),
    "maternity": ("lying-in", "lying in", "birthing", "bemonc", "maternity"),
    "dialysis": ("dialysis", "renal", "kidney", "nephro"),
}


ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "i": "i", "v": "v"}


def name_tokens(text):
    """Distinctive name words: accents folded, Sta./Sto./St. expanded, generic facility words and initials dropped."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\bsta\b\.?", "santa", text)
    text = re.sub(r"\bsto\b\.?", "santo", text)
    text = re.sub(r"\bst\b\.?", "saint", text)
    words = re.sub(r"[^a-z0-9 ]", " ", text.replace("'", "")).split()
    # Unit numbers distinguish branches ("RHU I" vs "RHU 2"): keep them, written as roman numerals.
    words = [ROMAN.get(word, word) for word in words]
    return frozenset(word for word in words if word not in GENERIC_WORDS and (len(word) > 1 or word in ROMAN.values()))


def facility_kinds(text):
    text = re.sub(r"\s+", " ", str(text).lower())
    return frozenset(kind for kind, words in FACILITY_KINDS.items() if any(re.search(rf"\b{re.escape(w)}", text) for w in words))


def same_facility(register_name, osm_name, min_similarity=.65):
    """Conservative match: every distinctive register word appears in the OSM name, names overlap
    enough, and their facility kinds agree when both show one."""
    register, other = name_tokens(register_name), name_tokens(osm_name)
    kinds, other_kinds = facility_kinds(register_name), facility_kinds(osm_name)
    return (bool(register) and register <= other and name_similarity(register_name, osm_name) >= min_similarity
            and (not kinds or not other_kinds or bool(kinds & other_kinds)))


def name_similarity(left, right):
    """Jaccard overlap of distinctive words; 0 when either name has none."""
    a, b = name_tokens(left), name_tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.


def _distance_km(lat1, lon1, lat2, lon2):
    to_rad = math.pi / 180
    a = (math.sin((lat2 - lat1) * to_rad / 2) ** 2
         + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin((lon2 - lon1) * to_rad / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def match_osm(clinics, features, anchors, min_similarity=.65, max_km=8.):
    """Attach an OSM feature when its distinctive name words agree and it lies near the clinic's area anchor.

    ``anchors`` gives an approximate (lat, lon) per clinic index; a name match far from it is rejected,
    because chains (NephroCare, B. Braun Avitum, KidneyCare) have several branches.
    """
    matches = {}
    used = set()
    for index, clinic in clinics.iterrows():
        anchor = anchors.get(index)
        best = None
        for feature in features:
            name = feature.get("name")
            if not name or feature["id"] in used:
                continue
            if not same_facility(clinic["name"], name, min_similarity):
                continue
            similarity = name_similarity(clinic["name"], name)
            if anchor is not None and _distance_km(anchor[0], anchor[1], feature["lat"], feature["lon"]) > max_km:
                continue
            if best is None or similarity > best[0]:
                best = (similarity, feature)
        if best:
            used.add(best[1]["id"])
            matches[index] = best[1]
    return matches


def load_clinics(root, register="dialysis"):
    """Prepared Laguna clinic table, or None when scripts/prepare_clinic_locations.py has not been run."""
    path = root / "data/processed/public/laguna" / f"{REGISTERS[register]['output']}.csv"
    return pd.read_csv(path) if path.exists() else None


def _plain_name(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"\bSTA\.?\s", "SANTA ", text)
    text = re.sub(r"\bSTO\.?\s", "SANTO ", text)
    text = re.sub(r"\b(CITY OF|CITY)\b", " ", text)
    return " ".join(re.sub(r"[^A-Z ]", " ", text).split())


def boundary_name(register_municipality, boundary_names):
    """The boundary shapeName for a register municipality spelling ("STA. ROSA" -> "City of Santa Rosa")."""
    wanted = _plain_name(register_municipality)
    matches = [name for name in boundary_names if _plain_name(name) == wanted]
    if len(matches) != 1:
        raise ValueError(f"No unique boundary for register municipality {register_municipality!r}: {matches}")
    return matches[0]


def display_text(value):
    """Title-case register text without breaking ordinals ("2ND FLR" -> "2nd Flr")."""
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), str(value).title())
