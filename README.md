# GPX MapLibre — 3D Terrain Animation

GPX → MapLibre 3D terrain demo for **Bom Jesus dos Perdões** (SP, Brazil). A Python
pipeline turns an SRTM elevation model and a GPS track into a local, self-contained
3D map (no map API keys required), served as two static HTML pages:

- **`index.html`** — interactive 3D viewer with terrain exaggeration, elevation
  profile, and track statistics
- **`animation.html`** — headless-renderable camera animation page used to produce
  a video of the track flyover

## Pipeline

```
bomJesusPerdoes.gpx ──┬─ download_srtm.py ──> srtm_merged.tif ──> tile_dem.py ──> terrain_tiles/{z}/{x}/{y}.png
                      └─ gpx2geojson.py ────> track.geojson
track.geojson + terrain_tiles + bomJesusPerdoes.gpx ──> animation.html ──> render_video.py ──> gpx_animation.mp4
```

| Step | Script | Input | Output |
|---|---|---|---|
| DEM download | `download_srtm.py` | `bomJesusPerdoes.gpx` | `srtm_merged.tif` |
| GPX → GeoJSON | `gpx2geojson.py` | `bomJesusPerdoes.gpx` | `track.geojson` |
| Terrain tiles | `tile_dem.py` | `srtm_merged.tif` | `terrain_tiles/{z}/{x}/{y}.png` |
| Video render | `render_video.py` | `animation.html` + data files | `gpx_animation.mp4` |

- **Elevation data**: SRTMGL1 1-arc-sec `.hgt.gz` from the AWS Open Data *skadi*
  bucket, with a Copernicus DEM 30m COG fallback; merged/cropped to
  `srtm_merged.tif` (WGS84, float32, nodata `-32768`, voids filled) via
  `gdalbuildvrt` + `gdalwarp` + `gdal_fillnodata`.
- **Terrain tiles**: Web Mercator XYZ PNGs, 256 px, [Terrarium](https://github.com/tilezen/joerd/blob/master/docs/formats.md#terrarium)
  encoded (`R=floor((h+32768)/256)%256, G=(h+32768)%256, B=frac*256`) and decoded by
  MapLibre `raster-dem` with `encoding: 'terrarium'`.

## Requirements

- Python 3 with `rasterio`, `numpy`, `Pillow`
- GDAL command-line tools (`gdalbuildvrt`, `gdalwarp`, `gdal_fillnodata`)
- `ffmpeg` (video rendering only)
- Playwright with Chromium (video rendering only)

## Setup

```bash
# 1. Download & merge the DEM covering the track
python3 download_srtm.py

# 2. Convert the GPX track to GeoJSON
python3 gpx2geojson.py

# 3. Generate terrarium terrain tiles (zoom range defaults to 9..15)
python3 tile_dem.py            # or: python3 tile_dem.py 9 15
```

## Viewing

Serve the project directory from any static file server and open `index.html`:

```bash
python3 -m http.server 8000
# → http://localhost:8000/index.html
```

The page loads `track.geojson`, `bomJesusPerdoes.gpx`, and the local
`terrain_tiles/` at runtime — no network map APIs required beyond the MapLibre
library and basemap tiles.

## Rendering the animation video

```bash
python3 render_video.py --gpx bomJesusPerdoes.gpx --out gpx_animation.mp4
```

`render_video.py` drives a headed Chromium via Playwright, advances the camera
through `window.__anim.setFrame(fraction)`, captures frames with
`page.screenshot()`, and encodes them with ffmpeg (`libx264`, `yuv420p`).

## Project structure

```
bomJesusPerdoes.gpx   # source track (input)
download_srtm.py      # DEM download + GDAL merge/crop
gpx2geojson.py        # GPX -> track.geojson
tile_dem.py           # DEM -> terrarium XYZ tiles
render_video.py       # Playwright + ffmpeg video render
index.html            # interactive 3D viewer
animation.html        # headless-renderable animation page
track.geojson         # derived, consumed by both pages
srtm_src/             # downloaded .hgt sources (generated)
srtm_merged.tif       # merged DEM (generated)
terrain_tiles/        # generated XYZ PNG tiles
gpx_animation.mp4     # rendered video (generated)
deploy-site/          # Apache deployment copy
```

Generated artifacts (`srtm_src/`, `srtm_merged.tif`, `terrain_tiles/`,
`gpx_animation.mp4`) are gitignored.

## Deploying to Apache

The repo ships a ready-to-copy deployment layout in `deploy-site/` plus a vhost
config (`deploy-site/gpxmaplibre.conf`) following the local named-vhost pattern:

```bash
sudo cp deploy-site/gpxmaplibre.conf /etc/apache2/sites-available/
sudo a2ensite gpxmaplibre
sudo systemctl reload apache2
```

The site is served at `http://gpxmaplibre/` (requires a `gpxmaplibre → <host-ip>`
entry in your hosts/DNS). Note that `deploy-site/` is a copy, not a symlink —
re-copy updated files after changing the root versions.