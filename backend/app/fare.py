import json
from pathlib import Path

from app.graph import Adjacency
from app.models import FareEntry
from app.routing import shortest_route
from app.models import OptimizeBy

_DEFAULT_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "fare_table.json"


def load_fare_table(path: Path = _DEFAULT_TABLE_PATH) -> list[FareEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [FareEntry(**entry) for entry in raw]


def km_to_fare(km: float, table: list[FareEntry]) -> tuple[int, int]:
    """キロ程からIC運賃・きっぷ運賃を返す。(ic, ticket)"""
    for entry in table:
        if entry.from_km <= km <= entry.to_km:
            return entry.fare_ic, entry.fare_ticket
    # 範囲外（テーブルの最大値を超えた場合）は最後のエントリを使う
    last = table[-1]
    return last.fare_ic, last.fare_ticket


def calc_direct_fare(
    adj: Adjacency,
    start: str,
    end: str,
    table: list[FareEntry],
) -> tuple[float, int, int]:
    """出発〜終着の最短キロ程とIC・きっぷ運賃を返す。(km, ic, ticket)"""
    result = shortest_route(adj, start, end, OptimizeBy.distance)
    if result is None:
        return 0.0, 0, 0
    _, total_km, _ = result
    ic, ticket = km_to_fare(total_km, table)
    return total_km, ic, ticket
