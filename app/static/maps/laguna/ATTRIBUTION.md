# Laguna street basemap

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
