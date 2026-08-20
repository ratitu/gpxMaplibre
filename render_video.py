#!/usr/bin/env python3
"""render_video.py — animate the GPX track on the maplibre-gl 3D map and encode an MP4.

Drives animation.html (which exposes window.__anim.setFrame(fraction)) in headed
chromium on the active X display (hardware GL — ~0.5s/frame at 720p, vs ~15s/frame
with SwiftShader software rendering), captures each frame via page.screenshot()
(compositor PNG — maplibre's webgl2 context ignores canvasContextAttributes
preserveDrawingBuffer, so canvas toDataURL comes back black), and pipes the PNG
frames into ffmpeg (libx264).

Usage:
    python3 render_video.py [--fps 30] [--width 1920] [--height 1080] [--dur 15]
                            [--out gpx_animation.mp4] [--url http://127.0.0.1:8000/animation.html]
                            [--gpx bomJesusPerdoes.gpx]
"""

import argparse
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-gpu-sandbox",
    "--enable-unsafe-swiftshader",  # harmless fallback if HW GL is unavailable
]

# Advance the animation to fraction f and wait until the map settles
# (or at most 400ms — idle can stall while tiles stream). Returns nothing;
# the frame is captured from the compositor via page.screenshot().
PACER_FN = r"""
async (f) => {
    const idle = new Promise(res => window.__map.once('idle', res));
    const stall = new Promise(res => setTimeout(res, 400));  // cap: never hang on idle
    window.__anim.setFrame(f);
    await Promise.race([idle, stall]);
    await new Promise(r => setTimeout(r, 50));  // let WebGL present settle
}
"""

PREWARM_FN = r"""
(f) => window.__anim.setFrame(f)
"""


def gpx_real_seconds(gpx_path: str) -> float:
    """Real elapsed time of the GPX track from <time> tags (min..max)."""
    with open(gpx_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    stamps = re.findall(r"<time>([^<]+)</time>", text)
    if not stamps:
        return 0.0
    times = []
    for s in stamps:
        try:
            # 2023-12-17T09:10:35Z
            t = datetime.strptime(s.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            times.append(t.timestamp())
        except ValueError:
            continue
    if not times:
        return 0.0
    return max(times) - min(times)


def main() -> int:
    ap = argparse.ArgumentParser(description="Animate GPX track on maplibre-gl 3D map → MP4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--dur", type=float, default=15.0, help="video duration in seconds")
    ap.add_argument("--out", default="gpx_animation.mp4")
    ap.add_argument("--url", default="http://127.0.0.1:8000/animation.html")
    ap.add_argument("--gpx", default="bomJesusPerdoes.gpx")
    args = ap.parse_args()

    dur = max(5.0, min(60.0, args.dur))
    n_frames = int(round(args.fps * dur))

    real_secs = gpx_real_seconds(args.gpx)
    speed = real_secs / dur if real_secs > 0 else 0.0
    print(f"[render] gpx={args.gpx} real_secs={real_secs:.0f}s speed=×{speed:.1f} "
          f"frames={n_frames} @ {args.fps}fps {args.width}x{args.height} dur={dur:.0f}s")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "image2pipe",
        "-c:v", "png",
        "-framerate", str(args.fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        args.out,
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=CHROMIUM_ARGS)
        page = browser.new_page(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=1,
        )
        page.goto(args.url, wait_until="load", timeout=60000)
        page.wait_for_function("window.__anim && window.__anim.ready", timeout=60000)
        print("[render] animation engine ready — prewarming tile cache...")

        # Prewarm: walk the track a few times so terrain/basemap tiles are cached.
        for f in [i / 10 for i in range(11)]:
            page.evaluate(PREWARM_FN, f)
            page.wait_for_timeout(250)

        print(f"[render] encoding {n_frames} frames → {args.out}")
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        t0 = time.time()
        try:
            for i in range(n_frames):
                f = i / (n_frames - 1) if n_frames > 1 else 0.0
                page.evaluate(PACER_FN, f)
                shot = page.screenshot()
                proc.stdin.write(shot)
                if i % max(1, n_frames // 10) == 0:
                    el = time.time() - t0
                    print(f"[render] frame {i}/{n_frames} ({100 * i / n_frames:.0f}%) "
                          f"elapsed {el:.1f}s ({n_frames / max(el, 0.01) * (n_frames - i) / n_frames:.0f}s ETA)")
        finally:
            proc.stdin.close()
        rc = proc.wait()
        browser.close()

    if rc != 0:
        print(f"[render] FAILED: ffmpeg exit code {rc}", file=sys.stderr)
        return 1

    print(f"[render] done in {time.time() - t0:.1f}s → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())