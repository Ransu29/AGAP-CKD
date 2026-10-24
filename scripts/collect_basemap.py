#!/usr/bin/env python3
"""Prepare a small OSM-derived Laguna street basemap for local/offline serving.

OpenFreeMap permits area downloads <=3,000 tiles / 50 MB with <=4 concurrent
requests and an identifying User-Agent. This bounded pack follows those limits;
it does not download from tile.openstreetmap.org. See manifest.json for provenance.
"""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app/static/maps/laguna"
PREFIX = "/app/static/maps/laguna"
BOUNDS = (120.75, 13.75, 122.0, 14.95)
STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"
HEADERS = {"User-Agent": "AGAP-CKD-prototype/1.0 (+https://github.com/Ransu29/AGAP-CKD)"}
MAX_BYTES = 50_000_000
NOTICES = {
    "openfreemap.md": "https://raw.githubusercontent.com/hyperknot/openfreemap/main/LICENSE.md",
    "liberty.md": "https://raw.githubusercontent.com/maputnik/osm-liberty/gh-pages/LICENSE.md",
    "mapbox-open-styles.md": "https://raw.githubusercontent.com/mapbox/mapbox-gl-styles/master/LICENSE.md",
    "openmaptiles.md": "https://raw.githubusercontent.com/openmaptiles/openmaptiles/master/LICENSE.md",
    "noto-fonts.txt": "https://raw.githubusercontent.com/notofonts/noto-fonts/main/LICENSE",
    "maki.txt": "https://raw.githubusercontent.com/mapbox/maki/main/LICENSE.txt",
}
ATTRIBUTION = """# Laguna street basemap

[OpenFreeMap](https://openfreemap.org/) · [© OpenMapTiles](https://www.openmaptiles.org/)
· [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL 1.0).

Liberty style from OpenFreeMap, derived from OSM Liberty/OSM Bright/Mapbox Open
Styles (BSD 3-Clause code; attributed design). OpenMapTiles schema/design:
BSD 3-Clause / CC BY 4.0. Noto Sans glyphs: SIL Open Font License 1.1.
Maki icons: CC0. Upstream notices are retained in `licenses/`.

Local adaptations: remove the remote low-zoom Natural Earth raster; bound the
vector source to the downloaded Laguna region/zooms; resolve tile, font and
sprite URLs to this app. No basemap features enter the model or allocation.
Access distances remain straight-line assumptions, without road routing.

The provenance, source snapshot, retrieval time, byte counts and SHA-256 hashes
are recorded in `manifest.json`. Regenerate with `make collect-map`, subject to
[OpenFreeMap's area-download terms](https://openfreemap.org/tos/).
"""


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.content


def tiles(bounds, minimum=7, maximum=12):
    west, south, east, north = bounds
    for zoom in range(minimum, maximum + 1):
        def point(lon, lat):
            return (math.floor((lon + 180) / 360 * 2 ** zoom),
                    math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2 ** zoom))
        left, bottom = point(west, south)
        right, top = point(east, north)
        for x in range(left, right + 1):
            for y in range(top, bottom + 1):
                yield zoom, x, y


def main():
    style = json.loads(fetch(STYLE_URL))
    tilejson_url = style["sources"]["openmaptiles"]["url"]
    tilejson = json.loads(fetch(tilejson_url))
    coordinates = list(tiles(BOUNDS))
    if len(coordinates) > 3000:
        raise ValueError("The requested basemap exceeds OpenFreeMap's tile limit.")
    jobs = [(f"tiles/{z}/{x}/{y}.pbf", tilejson["tiles"][0].format(z=z, x=x, y=y)) for z, x, y in coordinates]
    fonts = {",".join(layer.get("layout", {}).get("text-font", [])) for layer in style["layers"]}
    fonts.discard("")
    for font in sorted(fonts):
        for start in (0, 256, 512, 768, 8192, 8448):
            span = f"{start}-{start + 255}"
            jobs.append((f"fonts/{font}/{span}.pbf", style["glyphs"].replace("{fontstack}", quote(font)).replace("{range}", span)))
    for suffix in (".json", ".png", "@2x.json", "@2x.png"):
        jobs.append(("sprite" + suffix, style["sprite"] + suffix))
    jobs.extend(("licenses/" + name, url) for name, url in NOTICES.items())
    # Natural Earth is a remote low-zoom raster layer; the bounded local pack
    # starts at z7 and uses only vector tiles. Keep all roads/place labels.
    style["layers"] = [layer for layer in style["layers"] if layer.get("source") == "openmaptiles" or not layer.get("source")]
    style["sources"] = {"openmaptiles": dict(type="vector", tiles=[PREFIX + "/tiles/{z}/{x}/{y}.pbf"],
        minzoom=7, maxzoom=12, bounds=list(BOUNDS), attribution=tilejson["attribution"])}
    style["glyphs"] = PREFIX + "/fonts/{fontstack}/{range}.pbf"
    style["sprite"] = PREFIX + "/sprite"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="laguna-map-", dir=OUTPUT.parent) as temporary:
        staging = Path(temporary)
        records, size = [], 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch, url): (name, url) for name, url in jobs}
            for future in concurrent.futures.as_completed(futures):
                name, url = futures[future]
                data = future.result()
                size += len(data)
                if size > MAX_BYTES:
                    for pending in futures:
                        pending.cancel()
                    raise ValueError("The local basemap exceeds the 50 MB area-download limit.")
                destination = staging / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                records.append(dict(path=name, url=url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
                if len(records) % 50 == 0:
                    print(f"Basemap: {len(records)}/{len(jobs)} assets, {size / 1e6:.1f} MB", flush=True)
        (staging / "style.json").write_text(json.dumps(style, ensure_ascii=False))
        manifest = dict(collected_utc=datetime.now(timezone.utc).isoformat(), style_url=STYLE_URL,
            tilejson_url=tilejson_url, tile_template=tilejson["tiles"][0], bounds=BOUNDS, minzoom=7, maxzoom=12,
            tile_count=len(coordinates), total_bytes=size, attribution=tilejson["attribution"],
            policy_url="https://openfreemap.org/tos/", concurrency=4, user_agent=HEADERS["User-Agent"],
            purpose="Basemap display only; not routing, facility verification or model input", assets=sorted(records, key=lambda row: row["path"]))
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (staging / "ATTRIBUTION.md").write_text(ATTRIBUTION)
        if OUTPUT.exists():
            # Only replace this collector's generated pack after every fetch succeeds.
            backup = OUTPUT.with_name("laguna-previous")
            if backup.exists():
                raise FileExistsError(f"Remove/review the previous collector backup first: {backup}")
            OUTPUT.rename(backup)
            try:
                shutil.copytree(staging, OUTPUT)
            except Exception:
                shutil.rmtree(OUTPUT, ignore_errors=True)
                backup.rename(OUTPUT)
                raise
            shutil.rmtree(backup)
        else:
            shutil.copytree(staging, OUTPUT)
    print(f"Prepared {len(coordinates)} vector tiles, {len(records)} assets, {size / 1e6:.1f} MB in {OUTPUT}")


if __name__ == "__main__":
    main()
