import json
import math
from pathlib import Path

from app.graph import Adjacency
from app.models import FareTable, OptimizeBy
from app.routing import shortest_route

_DEFAULT_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "fare_table.json"

# 幹線+地方交通線の合計営業キロがこれ以下の場合、地方交通線の換算キロ(×1.1)を
# 適用せず営業キロそのままで幹線表を引く（要検証: 正式には専用の「地方交通線
# 普通運賃表(B表)」を使うべきだが、信頼できる出典が確認できなかったため、
# 幹線表への近似フォールバックとしている。大回りルートは通常10kmを大きく
# 超えるため、実務上この分岐に入るのは稀。）
_SHORT_MIXED_KM_THRESHOLD = 10.0


def load_fare_table(path: Path = _DEFAULT_TABLE_PATH) -> FareTable:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return FareTable.model_validate(raw)


def _lookup_fare(km: float, bands: list) -> int:
    """営業キロ(または運賃計算キロ)からキロ地帯を引いて運賃を返す。

    1km未満は切り上げてから帯を昇順に走査する（3.5km等の端数が最終帯に
    落ちてしまう旧実装のバグを修正）。表の最大キロを超えた場合はValueError。
    """
    # 浮動小数の誤差で 3.0000000001 のようになるケースを吸収してから切り上げる
    km_ceiled = math.ceil(round(km, 6) - 1e-9)
    km_ceiled = max(km_ceiled, 0)
    for band in bands:
        if km_ceiled <= band.to_km:
            return band.fare
    raise ValueError(
        f"Fare table exceeded: {km_ceiled}km (table max {bands[-1].to_km}km)"
    )


def _edge_details(
    adj: Adjacency, path: list[tuple[str, str]]
) -> list[tuple[str, str, str, float]]:
    """shortest_route の path (station_id, line_id) 列から、各区間の
    (from_station_id, to_station_id, line_id, distance) を隣接リストから復元する。
    """
    edges: list[tuple[str, str, str, float]] = []
    for i in range(1, len(path)):
        u = path[i - 1][0]
        v, line_id = path[i]
        distance = 0.0
        for n_id, lid, dist, _time in adj.get(u, []):
            if n_id == v and lid == line_id:
                distance = dist
                break
        else:
            # 完全一致が見つからない場合は駅ペアのみで代替（理論上発生しない想定）
            for n_id, lid, dist, _time in adj.get(u, []):
                if n_id == v:
                    distance = dist
                    break
        edges.append((u, v, line_id, distance))
    return edges


def _airport_surcharge(stations: list[str], table: FareTable) -> int:
    """関西空港線区間の加算運賃を1回だけ適用する。

    加算運賃はJRの規則上、乗車券のO-D（区間の両端）ごとに定まる。
    りんくうタウンを経由しても日根野～関西空港が1本の加算運賃(220円)で
    あり、日根野～りんくうタウン(160円)とりんくうタウン～関西空港(170円)
    を separately 合算するわけではない。そのため、経路のうち加算運賃
    区間（airport_surcharges に登場する駅群）に触れた最初と最後の駅を
    実際のO-Dとみなし、その組み合わせに一致する加算運賃を1件だけ適用する。
    """
    zone_stations: set[str] = set()
    for entry in table.airport_surcharges:
        zone_stations.add(entry.from_station_id)
        zone_stations.add(entry.to_station_id)

    touched = [sid for sid in stations if sid in zone_stations]
    if len(touched) < 2:
        return 0

    pair = {touched[0], touched[-1]}
    if len(pair) < 2:
        return 0

    for entry in table.airport_surcharges:
        if {entry.from_station_id, entry.to_station_id} == pair:
            return entry.surcharge
    return 0


def compute_fare(
    adj: Adjacency,
    path: list[tuple[str, str]],
    table: FareTable,
) -> int:
    """経路(shortest_route の戻り値のpath)から片道普通運賃を計算する。"""
    stations = [sid for sid, _ in path]
    edges = _edge_details(adj, path)

    if not edges:
        return 0

    # 特定運賃（競合私鉄対抗の特定区間運賃）は発着駅ペアで決まり、
    # キロ地帯の表引きより優先される（常に表引きより安い額が設定されている）
    od_pair = frozenset((stations[0], stations[-1]))
    for sf in table.specific_fares:
        if frozenset(sf.stations) == od_pair:
            return sf.fare

    total_km = sum(dist for *_rest, dist in edges)
    surcharge = _airport_surcharge(stations, table)

    if all(sid in table.denshaku_station_ids for sid in stations):
        return _lookup_fare(total_km, table.denshaku) + surcharge

    local_km = sum(
        dist for _u, _v, lid, dist in edges if lid in table.local_line_ids
    )
    trunk_km = total_km - local_km

    if local_km <= 0:
        return _lookup_fare(total_km, table.trunk) + surcharge

    converted_local_km = local_km * table.local_conversion_factor
    combined_km = trunk_km + converted_local_km

    if combined_km <= _SHORT_MIXED_KM_THRESHOLD:
        # 地方交通線表(B表)が未確認のため、営業キロ合計で幹線表を近似的に適用
        fare = _lookup_fare(trunk_km + local_km, table.trunk)
    else:
        fare = _lookup_fare(combined_km, table.trunk)

    return fare + surcharge


def calc_direct_fare(
    adj: Adjacency,
    start: str,
    end: str,
    table: FareTable,
) -> tuple[float, int, int]:
    """出発〜終着の最短キロ程とIC・きっぷ運賃を返す。(km, ic, ticket)

    JR西日本はICOCA運賃ときっぷ運賃が同額（1円単位運賃は未導入）のため、
    ic/ticketは常に同じ値を返す。
    """
    result = shortest_route(adj, start, end, OptimizeBy.distance)
    if result is None:
        return 0.0, 0, 0
    path, total_km, _ = result
    fare = compute_fare(adj, path, table)
    return total_km, fare, fare
