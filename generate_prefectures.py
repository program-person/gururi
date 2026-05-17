"""
Download prefecture GeoJSON from amay077/JapanPrefGeoJson and generate
frontend/src/data/prefectures.ts with simplified but accurate boundaries.

Target prefectures (Kinki + adjacent):
  24=三重, 25=滋賀, 26=京都, 27=大阪, 28=兵庫, 29=奈良, 30=和歌山
"""

import json
import math
import urllib.request
from typing import List, Tuple

BASE_URL = "https://raw.githubusercontent.com/amay077/JapanPrefGeoJson/master/prefs/{}.geojson"

PREFS = [
    (24, "三重",    "#fef9c3"),
    (25, "滋賀",    "#dcfce7"),
    (26, "京都",    "#ede9fe"),
    (27, "大阪",    "#fee2e2"),
    (28, "兵庫",    "#dbeafe"),
    (29, "奈良",    "#fce7f3"),
    (30, "和歌山",  "#ffedd5"),
]


def fetch_geojson(pref_id: int) -> dict:
    url = BASE_URL.format(pref_id)
    print(f"  Fetching {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def rdp(points: List[Tuple[float, float]], epsilon: float) -> List[Tuple[float, float]]:
    """Ramer-Douglas-Peucker simplification."""
    if len(points) < 3:
        return points
    # Find the point with the maximum distance from the line start→end
    start, end = points[0], points[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        dists = [math.hypot(p[0] - start[0], p[1] - start[1]) for p in points[1:-1]]
    else:
        dists = [abs(dx * (start[1] - p[1]) - (start[0] - p[0]) * dy) / length
                 for p in points[1:-1]]
    max_dist = max(dists)
    max_idx = dists.index(max_dist) + 1

    if max_dist > epsilon:
        left  = rdp(points[:max_idx + 1], epsilon)
        right = rdp(points[max_idx:],     epsilon)
        return left[:-1] + right
    else:
        return [start, end]


def extract_outer_ring(geometry: dict) -> List[Tuple[float, float]]:
    """
    Extract the largest outer ring from a Polygon or MultiPolygon.
    GeoJSON coords are [lng, lat] — we return (lat, lng) tuples.
    """
    rings: List[List[List[float]]] = []

    if geometry["type"] == "Polygon":
        rings = [geometry["coordinates"][0]]
    elif geometry["type"] == "MultiPolygon":
        # Collect all outer rings; pick the longest (main land)
        for poly in geometry["coordinates"]:
            rings.append(poly[0])
    else:
        raise ValueError(f"Unsupported geometry type: {geometry['type']}")

    # Pick the ring with the most points (= largest polygon = main land)
    outer = max(rings, key=len)
    # Convert [lng, lat] → (lat, lng)
    return [(c[1], c[0]) for c in outer]


def simplify_ring(ring: List[Tuple[float, float]], epsilon: float = 0.01) -> List[Tuple[float, float]]:
    """Simplify using RDP. epsilon is in degrees (~1 km at 0.01°)."""
    simplified = rdp(ring, epsilon)
    # Ensure ring is closed (first == last) and then drop last point
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    # Drop closing duplicate for TypeScript array
    return simplified[:-1]


def format_coord(lat: float, lng: float) -> str:
    return f"[{lat:.5f}, {lng:.5f}]"


def generate_ts(prefs_data: list) -> str:
    lines = [
        'export interface PrefectureData {',
        '  name: string;',
        '  fill: string;',
        '  coords: [number, number][]; // [lat, lng]',
        '}',
        '',
        'const PREFECTURES: PrefectureData[] = [',
    ]

    for name, fill, coords in prefs_data:
        coord_strs = [f"    {format_coord(lat, lng)}" for lat, lng in coords]
        lines.append(f'  {{')
        lines.append(f'    name: "{name}",')
        lines.append(f'    fill: "{fill}",')
        lines.append(f'    coords: [')
        lines.append(',\n'.join(coord_strs))
        lines.append(f'    ],')
        lines.append(f'  }},')

    lines.append('];')
    lines.append('')
    lines.append('export default PREFECTURES;')
    return '\n'.join(lines)


def main():
    print("Generating prefecture boundary data...")
    prefs_data = []

    for pref_id, name, fill in PREFS:
        print(f"\n[{pref_id}] {name}")
        try:
            geo = fetch_geojson(pref_id)

            # Support both Feature and FeatureCollection
            if geo["type"] == "Feature":
                geometry = geo["geometry"]
            elif geo["type"] == "FeatureCollection":
                geometry = geo["features"][0]["geometry"]
            else:
                geometry = geo  # raw geometry

            ring = extract_outer_ring(geometry)
            print(f"  Original ring: {len(ring)} points")

            simplified = simplify_ring(ring, epsilon=0.015)
            print(f"  Simplified:    {len(simplified)} points")

            prefs_data.append((name, fill, simplified))
        except Exception as e:
            print(f"  ERROR: {e}")
            raise

    ts_content = generate_ts(prefs_data)

    out_path = "frontend/src/data/prefectures.ts"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ts_content)

    print(f"\nWrote {out_path}")
    total_pts = sum(len(c) for _, _, c in prefs_data)
    print(f"Total points: {total_pts}")


if __name__ == "__main__":
    main()
