"""大回りルートの区間ごとの時刻表組み立て。

ルートの path を同一路線の連続区間（レッグ）に分割し、レッグごとに
transit.ls8h.com API（transit.py）で実ダイヤを照会する。
未収録路線（奈良線 D・関西空港線 S・JR東西線区間）や API 障害時は、
運転間隔テーブルによる期待値ベースの推定にフォールバックする。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import transit
from app.graph import Adjacency
from app.models import PathSegment, TimetableLeg, TimetableResponse

# 日中のおおよその運転間隔（分）。推定時の期待待ち時間 = 間隔 / 2
HEADWAY_MIN: dict[str, float] = {
    "O": 4, "A": 8, "G": 8, "H": 8, "Q": 10, "F": 15, "R": 8,
    "D": 15, "B": 15, "C": 30, "V": 60, "E": 10, "U": 30, "T": 30,
    "S": 15, "HA": 15, "I": 30,
}
DEFAULT_HEADWAY_MIN = 20.0
TRANSFER_WALK_MIN = 3.0
# 実ダイヤ照会時、乗換では前レッグ到着からこの分数以降に出る列車を探す
TRANSFER_BUFFER_MIN = 2.0

# 路線ID -> 駅ID -> transit API 駅ID（scripts/build_transit_station_map.py で生成）
TransitMap = dict[str, dict[str, str]]


def load_transit_map(path: Path) -> TransitMap:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("map", {})


@dataclass(frozen=True)
class Leg:
    line_id: str
    station_ids: tuple[str, ...]  # 乗車駅〜下車駅（中間駅含む）


def split_legs(path: list[PathSegment]) -> list[Leg]:
    """path（先頭要素の lineId は空）を同一路線の連続区間に分割する。"""
    legs: list[Leg] = []
    cur_line: str | None = None
    cur: list[str] = []
    for i, seg in enumerate(path):
        if i == 0:
            cur = [seg.station_id]
            continue
        if cur_line is not None and seg.line_id != cur_line:
            legs.append(Leg(cur_line, tuple(cur)))
            cur = [cur[-1]]
        cur_line = seg.line_id
        cur.append(seg.station_id)
    if cur_line is not None and len(cur) >= 2:
        legs.append(Leg(cur_line, tuple(cur)))
    return legs


def _edge_minutes(adj: Adjacency, u: str, v: str, line_id: str) -> float:
    fallback = 0.0
    for nb, lid, _dist, t in adj.get(u, []):
        if nb == v:
            if lid == line_id:
                return t
            fallback = t
    return fallback


def _ride_minutes(adj: Adjacency, leg: Leg) -> float:
    return sum(
        _edge_minutes(adj, a, b, leg.line_id)
        for a, b in zip(leg.station_ids, leg.station_ids[1:])
    )


def _parse_hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


def _fmt(secs: int) -> str:
    return f"{(secs // 3600) % 24:02d}:{(secs % 3600) // 60:02d}"


def _pick_direct(data: dict[str, Any]) -> tuple[int, int, str | None, str | None] | None:
    """乗換なし（= 指定路線をそのまま乗る）最速の旅程を選ぶ。

    レッグの両端駅は同一路線のものを渡しているため、乗換0の旅程は
    その路線の列車とみなせる。乗換ありしか返らない場合は None
    （プランナーが別経路に迂回した = 大回りの経路と一致しない）。
    """
    for j in data.get("journeys", []):
        if j.get("transferCount") != 0:
            continue
        transit_legs = [l for l in j.get("legs", []) if l.get("kind") == "transit"]
        if len(transit_legs) != 1:
            continue
        leg = transit_legs[0]
        dep = leg.get("departureSecs")
        arr = leg.get("arrivalSecs")
        if not isinstance(dep, int) or not isinstance(arr, int) or arr < dep:
            continue
        return dep, arr, leg.get("trainType"), leg.get("headsign")
    return None


def build_timetable(
    path: list[PathSegment],
    depart_hhmm: str,
    adj: Adjacency,
    transit_map: TransitMap,
) -> TimetableResponse:
    legs = split_legs(path)
    start = _parse_hhmm(depart_hhmm)
    cur = start
    out: list[TimetableLeg] = []
    has_estimate = False

    for idx, leg in enumerate(legs):
        line_map = transit_map.get(leg.line_id, {})
        from_tid = line_map.get(leg.station_ids[0])
        to_tid = line_map.get(leg.station_ids[-1])

        picked = None
        if from_tid and to_tid:
            query_secs = cur + (int(TRANSFER_BUFFER_MIN * 60) if idx > 0 else 0)
            data = transit.plan(from_tid, to_tid, _fmt(query_secs))
            if data:
                picked = _pick_direct(data)

        if picked:
            dep, arr, train_type, headsign = picked
            if dep < cur:  # 日跨ぎで API が翌日の時刻を返した場合の保険
                dep += 86400
                arr += 86400
            source = "timetable"
        else:
            has_estimate = True
            headway = HEADWAY_MIN.get(leg.line_id, DEFAULT_HEADWAY_MIN)
            wait_min = headway / 2 + (TRANSFER_WALK_MIN if idx > 0 else 0)
            dep = cur + int(wait_min * 60)
            arr = dep + int(_ride_minutes(adj, leg) * 60)
            train_type = None
            headsign = None
            source = "estimate"

        out.append(
            TimetableLeg(
                line_id=leg.line_id,
                from_station_id=leg.station_ids[0],
                to_station_id=leg.station_ids[-1],
                departure=_fmt(dep),
                arrival=_fmt(arr),
                wait_min=round((dep - cur) / 60, 1),
                ride_min=round((arr - dep) / 60, 1),
                source=source,
                train_type=train_type,
                headsign=headsign,
            )
        )
        cur = arr

    return TimetableResponse(
        depart_time=depart_hhmm,
        arrival_time=_fmt(cur),
        total_min=round((cur - start) / 60, 1),
        has_estimate=has_estimate,
        legs=out,
    )
