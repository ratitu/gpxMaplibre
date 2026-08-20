# PROJECT KNOWLEDGE BASE

Generated: 2026-08-20 | Commit: b022548 | Branch: main | Public: github.com/ratitu/gpxMaplibre

## OVERVIEW

GPX → MapLibre 3D terrain demo for Bom Jesus dos Perdões (SP-BR). Python pipeline
(SRTM DEM → terrarium tiles, GPX → GeoJSON) feeds two static MapLibre GL JS pages
(interactive viewer + camera animation). UI text is pt-BR.

## STRUCTURE

```
bomJesusPerdoes.gpx   # source track (input to pipeline)
download_srtm.py      # SRTM DEM download + GDAL merge/crop -> srtm_merged.tif
gpx2geojson.py        # GPX -> track.geojson ([lon,lat,ele])
tile_dem.py           # srtm_merged.tif -> terrain_tiles/{z}/{x}/{y}.png (terrarium)
render_video.py       # Playwright + ffmpeg: animation.html -> gpx_animation.mp4
index.html            # interactive 3D viewer (elevation profile, exaggeration, stats)
animation.html        # headless-renderable animation page (window.__anim API)
track.geojson         # derived, consumed by both pages
srtm_src/             # downloaded .hgt/.hgt.gz (generated)
srtm_merged.tif       # merged DEM (generated, gitignored)
terrain_tiles/        # XYZ PNG tiles (generated, gitignored)
deploy-site/          # Apache deployment copy (own index/animation/geojson/gpx/tiles + vhost conf)
gpx_animation.mp4     # rendered video (generated, gitignored; NOT referenced by any HTML)
```

## WHERE TO LOOK

| Need | File |
|---|---|
| DEM download / merge | download_srtm.py |
| Tile generation / terrarium | tile_dem.py |
| GPX → GeoJSON | gpx2geojson.py |
| Video render | render_video.py |
| Interactive 3D page | index.html |
| Animation page (headless) | animation.html |
| Apache deployment | deploy-site/ + /etc/apache2/sites-available/gpxmaplibre.conf |

## CODE MAP

- `parse_bounds(gpx_path)` — regex `<trkpt lat= lon=>` → (min_lat,max_lat,min_lon,max_lon); sys.exit if none (download_srtm.py)
- `srtm_tile_names(lat,lon ranges)` — 1x1-deg SW-corner names `N{S}23W{047}` sorted (download_srtm.py)
- `download(url,dest,retries=3)` — cache-skip if exists+size>0; urllib UA "gpx-srtm-demo/1.0", timeout 60 (download_srtm.py)
- `run(cmd)` — echo + subprocess.run(check=True) for gdalbuildvrt/gdalwarp/gdal_fillnodata (download_srtm.py)
- `x_of_lon/y_of_lat/lon_of_x/lat_of_y(z)` — Web Mercator math (tile_dem.py)
- `encode_terrarium(elev)` — float32 → RGB uint8; R=(h+32768)//256%256, G=(h+32768)%256, B=frac*256 (tile_dem.py)
- `render_video.py` — argparse CLI (`--gpx`, `--out`); headed Chromium `page.screenshot()` compositor capture; ffmpeg libx264 yuv420p image2pipe
- `window.__anim.setFrame(fraction)` / `window.__anim.ready` — headless control surface on animation.html
- `window.__map` — MapLibre instance exposed by both pages

## PIPELINE

```
bomJesusPerdoes.gpx ──┬─ download_srtm.py ──> srtm_merged.tif ──> tile_dem.py ──> terrain_tiles/{z}/{x}/{y}.png
                     └─ gpx2geojson.py ────> track.geojson
track.geojson + terrain_tiles + bomJesusPerdoes.gpx ──> animation.html ──> render_video.py ──> gpx_animation.mp4
```

## CONVENTIONS

- All scripts derive paths from `HERE = os.path.dirname(os.path.abspath(__file__))`; never CWD-relative.
- CLI style: only render_video.py uses argparse; others hardcode defaults or take positional `sys.argv` (tile_dem.py `[zmin] [zmax]`, default 9 15).
- GeoJSON coords are `[lon, lat, ele]`; elevation optional, rounded to 1 decimal.
- Terrain tiles: 256px, Web Mercator XYZ, `encoding: 'terrarium'` in MapLibre `raster-dem`.
- HTTP: stdlib `urllib.request` only (no requests); retries=3, timeout=60, custom UA.
- Video: `page.screenshot()` (compositor), not canvas toDataURL — documented choice; ffmpeg via image2pipe.
- HTML: no bundler; inline scripts; MapLibre pinned `maplibre-gl@4.7.1` from unpkg; basemap Esri World Imagery raster.
- Shared JS (both pages): haversine distance, 9-color elevation ramp with 25m bucketed gradient stops, 50m-rounded adaptive ramp bounds.

## ANTI-PATTERNS

- Fixed repo filenames baked into scripts (bomJesusPerdoes.gpx, srtm_merged.tif, track.geojson) — intentional for a demo, but scripts are not reusable per-track without edits.
- Broad `except Exception ... # noqa: BLE001` in download_srtm.py (lines ~67, ~100).
- gpx2geojson.py runs at module import time (no `if __name__ == "__main__"` guard).
- tile_dem.py mutates module globals via `global ZMIN, ZMAX` for CLI values.
- Frontend fetches `bomJesusPerdoes.gpx` at runtime in addition to track.geojson — page is coupled to the exact source filename.
- Do NOT commit generated data: srtm_src/, srtm_merged.tif, terrain_tiles/, gpx_animation.mp4, *.pyc, __pycache__/ (all in .gitignore).
- Do NOT reference gpx_animation.mp4 from HTML — it is render output only.
- Agent has no passwordless sudo; Apache changes require the user to run the sudo command.

## UNIQUE STYLES

- Pipeline is file-artifact-driven (each script consumes a named file on disk, no shared state).
- Animation is a headless-renderable HTML page exposing a JS API to Playwright — rendering logic lives in the browser page, not the Python script.
- No tests, no CI, no config files — scripts are top-level with python3 shebang.

## COMMANDS

```
python3 download_srtm.py                 # fetch DEM + merge to srtm_merged.tif (needs GDAL)
python3 tile_dem.py [zmin] [zmax]        # srtm_merged.tif -> terrain_tiles (default 9 15)
python3 gpx2geojson.py                   # bomJesusPerdoes.gpx -> track.geojson
python3 render_video.py --gpx bomJesusPerdoes.gpx --out gpx_animation.mp4
```

## NOTES

- Live at `http://gpxmaplibre/` (Apache named vhost → deploy-site/); plain-IP access is intercepted by the queimadas Streamlit proxy on 192.168.15.3.
- deploy-site/ is a deployment copy, not a symlink — edits to root files must be re-copied or applied twice.
- Codegraph index available at .codegraph (symlink).