from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.fare import calc_direct_fare, load_fare_table
from app.graph import Adjacency, build_adjacency, load_graph_data, station_ids
from app.models import (
    FareResponse,
    FareTable,
    GraphData,
    Line,
    OmawariRoute,
    OptimizeBy,
    PathSegment,
    RouteResponse,
    Station,
    TimetableRequest,
    TimetableResponse,
)
from app.omawari import find_omawari_by_fare, find_omawari_routes
from app.ratelimit import SlidingWindowRateLimiter
from app.routing import shortest_route
from app.timetable import TransitMap, build_timetable, load_transit_map, split_legs

# /timetable の path 上限。ゴールデンループは maxStations を超える長さになるため、
# グラフの総駅数を上限とする（同一駅は再訪しないので、これ以上長い経路は存在しない）
MAX_TIMETABLE_PATH_SEGMENTS = 400
# 外部 transit API への負荷はレッグ数（＝API呼び出し回数）で決まる。
# 実測では最長のゴールデンループでも17レッグ
MAX_TIMETABLE_LEGS = 40


@dataclass(frozen=True)
class RailState:
    data: GraphData
    adj: Adjacency
    stations: frozenset[str]
    fare_table: FareTable


def _load_state(path: Path) -> RailState:
    data = load_graph_data(path)
    fare_table = load_fare_table()
    return RailState(
        data=data,
        adj=build_adjacency(data.edges),
        stations=frozenset(station_ids(data)),
        fare_table=fare_table,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rail = _load_state(settings.data_path)
    app.state.transit_map = load_transit_map(settings.transit_map_path)
    yield


app = FastAPI(title="JR West Omawari Route Planner", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.allow_all_origins else settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 探索が重い・外部APIを呼ぶエンドポイントのみ制限対象にする
RATE_LIMITED_PATHS = frozenset({"/omawari", "/omawari/by-fare", "/timetable"})
rate_limiter = SlidingWindowRateLimiter()


def _client_key(request: Request) -> str:
    # Railway 等のリバースプロキシ配下では接続元がプロキシIPになるため
    # X-Forwarded-For の先頭（実クライアント）を優先する。直接公開時は
    # 偽装可能だが、悪用しても「自分のキーを分散できる」だけなので許容
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if settings.rate_limit_enabled and request.url.path in RATE_LIMITED_PATHS:
        allowed = rate_limiter.allow(
            _client_key(request),
            settings.rate_limit_max_requests,
            settings.rate_limit_window_secs,
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please retry later."},
            )
    return await call_next(request)


def get_rail(request: Request) -> RailState:
    return request.app.state.rail


def _check_station(rail: RailState, station_id: str, label: str) -> None:
    if station_id not in rail.stations:
        raise HTTPException(status_code=404, detail=f"{label} not found: {station_id}")


# ------------------------------------------------------------------
# 譌｢蟄倥お繝ｳ繝峨・繧､繝ｳ繝・
# ------------------------------------------------------------------

@app.get("/route", response_model=RouteResponse, response_model_by_alias=True)
def get_route(
    request: Request,
    start_station_id: str = Query(..., alias="startStationId"),
    end_station_id: str = Query(..., alias="endStationId"),
    by: OptimizeBy = Query(OptimizeBy.time, description="Optimize by distance or travel time"),
) -> RouteResponse:
    rail = get_rail(request)
    _check_station(rail, start_station_id, "Start station")
    _check_station(rail, end_station_id, "End station")

    result = shortest_route(rail.adj, start_station_id, end_station_id, by)
    if result is None:
        raise HTTPException(status_code=404, detail="No route between stations")

    path_tuples, total_distance, total_time = result
    path = [PathSegment(station_id=sid, line_id=lid) for sid, lid in path_tuples]
    return RouteResponse(total_distance=total_distance, total_time=total_time, path=path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


# ------------------------------------------------------------------
# 譁ｰ繧ｨ繝ｳ繝峨・繧､繝ｳ繝・
# ------------------------------------------------------------------

@app.get("/stations", response_model=list[Station])
def list_stations(request: Request) -> list[Station]:
    rail = get_rail(request)
    return sorted(rail.data.stations, key=lambda s: s.id)


@app.get("/lines", response_model=list[Line])
def list_lines(request: Request) -> list[Line]:
    rail = get_rail(request)
    return rail.data.lines


@app.get("/fare", response_model=FareResponse, response_model_by_alias=True)
def get_fare(
    request: Request,
    from_station_id: str = Query(..., alias="fromStationId"),
    to_station_id: str = Query(..., alias="toStationId"),
) -> FareResponse:
    rail = get_rail(request)
    _check_station(rail, from_station_id, "From station")
    _check_station(rail, to_station_id, "To station")

    try:
        km, ic, ticket = calc_direct_fare(rail.adj, from_station_id, to_station_id, rail.fare_table)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FareResponse(direct_km=km, fare_ic=ic, fare_ticket=ticket)


@app.get("/omawari", response_model=list[OmawariRoute], response_model_by_alias=True)
def get_omawari(
    request: Request,
    start_station_id: str = Query(..., alias="startStationId"),
    end_station_id: str | None = Query(None, alias="endStationId"),
    max_time_min: float = Query(480.0, alias="maxTimeMin", ge=1, le=10000),
    max_stations: int = Query(120, alias="maxStations", ge=5, le=200),
    num_results: int = Query(5, alias="numResults", ge=1, le=20),
) -> list[OmawariRoute]:
    rail = get_rail(request)
    _check_station(rail, start_station_id, "Start station")
    if end_station_id is not None:
        _check_station(rail, end_station_id, "End station")
        if end_station_id == start_station_id:
            raise HTTPException(status_code=400, detail="Start and end station must differ")

    name_to_id = {s.name: s.id for s in rail.data.stations}
    return find_omawari_routes(
        rail.adj,
        start_station_id,
        rail.fare_table,
        end=end_station_id,
        max_stations=max_stations,
        max_time_min=max_time_min,
        num_results=num_results,
        name_to_id=name_to_id,
    )


def _validate_timetable_path(rail: RailState, path: list[PathSegment]) -> None:
    """path がグラフ上の実在ルートであることを検証する。

    任意の駅ペアを受け付けると外部の transit API への踏み台
    （こちらの UA で好きな検索を打たせる）に使えてしまうため、
    連続する駅が指定路線の実エッジで結ばれていることまで確認する。
    """
    if len(path) < 2:
        raise HTTPException(status_code=400, detail="path must contain at least 2 stations")
    if len(path) > MAX_TIMETABLE_PATH_SEGMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"path too long (max {MAX_TIMETABLE_PATH_SEGMENTS} segments)",
        )
    for seg in path:
        _check_station(rail, seg.station_id, "Station")
    for prev, seg in zip(path, path[1:]):
        edge_exists = any(
            neighbor_id == seg.station_id and line_id == seg.line_id
            for neighbor_id, line_id, _dist, _time in rail.adj.get(prev.station_id, [])
        )
        if not edge_exists:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"path is not a valid route: no edge "
                    f"{prev.station_id} -> {seg.station_id} on line {seg.line_id}"
                ),
            )

    num_legs = len(split_legs(path))
    if num_legs > MAX_TIMETABLE_LEGS:
        raise HTTPException(
            status_code=400,
            detail=f"too many legs (max {MAX_TIMETABLE_LEGS})",
        )


@app.post("/timetable", response_model=TimetableResponse, response_model_by_alias=True)
def post_timetable(request: Request, body: TimetableRequest) -> TimetableResponse:
    """大回りルートの区間ごとの発着時刻（実ダイヤ + 未収録区間は推定）"""
    rail = get_rail(request)
    _validate_timetable_path(rail, body.path)

    transit_map: TransitMap = request.app.state.transit_map
    return build_timetable(body.path, body.depart_time, rail.adj, transit_map)


@app.get("/omawari/by-fare", response_model=list[OmawariRoute], response_model_by_alias=True)
def get_omawari_by_fare(
    request: Request,
    start_station_id: str = Query(..., alias="startStationId"),
    max_fare: int = Query(..., alias="maxFare", ge=100, le=5000),
    max_time_min: float = Query(480.0, alias="maxTimeMin", ge=1, le=10000),
    num_results: int = Query(5, alias="numResults", ge=1, le=20),
) -> list[OmawariRoute]:
    rail = get_rail(request)
    _check_station(rail, start_station_id, "Start station")

    return find_omawari_by_fare(
        rail.adj,
        start_station_id,
        rail.fare_table,
        max_fare=max_fare,
        max_time_min=max_time_min,
        num_results=num_results,
    )

