"""
Fetch Lake Biwa outline from OpenStreetMap Overpass API and generate
frontend/src/data/lakes.ts
"""

import json
import math
import urllib.request
import urllib.parse
from typing import List, Tuple

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Lake Biwa relation ID on OpenStreetMap
BIWAKO_SEARCH_QUERY = """
[out:json][timeout:30];
(
  relation["name"="琵琶湖"]["type"="multipolygon"];
  way["name"="琵琶湖"]["natural"="water"];
  relation["name:ja"="琵琶湖"];
);
out ids tags;
"""

BIWAKO_QUERY = """
[out:json][timeout:60];
relation["name"="琵琶湖"]["natural"="water"];
out geom;
"""


def fetch_overpass(query: str) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        OVERPASS_URL, data=data,
        headers={
            "User-Agent": "generate_lakes.py/1.0 (local dev)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def rdp(points: List[Tuple[float, float]], epsilon: float) -> List[Tuple[float, float]]:
    if len(points) < 3:
        return points
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
        left = rdp(points[:max_idx + 1], epsilon)
        right = rdp(points[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [start, end]


def extract_outer_ring(element: dict) -> List[Tuple[float, float]]:
    """Extract the longest way from the relation members as the outer ring."""
    # Collect all way segments from members
    ways = []
    for member in element.get("members", []):
        if member.get("type") == "way" and member.get("role") in ("outer", ""):
            geom = member.get("geometry", [])
            if geom:
                ways.append([(n["lat"], n["lon"]) for n in geom])

    if not ways:
        raise ValueError("No outer ring found in relation")

    # Stitch ways into one ring
    ring = list(ways[0])
    used = {0}
    for _ in range(len(ways) - 1):
        last = ring[-1]
        best = None
        best_dist = float("inf")
        for j, way in enumerate(ways):
            if j in used:
                continue
            d0 = math.hypot(way[0][0] - last[0], way[0][1] - last[1])
            d1 = math.hypot(way[-1][0] - last[0], way[-1][1] - last[1])
            if d0 < best_dist:
                best_dist, best, reverse = d0, j, False
            if d1 < best_dist:
                best_dist, best, reverse = d1, j, True
        if best is not None:
            used.add(best)
            seg = ways[best]
            if reverse:
                seg = seg[::-1]
            ring.extend(seg[1:])

    return ring


def format_coord(lat: float, lng: float) -> str:
    return f"[{lat:.5f}, {lng:.5f}]"


def main():
    print("Searching for Lake Biwa on OSM...")
    search_result = fetch_overpass(BIWAKO_SEARCH_QUERY)
    for el in search_result.get("elements", []):
        print(f"  Found: type={el['type']} id={el['id']} tags={el.get('tags',{}).get('name','?')}")

    print("\nFetching Lake Biwa geometry...")
    result = fetch_overpass(BIWAKO_QUERY)

    elements = result.get("elements", [])
    relation = next((e for e in elements if e["type"] == "relation"), None)
    if not relation:
        print("ERROR: relation not found")
        return

    ring = extract_outer_ring(relation)
    print(f"  Raw ring: {len(ring)} points")

    simplified = rdp(ring, epsilon=0.003)
    # Close and drop duplicate
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    simplified = simplified[:-1]
    print(f"  Simplified: {len(simplified)} points")

    # Check bounding box
    lats = [p[0] for p in simplified]
    lngs = [p[1] for p in simplified]
    print(f"  Lat: {min(lats):.3f} - {max(lats):.3f}")
    print(f"  Lng: {min(lngs):.3f} - {max(lngs):.3f}")

    coord_strs = [f"    {format_coord(lat, lng)}" for lat, lng in simplified]

    ts = "\n".join([
        "export interface LakeData {",
        "  name: string;",
        "  coords: [number, number][]; // [lat, lng]",
        "}",
        "",
        "const LAKES: LakeData[] = [",
        "  {",
        '    name: "琵琶湖",',
        "    coords: [",
        ",\n".join(coord_strs),
        "    ],",
        "  },",
        "];",
        "",
        "export default LAKES;",
    ])

    out_path = "frontend/src/data/lakes.ts"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ts)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
