"""
Catalog helpers for route-aware restaurant discovery responses.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Optional

from models import Coordinate, Restaurant, RestaurantDetail, RestaurantSummary, RouteSummary


ROUTES: dict[str, RouteSummary] = {
    "bangalore-mysore": RouteSummary(
        id="bangalore-mysore",
        origin="Bangalore",
        destination="Mysore",
        highway="NH-275",
        distance_km=145,
        eta_minutes=180,
        coordinates=[
            Coordinate(lat=12.9716, lon=77.5946),
            Coordinate(lat=12.8342, lon=77.4010),
            Coordinate(lat=12.7217, lon=77.2813),
            Coordinate(lat=12.5825, lon=77.0451),
            Coordinate(lat=12.2958, lon=76.6394),
        ],
    )
}

RESTAURANT_META: dict[str, dict[str, str]] = {
    "maddur-tiffanys": {
        "phone": "+91 80411 22334",
        "address": "Maddur service road, NH-275, Mandya",
        "hours": "6:30 AM - 10:30 PM",
        "about": "A classic highway halt known for crisp Maddur vada, fast turnaround, and reliable family-stop amenities.",
    },
    "kamat-lokaruchi": {
        "phone": "+91 80471 18000",
        "address": "Channapatna bypass, NH-275, Ramanagara",
        "hours": "7:00 AM - 10:00 PM",
        "about": "Popular for sit-down Karnataka meals with a spacious campus, parking, and dependable washrooms.",
    },
    "empire-restaurant-ramanagara": {
        "phone": "+91 80612 33445",
        "address": "Ramanagara highway junction, NH-275",
        "hours": "11:00 AM - 11:30 PM",
        "about": "A quick-stop non-veg favorite with biryani, kababs, and fast table service close to the main carriageway.",
    },
    "hotel-rrr": {
        "phone": "+91 82124 88001",
        "address": "Maddur-Mysore road, NH-275, Mandya district",
        "hours": "11:30 AM - 10:30 PM",
        "about": "Known for Andhra-style meals and spicy chicken fry, especially for travelers reaching the final leg to Mysore.",
    },
    "adyar-ananda-bhavan-a2b": {
        "phone": "+91 80495 22110",
        "address": "Bidadi service lane, NH-275, Ramanagara",
        "hours": "6:00 AM - 11:00 PM",
        "about": "A dependable family chain stop for tiffin, coffee, sweets, and quick breakfast breaks.",
    },
    "shivalli-restaurant": {
        "phone": "+91 81922 00117",
        "address": "Ring road dining strip, Mysore",
        "hours": "7:00 AM - 10:30 PM",
        "about": "A Mysore-side destination for benne dosa and South Karnataka tiffin before or after the final city stretch.",
    },
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "restaurant"


def get_route(route_id: str) -> RouteSummary:
    route = ROUTES.get(route_id)
    if not route:
        raise KeyError(route_id)
    return route


def is_route_match(restaurant: Restaurant, route_id: Optional[str]) -> bool:
    if not route_id:
        return True
    if route_id == "bangalore-mysore":
        route = get_route(route_id)
        return (
            restaurant.distance_from_bangalore_km is not None
            and restaurant.distance_from_bangalore_km <= route.distance_km + 15
        )
    return False


def filter_restaurants(
    restaurants: Iterable[Restaurant],
    route_id: Optional[str] = None,
    dish: Optional[str] = None,
) -> list[Restaurant]:
    filtered = [restaurant for restaurant in restaurants if is_route_match(restaurant, route_id)]
    if dish:
        dish_lower = dish.strip().lower()
        filtered = [
            restaurant
            for restaurant in filtered
            if any(dish_lower in candidate.lower() for candidate in restaurant.dishes)
            or dish_lower in restaurant.famous_for.lower()
        ]
    return filtered


def popular_dishes(restaurants: Iterable[Restaurant], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for restaurant in restaurants:
        counter.update(dish.title() for dish in restaurant.dishes)
    return [dish for dish, _ in counter.most_common(limit)]


def match_dishes(restaurant: Restaurant, dish: Optional[str]) -> list[str]:
    if not dish:
        return []
    dish_lower = dish.strip().lower()
    return [candidate.title() for candidate in restaurant.dishes if dish_lower in candidate.lower()]


def compute_eta_minutes(restaurant: Restaurant) -> int:
    return max(5, round(restaurant.detour_km * 7 + restaurant.distance_from_route_km * 4 + 6))


def build_tags(restaurant: Restaurant) -> list[str]:
    tags = ["Veg Friendly" if restaurant.type == "veg" else "Non-Veg"]
    if restaurant.fast_service:
        tags.append("Fast service")
    if restaurant.washroom:
        tags.append("Clean washroom")
    if restaurant.parking:
        tags.append("Parking")
    return tags


def _meta_for(restaurant: Restaurant) -> dict[str, str]:
    slug = slugify(restaurant.name)
    return RESTAURANT_META.get(
        slug,
        {
            "phone": "+91 80000 00000",
            "address": "Along your highway route",
            "hours": "7:00 AM - 10:00 PM",
            "about": f"{restaurant.name} is a convenient highway stop serving {restaurant.famous_for.lower()}.",
        },
    )


def build_summary(
    restaurant: Restaurant,
    *,
    score: Optional[float] = None,
    reason: Optional[str] = None,
    dish: Optional[str] = None,
    distance_km: Optional[float] = None,
    distance_from_route_km: Optional[float] = None,
    detour_km: Optional[float] = None,
    time_to_reach_minutes: Optional[int] = None,
    distance_from_origin_km: Optional[float] = None,
) -> RestaurantSummary:
    meta = _meta_for(restaurant)
    resolved_distance_from_route_km = distance_from_route_km if distance_from_route_km is not None else restaurant.distance_from_route_km
    resolved_detour_km = detour_km if detour_km is not None else restaurant.detour_km
    return RestaurantSummary(
        id=slugify(restaurant.name),
        name=restaurant.name,
        famous_for=restaurant.famous_for,
        rating=restaurant.rating,
        distance_km=distance_km if distance_km is not None else distance_from_origin_km,
        distance_from_route_km=resolved_distance_from_route_km,
        detour_km=resolved_detour_km,
        time_to_reach_minutes=time_to_reach_minutes if time_to_reach_minutes is not None else compute_eta_minutes(restaurant),
        distance_from_origin_km=distance_from_origin_km if distance_from_origin_km is not None else restaurant.distance_from_bangalore_km,
        matching_dishes=match_dishes(restaurant, dish),
        phone=meta["phone"],
        address=meta["address"],
        is_open=True,
        tags=build_tags(restaurant),
        score=score,
        reason=reason,
        lat=restaurant.lat,
        lon=restaurant.lon,
    )


def build_detail(
    restaurant: Restaurant,
    *,
    route: RouteSummary,
    related: list[Restaurant],
) -> RestaurantDetail:
    meta = _meta_for(restaurant)
    suggested_stops = [
        build_summary(candidate)
        for candidate in related
        if slugify(candidate.name) != slugify(restaurant.name)
    ][:3]
    return RestaurantDetail(
        **build_summary(restaurant).model_dump(),
        dishes=[dish.title() for dish in restaurant.dishes],
        highway=route.highway,
        hours=meta["hours"],
        about=meta["about"],
        amenities=build_tags(restaurant),
        suggested_stops=suggested_stops,
    )
