from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# "H:MM" / "HH:MM"（0:00〜23:59）。時刻入力はすべてこの形式で受ける
HHMM_PATTERN = r"^([01]?\d|2[0-3]):[0-5]\d$"
HhMm = Annotated[str, StringConstraints(pattern=HHMM_PATTERN)]


class OptimizeBy(str, Enum):
    distance = "distance"
    time = "time"


class Station(BaseModel):
    id: str
    name: str
    lat: float | None = None
    lng: float | None = None


class Line(BaseModel):
    id: str
    name: str


class Edge(BaseModel):
    from_station_id: str = Field(alias="fromStationId")
    to_station_id: str = Field(alias="toStationId")
    line_id: str = Field(alias="lineId")
    distance: float = Field(ge=0)
    travel_time: float = Field(alias="travelTime", ge=0)

    model_config = {"populate_by_name": True}


class GraphData(BaseModel):
    stations: list[Station]
    lines: list[Line]
    edges: list[Edge]

    model_config = {"populate_by_name": True}


class PathSegment(BaseModel):
    station_id: str = Field(alias="stationId")
    line_id: str = Field(alias="lineId")

    model_config = {"populate_by_name": True}


class RouteResponse(BaseModel):
    total_distance: float = Field(alias="totalDistance")
    total_time: float = Field(alias="totalTime")
    path: list[PathSegment]

    model_config = {"populate_by_name": True}


class FareBand(BaseModel):
    """キロ程帯の上限(to_km)と、その帯に適用される片道普通運賃。"""

    to_km: float = Field(alias="toKm")
    fare: int

    model_config = {"populate_by_name": True}


class AirportSurcharge(BaseModel):
    """関西空港線などの加算運賃区間。"""

    from_station_id: str = Field(alias="from")
    to_station_id: str = Field(alias="to")
    surcharge: int

    model_config = {"populate_by_name": True}


class SpecificFare(BaseModel):
    """競合私鉄対抗の特定区間運賃（発着駅ペア・双方向に適用）。"""

    stations: tuple[str, str]
    fare: int

    model_config = {"populate_by_name": True}


class FareTable(BaseModel):
    """2025-04-01改定後の運賃体系データ（backend/data/fare_table.json）。"""

    revision: str
    trunk: list[FareBand]
    denshaku: list[FareBand]
    local: list[FareBand]
    local_line_ids: list[str] = Field(alias="localLineIds")
    local_conversion_factor: float = Field(alias="localConversionFactor")
    denshaku_station_ids: list[str] = Field(alias="denshakuStationIds")
    airport_surcharges: list[AirportSurcharge] = Field(alias="airportSurcharges")
    specific_fares: list[SpecificFare] = Field(
        default_factory=list, alias="specificFares"
    )

    model_config = {"populate_by_name": True}


class FareResponse(BaseModel):
    direct_km: float = Field(alias="directKm")
    fare_ic: int = Field(alias="fareIc")
    fare_ticket: int = Field(alias="fareTicket")

    model_config = {"populate_by_name": True}


class TimetableLeg(BaseModel):
    line_id: str = Field(alias="lineId")
    from_station_id: str = Field(alias="fromStationId")
    to_station_id: str = Field(alias="toStationId")
    departure: str
    arrival: str
    wait_min: float = Field(alias="waitMin")
    ride_min: float = Field(alias="rideMin")
    # timetable=実ダイヤ（transit API）, estimate=運転間隔ベースの推定
    source: Literal["timetable", "estimate"]
    # 着時刻がユーザー入力で上書きされたレッグ。departure は arrival からの逆算値
    overridden: bool = False
    train_type: str | None = Field(None, alias="trainType")
    headsign: str | None = None

    model_config = {"populate_by_name": True}


class TimetableRequest(BaseModel):
    path: list[PathSegment]
    depart_time: str = Field(alias="departTime", pattern=HHMM_PATTERN)
    # 駅ID -> その駅への実際の着時刻。ダイヤ未収録路線をユーザーが自分で
    # 調べて入れるための上書き。以降のレッグはこの時刻を起点に再照会される。
    # キーはレッグの着駅（= 乗換駅と終着駅）に限る。上限はレッグ数の上限と同じ
    arrival_overrides: dict[str, HhMm] = Field(
        default_factory=dict, alias="arrivalOverrides", max_length=40
    )

    model_config = {"populate_by_name": True}


class TimetableResponse(BaseModel):
    depart_time: str = Field(alias="departTime")
    arrival_time: str = Field(alias="arrivalTime")
    total_min: float = Field(alias="totalMin")
    has_estimate: bool = Field(alias="hasEstimate")
    legs: list[TimetableLeg]

    model_config = {"populate_by_name": True}


class OmawariRoute(BaseModel):
    path: list[PathSegment]
    total_distance: float = Field(alias="totalDistance")
    total_time: float = Field(alias="totalTime")
    station_count: int = Field(alias="stationCount")
    direct_km: float = Field(alias="directKm")
    fare_ic: int = Field(alias="fareIc")

    model_config = {"populate_by_name": True}
