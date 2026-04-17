"""
Dynamic route helpers powered by external routing providers.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from models import Coordinate

ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
OSRM_DIRECTIONS_URL = "https://router.project-osrm.org/route/v1/driving"


def fetch_route_coordinates(origin: Coordinate, destination: Coordinate) -> list[Coordinate]:
    route_coordinates = fetch_ors_route(origin, destination)
    if route_coordinates:
        return route_coordinates

    route_coordinates = fetch_osrm_route(origin, destination)
    if route_coordinates:
        return route_coordinates

    print("[recommend] route providers unavailable, falling back to straight line route")
    return [origin, destination]


def fetch_ors_route(origin: Coordinate, destination: Coordinate) -> list[Coordinate]:
    api_key = os.getenv("OPENROUTESERVICE_API_KEY") or os.getenv("ORS_API_KEY")
    if not api_key:
        return []

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
        with urlopen(request, timeout=12) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[recommend] openrouteservice request failed: {exc}")
        return []

    encoded_geometry = (
        response_data.get("routes", [{}])[0].get("geometry")
        if isinstance(response_data, dict)
        else None
    )
    if not encoded_geometry:
        print("[recommend] openrouteservice returned no geometry")
        return []

    coordinates = decode_polyline(encoded_geometry)
    return coordinates if len(coordinates) >= 2 else []


def fetch_osrm_route(origin: Coordinate, destination: Coordinate) -> list[Coordinate]:
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
        with urlopen(request, timeout=12) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[recommend] osrm request failed: {exc}")
        return []

    raw_coordinates = (
        response_data.get("routes", [{}])[0].get("geometry", {}).get("coordinates")
        if isinstance(response_data, dict)
        else None
    )
    if not raw_coordinates:
        print("[recommend] osrm returned no geometry")
        return []

    coordinates = [
        Coordinate(lat=coordinate[1], lon=coordinate[0])
        for coordinate in raw_coordinates
        if isinstance(coordinate, list) and len(coordinate) >= 2
    ]
    return coordinates if len(coordinates) >= 2 else []


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
