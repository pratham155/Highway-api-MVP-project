"""
Dynamic route helpers powered by external routing providers.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from models import Coordinate

ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
OSRM_DIRECTIONS_URL = "https://router.project-osrm.org/route/v1/driving"
ORS_TIMEOUT_SECONDS = 2.5
OSRM_TIMEOUT_SECONDS = 3.5


@dataclass
class RouteMetrics:
    coordinates: list[Coordinate]
    distance_km: float
    duration_minutes: int


def fetch_route_details(origin: Coordinate, destination: Coordinate) -> RouteMetrics:
    return _fetch_route_details_cached(
        round(origin.lat, 5),
        round(origin.lon, 5),
        round(destination.lat, 5),
        round(destination.lon, 5),
    )


@lru_cache(maxsize=256)
def _fetch_route_details_cached(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> RouteMetrics:
    origin = Coordinate(lat=origin_lat, lon=origin_lon)
    destination = Coordinate(lat=destination_lat, lon=destination_lon)
    route_metrics = fetch_ors_route(origin, destination)
    if route_metrics:
        return route_metrics

    route_metrics = fetch_osrm_route(origin, destination)
    if route_metrics:
        return route_metrics

    print("[recommend] route providers unavailable, falling back to straight line route")
    straight_line_distance = haversine_km(origin, destination)
    return RouteMetrics(
        coordinates=[origin, destination],
        distance_km=round(straight_line_distance, 1),
        duration_minutes=max(1, round((straight_line_distance / 45.0) * 60)),
    )


def fetch_route_coordinates(origin: Coordinate, destination: Coordinate) -> list[Coordinate]:
    return fetch_route_details(origin, destination).coordinates


def fetch_ors_route(origin: Coordinate, destination: Coordinate) -> RouteMetrics | None:
    api_key = os.getenv("OPENROUTESERVICE_API_KEY") or os.getenv("ORS_API_KEY")
    if not api_key:
        return None

    payload = json.dumps(
        {
            "coordinates": [
                [origin.lon, origin.lat],
                [destination.lon, destination.lat],
            ]
        }
    ).encode("utf-8")

    request = Request(
        ORS_DIRECTIONS_URL,
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=ORS_TIMEOUT_SECONDS) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[recommend] openrouteservice request failed: {exc}")
        return None

    route = response_data.get("routes", [{}])[0] if isinstance(response_data, dict) else {}
    encoded_geometry = route.get("geometry")
    summary = route.get("summary", {})
    if not encoded_geometry or not isinstance(summary, dict):
        print("[recommend] openrouteservice returned no geometry")
        return None

    coordinates = decode_polyline(encoded_geometry)
    if len(coordinates) < 2:
        return None

    distance_meters = float(summary.get("distance", 0))
    duration_seconds = float(summary.get("duration", 0))
    return RouteMetrics(
        coordinates=coordinates,
        distance_km=round(distance_meters / 1000, 1),
        duration_minutes=max(1, round(duration_seconds / 60)),
    )


def fetch_osrm_route(origin: Coordinate, destination: Coordinate) -> RouteMetrics | None:
    query = urlencode(
        {
            "overview": "full",
            "geometries": "geojson",
        }
    )
    url = (
        f"{OSRM_DIRECTIONS_URL}/"
        f"{origin.lon},{origin.lat};{destination.lon},{destination.lat}?{query}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=OSRM_TIMEOUT_SECONDS) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[recommend] osrm request failed: {exc}")
        return None

    route = response_data.get("routes", [{}])[0] if isinstance(response_data, dict) else {}
    raw_coordinates = route.get("geometry", {}).get("coordinates")
    if not raw_coordinates:
        print("[recommend] osrm returned no geometry")
        return None

    coordinates = [
        Coordinate(lat=coordinate[1], lon=coordinate[0])
        for coordinate in raw_coordinates
        if isinstance(coordinate, list) and len(coordinate) >= 2
    ]
    if len(coordinates) < 2:
        return None

    distance_meters = float(route.get("distance", 0))
    duration_seconds = float(route.get("duration", 0))
    return RouteMetrics(
        coordinates=coordinates,
        distance_km=round(distance_meters / 1000, 1),
        duration_minutes=max(1, round(duration_seconds / 60)),
    )


def decode_polyline(polyline: str) -> list[Coordinate]:
    coordinates: list[Coordinate] = []
    index = 0
    lat = 0
    lon = 0

    while index < len(polyline):
        lat_change, index = _decode_value(polyline, index)
        lon_change, index = _decode_value(polyline, index)
        lat += lat_change
        lon += lon_change
        coordinates.append(Coordinate(lat=lat / 1e5, lon=lon / 1e5))

    return coordinates


def _decode_value(polyline: str, start_index: int) -> tuple[int, int]:
    result = 0
    shift = 0
    index = start_index

    while True:
        byte = ord(polyline[index]) - 63
        index += 1
        result |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            break

    delta = ~(result >> 1) if result & 1 else result >> 1
    return delta, index


def haversine_km(origin: Coordinate, destination: Coordinate) -> float:
    import math

    radius_km = 6371.0
    lat1 = math.radians(origin.lat)
    lon1 = math.radians(origin.lon)
    lat2 = math.radians(destination.lat)
    lon2 = math.radians(destination.lon)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c
