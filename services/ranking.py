"""
Polyline-based ranking service for highway stop recommendations.
"""

from __future__ import annotations

import math
from typing import List, Optional, TypedDict

from models import Coordinate, RecommendedStop, Restaurant
from services.catalog import build_summary

PRIMARY_ROUTE_THRESHOLD_KM = 5.0
SECONDARY_ROUTE_THRESHOLD_KM = 10.0


class Candidate(TypedDict):
    restaurant: Restaurant
    user_distance_km: float
    route_distance_km: float


def rank_restaurants(
    restaurants: List[Restaurant],
    *,
    origin: Coordinate,
    route_coordinates: List[Coordinate],
    top_n: int = 3,
) -> List[RecommendedStop]:
    candidates = build_route_candidates(restaurants, origin=origin, route_coordinates=route_coordinates)
    if not candidates:
        return []

    return [
        build_recommended_stop(
            candidate,
            reason=build_default_reason(index=index),
        )
        for index, candidate in enumerate(candidates[:top_n])
    ]


def search_restaurants_by_craving(
    restaurants: List[Restaurant],
    *,
    origin: Coordinate,
    route_coordinates: List[Coordinate],
    craving: str,
    limit: int = 10,
) -> List[RecommendedStop]:
    normalized_craving = craving.strip().lower()
    candidates = build_route_candidates(restaurants, origin=origin, route_coordinates=route_coordinates)
    if not candidates:
        return []

    matched_candidates = [
        candidate
        for candidate in candidates
        if normalized_craving in " ".join(candidate["restaurant"].dishes).lower()
    ]
    matched_candidates.sort(key=lambda candidate: (candidate["route_distance_km"], -candidate["restaurant"].rating))

    return [
        build_recommended_stop(
            candidate,
            reason=f"Best match for {normalized_craving}",
            dish=normalized_craving,
        )
        for candidate in matched_candidates[:limit]
    ]


def build_route_candidates(
    restaurants: List[Restaurant],
    *,
    origin: Coordinate,
    route_coordinates: List[Coordinate],
) -> List[Candidate]:
    if len(route_coordinates) < 2:
        print("[recommend] route has fewer than 2 points")
        return []

    primary_candidates: list[Candidate] = []
    secondary_candidates: list[Candidate] = []

    for restaurant in restaurants:
        route_distance_km = round(
            distance_point_to_polyline(
                restaurant.lat,
                restaurant.lon,
                route_coordinates,
            ),
            1,
        )
        user_distance_km = round(haversine_km(origin.lat, origin.lon, restaurant.lat, restaurant.lon), 1)

        candidate = Candidate(
            restaurant=restaurant,
            user_distance_km=user_distance_km,
            route_distance_km=route_distance_km,
        )

        if route_distance_km <= PRIMARY_ROUTE_THRESHOLD_KM:
            primary_candidates.append(candidate)
        elif route_distance_km <= SECONDARY_ROUTE_THRESHOLD_KM:
            secondary_candidates.append(candidate)

    primary_candidates.sort(key=lambda candidate: (candidate["route_distance_km"], -candidate["restaurant"].rating))
    secondary_candidates.sort(key=lambda candidate: (candidate["route_distance_km"], -candidate["restaurant"].rating))

    if primary_candidates:
        print(
            f"[recommend] strict route matches={len(primary_candidates)} threshold_km={PRIMARY_ROUTE_THRESHOLD_KM}"
        )
        return primary_candidates
    if secondary_candidates:
        print(
            f"[recommend] relaxed route matches={len(secondary_candidates)} threshold_km={SECONDARY_ROUTE_THRESHOLD_KM}"
        )
        return secondary_candidates
    print("[recommend] no restaurants found near computed polyline")
    return []
def build_recommended_stop(
    candidate: Candidate,
    *,
    reason: str,
    dish: Optional[str] = None,
) -> RecommendedStop:
    restaurant = candidate["restaurant"]
    return RecommendedStop(
        **build_summary(
            restaurant,
            reason=reason,
            dish=dish,
            distance_km=candidate["user_distance_km"],
            distance_from_route_km=candidate["route_distance_km"],
            detour_km=candidate["route_distance_km"],
            time_to_reach_minutes=estimate_eta_minutes(candidate["user_distance_km"]),
            distance_from_origin_km=candidate["user_distance_km"],
        ).model_dump()
    )


def build_default_reason(*, index: int) -> str:
    if index == 0:
        return "Closest stop"
    if index == 1:
        return "Top rated"
    return "Quick service"


def estimate_eta_minutes(user_distance_km: float) -> int:
    return max(5, round((user_distance_km / 45.0) * 60))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def distance_point_to_polyline(lat: float, lon: float, route_coordinates: List[Coordinate]) -> float:
    nearest_distance = float("inf")

    for start, end in zip(route_coordinates, route_coordinates[1:]):
        nearest_distance = min(
            nearest_distance,
            distance_point_to_segment(lat, lon, start.lat, start.lon, end.lat, end.lon),
        )

    return nearest_distance


def distance_point_to_segment(
    lat: float,
    lon: float,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    px, py = project_to_local_km(lat, lon, lat1, lon1)
    ex, ey = project_to_local_km(lat2, lon2, lat1, lon1)

    length_sq = ex**2 + ey**2
    if length_sq == 0:
        return math.hypot(px, py)

    progress = ((px * ex) + (py * ey)) / length_sq
    clamped_progress = max(0.0, min(1.0, progress))
    nearest_x = clamped_progress * ex
    nearest_y = clamped_progress * ey
    return math.hypot(px - nearest_x, py - nearest_y)


def project_to_local_km(
    lat: float,
    lon: float,
    reference_lat: float,
    reference_lon: float,
) -> tuple[float, float]:
    x = (lon - reference_lon) * 111.32 * math.cos(math.radians(reference_lat))
    y = (lat - reference_lat) * 110.57
    return x, y
