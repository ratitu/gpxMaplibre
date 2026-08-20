#!/usr/bin/env python3
"""Convert the GPX track to a GeoJSON LineString with [lon, lat, ele] coords."""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
GPX = os.path.join(HERE, "bomJesusPerdoes.gpx")
OUT = os.path.join(HERE, "track.geojson")

pattern = re.compile(r'<trkpt lat="([-\d.]+)" lon="([-\d.]+)">(?:<ele>([-\d.]+)</ele>)?')

coords = []
for m in pattern.finditer(open(GPX, encoding="utf-8").read()):
    lon, lat = float(m.group(2)), float(m.group(1))
    coord = [lon, lat]
    if m.group(3) is not None:
        coord.append(round(float(m.group(3)), 1))
    coords.append(coord)

geojson = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {"name": "Bom Jesus dos Perdoes track"},
        "geometry": {"type": "LineString", "coordinates": coords},
    }],
}

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(geojson, fh)

elev = [c[2] for c in coords if len(c) == 3]
print(f"Wrote {OUT}: {len(coords)} points"
      + (f", elevation {min(elev):.0f}..{max(elev):.0f} m" if elev else ""))
