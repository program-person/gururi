from enum import Enum

from pydantic import BaseModel, Field


class OptimizeBy(str, Enum):
    distance = "distance"
    time = "time"


class Station(BaseModel):
    id: str
    name: str


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


class FareEntry(BaseModel):
    from_km: float
    to_km: float
    fare_ic: int
    fare_ticket: int


class FareResponse(BaseModel):
    direct_km: float = Field(alias="directKm")
    fare_ic: int = Field(alias="fareIc")
    fare_ticket: int = Field(alias="fareTicket")

    model_config = {"populate_by_name": True}


class OmawariRoute(BaseModel):
    path: list[PathSegment]
    total_distance: float = Field(alias="totalDistance")
    total_time: float = Field(alias="totalTime")
    station_count: int = Field(alias="stationCount")
    direct_km: float = Field(alias="directKm")
    fare_ic: int = Field(alias="fareIc")

    model_config = {"populate_by_name": True}
