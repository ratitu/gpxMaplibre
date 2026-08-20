#!/usr/bin/env python3
"""Generate terrarium-encoded XYZ PNG tiles from a DEM GeoTIFF.

Output: terrain_tiles/{z}/{x}/{y}.png  (Web Mercator XYZ scheme, 256 px)
Encoding: R = floor((h+32768)/256) % 256, G = (h+32768) % 256, B = frac*256
(decoded by MapLibre as h = (R*256 + G + B/256) - 32768)

Usage: tile_dem.py [zmin] [zmax]   (default 9 15)
"""
import math
import os
import sys

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

HERE = os.path.dirname(os.path.abspath(__file__))
DEM = os.path.join(HERE, "srtm_merged.tif")
OUT_DIR = os.path.join(HERE, "terrain_tiles")
TILE = 256

ZMIN, ZMAX = 9, 15


def x_of_lon(lon, z):
    return (lon + 180.0) / 360.0 * (2 ** z)


def y_of_lat(lat, z):
    lat = math.radians(lat)
    return (1.0 - math.asinh(math.tan(lat)) / math.pi) / 2.0 * (2 ** z)


def lon_of_x(x, z):
    return x / (2 ** z) * 360.0 - 180.0


def lat_of_y(y, z):
    n = math.pi * (1.0 - 2.0 * y / (2 ** z))
    return math.degrees(math.atan(math.sinh(n)))


def encode_terrarium(elev: np.ndarray) -> np.ndarray:
    """float32 elevation array -> RGB uint8 array in terrarium encoding."""
    v = np.clip(elev + 32768.0, 0.0, 65535.0)
    vf = np.floor(v)
    r = np.floor(vf / 256.0).astype(np.uint8)          # 0..255
    g = (vf - r.astype(np.float32) * 256.0).astype(np.uint8)  # 0..255
    b = np.floor((v - vf) * 256.0).astype(np.uint8)    # 0..255
    return np.stack([r, g, b], axis=-1)


def main():
    global ZMIN, ZMAX
    if len(sys.argv) > 2:
        ZMIN, ZMAX = int(sys.argv[1]), int(sys.argv[2])

    with rasterio.open(DEM) as src:
        dem = src.read(1).astype("float32")
        src_transform = src.transform
        src_crs = src.crs
        west, south, east, north = src.bounds
        nodata = src.nodata if src.nodata is not None else -32768.0
        valid = dem[dem != nodata]
        base = float(np.nanmin(valid)) if valid.size else 0.0
        dem[dem == nodata] = base
    print(f"DEM bounds: ({west:.5f}, {south:.5f}, {east:.5f}, {north:.5f})  fill={base:.1f}")

    total = 0
    for z in range(ZMIN, ZMAX + 1):
        # pad by 1 tile so pitched/neighbouring views are covered
        xmin = int(math.floor(x_of_lon(west, z))) - 1
        xmax = int(math.floor(x_of_lon(east, z))) + 1
        ymin = int(math.floor(y_of_lat(north, z))) - 1
        ymax = int(math.floor(y_of_lat(south, z))) + 1

        nx, ny = xmax - xmin + 1, ymax - ymin + 1
        W, H = nx * TILE, ny * TILE
        dst = np.full((H, W), base, dtype="float32")

        tgt_bounds = (
            lon_of_x(xmin, z),           # west
            lat_of_y(ymax + 1, z),       # south
            lon_of_x(xmax + 1, z),       # east
            lat_of_y(ymin, z),           # north
        )
        reproject(
            dem,
            dst,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=from_bounds(*tgt_bounds, W, H),
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
        )

        for dx in range(nx):
            for dy in range(ny):
                tile_elev = dst[dy * TILE:(dy + 1) * TILE, dx * TILE:(dx + 1) * TILE]
                rgb = encode_terrarium(tile_elev)
                path = os.path.join(OUT_DIR, str(z), str(xmin + dx), f"{ymin + dy}.png")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                Image.fromarray(rgb, "RGB").save(path, optimize=True)
                total += 1

        print(f"zoom {z}: tiles {xmin}..{xmax} x {ymin}..{ymax} ({nx * ny} tiles)")

    print(f"Done: {total} tiles in {OUT_DIR}")


if __name__ == "__main__":
    main()
