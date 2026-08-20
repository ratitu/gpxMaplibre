#!/usr/bin/env python3
"""Download SRTM DEM covering the GPX track bounds and merge/crop to a GeoTIFF.

Sources (tried in order):
  1. SRTMGL1 1-arc-second (~30 m) .hgt.gz from the AWS Open Data "skadi" bucket
     (https://s3.amazonaws.com/elevation-tiles-prod/skadi/...)
  2. Copernicus DEM 30 m COG GeoTIFF from the public AWS bucket
     (https://copernicus-dem-30m.s3.amazonaws.com/...)

Output: srtm_merged.tif (WGS84, float32, nodata=-32768, voids filled).
"""
import math
import os
import re
import sys
import gzip
import shutil
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GPX = os.path.join(HERE, "bomJesusPerdoes.gpx")
OUT_TIF = os.path.join(HERE, "srtm_merged.tif")
MARGIN_DEG = 0.008  # ~0.9 km buffer around the track

SRTM_BASE = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"
COPERNICUS_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"


def parse_bounds(gpx_path):
    data = open(gpx_path, encoding="utf-8").read()
    pts = re.findall(r'<trkpt lat="([-\d.]+)" lon="([-\d.]+)"', data)
    if not pts:
        sys.exit("No <trkpt> found in GPX")
    lats = [float(p[0]) for p in pts]
    lons = [float(p[1]) for p in pts]
    return min(lats), max(lats), min(lons), max(lons)


def bands_intersecting(vmin, vmax):
    """Integer 1-degree bands [k, k+1] intersecting [vmin, vmax] (inclusive range)."""
    return range(math.floor(vmin), math.floor(vmax) + 1)


def srtm_tile_names(lat_min, lat_max, lon_min, lon_max):
    """1x1-degree SRTM tile names whose SW-corner lat/lon bands intersect the bbox."""
    tiles = set()
    for lat in bands_intersecting(lat_min, lat_max):
        for lon in bands_intersecting(lon_min, lon_max):
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            tiles.add(f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}")
    return sorted(tiles)


def download(url, dest, retries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"  cached: {dest}")
        return True
    for i in range(retries):
        try:
            print(f"  GET {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "gpx-srtm-demo/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  attempt {i + 1} failed: {exc}")
    return False


def run(cmd):
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    lat_min, lat_max, lon_min, lon_max = parse_bounds(GPX)
    print(f"Track bbox: lat [{lat_min:.6f}, {lat_max:.6f}]  lon [{lon_min:.6f}, {lon_max:.6f}]")

    tiles = srtm_tile_names(lat_min, lat_max, lon_min, lon_max)
    print(f"SRTM tiles needed: {tiles}")

    workdir = os.path.join(HERE, "srtm_src")
    os.makedirs(workdir, exist_ok=True)
    hgt_files = []

    # ---- try SRTMGL1 skadi first ----
    for tile in tiles:
        lat_band = tile[:3]  # e.g. S23
        url = f"{SRTM_BASE}/{lat_band}/{tile}.hgt.gz"
        gz = os.path.join(workdir, f"{tile}.hgt.gz")
        hgt = os.path.join(workdir, f"{tile}.hgt")
        if not download(url, gz):
            continue
        try:
            with gzip.open(gz, "rb") as fin, open(hgt, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            hgt_files.append(hgt)
        except Exception as exc:  # noqa: BLE001
            print(f"  corrupt gzip for {tile}: {exc}")

    # ---- fallback: Copernicus DEM 30 m COG ----
    if not hgt_files:
        print("SRTM skadi download failed -> falling back to Copernicus DEM 30m COG")
        for lat in bands_intersecting(lat_min, lat_max):
            for lon in bands_intersecting(lon_min, lon_max):
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"
                name = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
                url = f"{COPERNICUS_BASE}/{name}/{name}.tif"
                tif = os.path.join(workdir, f"{name}.tif")
                if download(url, tif):
                    hgt_files.append(tif)

    if not hgt_files:
        sys.exit("FATAL: could not download any elevation data")

    # ---- merge + crop ----
    west = lon_min - MARGIN_DEG
    east = lon_max + MARGIN_DEG
    south = lat_min - MARGIN_DEG
    north = lat_max + MARGIN_DEG

    vrt = os.path.join(workdir, "mosaic.vrt")
    run(["gdalbuildvrt", "-overwrite", vrt] + hgt_files)
    run([
        "gdalwarp", "-overwrite",
        "-t_srs", "EPSG:4326",
        "-r", "bilinear",
        "-te", f"{west:.6f}", f"{south:.6f}", f"{east:.6f}", f"{north:.6f}",
        "-dstnodata", "-32768",
        "-of", "GTiff",
        vrt, OUT_TIF,
    ])
    run(["gdal_fillnodata", "-md", "40", OUT_TIF, OUT_TIF])
    print(f"Wrote {OUT_TIF}")


if __name__ == "__main__":
    main()
