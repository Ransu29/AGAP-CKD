"""OSM-derived display assets; never used for scoring, access or routing."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit

DIRECTORY = Path(__file__).resolve().parents[2] / "app/static/maps/laguna"
LOCAL_STYLE = "/app/static/maps/laguna/style.json"
REMOTE_STYLE = "https://tiles.openfreemap.org/styles/liberty"


def basemap_source(directory=DIRECTORY, browser_url=None, base_path=""):
    """A complete local pack keeps streets/labels available without internet."""
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
        complete = (directory / "style.json").is_file() and bool(manifest["assets"]) and all(
            (directory / asset["path"]).is_file() for asset in manifest["assets"])
    except (OSError, ValueError, KeyError):
        complete = False
    if not complete:
        return dict(style=REMOTE_STYLE, offline=False)
    if not browser_url:
        return dict(style=LOCAL_STYLE, offline=True)
    # Streamlit's bundled map renderer requires absolute glyph/sprite/tile URLs.
    # Resolve them against the actual browser origin, including a hosted prefix;
    # hard-coding localhost would break other ports and remote demo machines.
    parsed = urlsplit(browser_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("The basemap requires an HTTP(S) browser origin.")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    prefix = "/" + base_path.strip("/") if base_path.strip("/") else ""
    root = origin + prefix
    name = "style-runtime-" + hashlib.sha256(root.encode()).hexdigest()[:16] + ".json"
    destination = directory / name
    style = json.loads((directory / "style.json").read_text())
    style["glyphs"] = root + style["glyphs"]
    style["sprite"] = root + style["sprite"]
    for source in style["sources"].values():
        source["tiles"] = [root + url for url in source["tiles"]]
    content = json.dumps(style, ensure_ascii=False)
    if not destination.exists() or destination.read_text() != content:
        # Concurrent sessions may open the same origin; publish a complete file.
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False, encoding="utf-8") as handle:
            handle.write(content)
            temporary = handle.name
        os.replace(temporary, destination)
    return dict(style=root + LOCAL_STYLE.rsplit("/", 1)[0] + "/" + name, offline=True)
