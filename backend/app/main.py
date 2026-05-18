from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.fare import calc_direct_fare, load_fare_table
from app.graph import Adjacency, build_adjacency, load_graph_data, station_ids
from app.models import (
    FareEntry,
    FareResponse,
    GraphData,
    OmawariRoute,
    OptimizeBy,
    PathSegment,
    RouteResponse,
    Station,
)
from app.omawari import find_omawari_by_fare, find_omawari_routes
from app.routing import shortest_route


@dataclass(frozen=True)
class RailState:
    data: GraphData
    adj: Adjacency
    stations: frozenset[str]
    fare_table: list[FareEntry]


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
    yield


app = FastAPI(title="JR West Omawari Route Planner", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_rail(request: Request) -> RailState:
    return request.app.state.rail


def _check_station(rail: RailState, station_id: str, label: str) -> None:
    if station_id not in rail.stations:
        raise HTTPException(status_code=404, detail=f"{label} not found: {station_id}")


# ------------------------------------------------------------------
# 既存エンドポイント
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
    return {"status": "ok"}


# ------------------------------------------------------------------
# 新エンドポイント
# ------------------------------------------------------------------

@app.get("/stations", response_model=list[Station])
def list_stations(request: Request) -> list[Station]:
    rail = get_rail(request)
    return sorted(rail.data.stations, key=lambda s: s.id)


@app.get("/fare", response_model=FareResponse, response_model_by_alias=True)
def get_fare(
    request: Request,
    from_station_id: str = Query(..., alias="fromStationId"),
    to_station_id: str = Query(..., alias="toStationId"),
) -> FareResponse:
    rail = get_rail(request)
    _check_station(rail, from_station_id, "From station")
    _check_station(rail, to_station_id, "To station")

    km, ic, ticket = calc_direct_fare(rail.adj, from_station_id, to_station_id, rail.fare_table)
    return FareResponse(direct_km=km, fare_ic=ic, fare_ticket=ticket)


@app.get("/omawari", response_model=list[OmawariRoute], response_model_by_alias=True)
def get_omawari(
    request: Request,
    start_station_id: str = Query(..., alias="startStationId"),
    end_station_id: str | None = Query(None, alias="endStationId"),
    max_time_min: float = Query(480.0, alias="maxTimeMin", ge=30, le=720),
    max_stations: int = Query(50, alias="maxStations", ge=5, le=100),
    num_results: int = Query(5, alias="numResults", ge=1, le=20),
) -> list[OmawariRoute]:
    rail = get_rail(request)
    _check_station(rail, start_station_id, "Start station")
    if end_station_id is not None:
        _check_station(rail, end_station_id, "End station")
        if end_station_id == start_station_id:
            raise HTTPException(status_code=400, detail="Start and end station must differ")

    return find_omawari_routes(
        rail.adj,
        start_station_id,
        rail.fare_table,
        end=end_station_id,
        max_stations=max_stations,
        max_time_min=max_time_min,
        num_results=num_results,
    )


@app.get("/omawari/by-fare", response_model=list[OmawariRoute], response_model_by_alias=True)
def get_omawari_by_fare(
    request: Request,
    start_station_id: str = Query(..., alias="startStationId"),
    max_fare: int = Query(..., alias="maxFare", ge=100, le=5000),
    max_time_min: float = Query(480.0, alias="maxTimeMin", ge=30, le=720),
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
