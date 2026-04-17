"""
Highway Food Discovery API.

Run:
    uvicorn main:app --reload
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))

from models import Coordinate, DishSearchResponse, HomeResponse, RecommendationResponse, RestaurantDetail, RestaurantListResponse, RouteSummary
from services.catalog import build_detail, build_summary, filter_restaurants, get_route, popular_dishes, slugify
from services.dynamic_route import fetch_route_coordinates
from services.loader import load_restaurants
from services.ranking import rank_restaurants, search_restaurants_by_craving

app = FastAPI(
    title="Highway Food Discovery API",
    description="Route-aware food discovery endpoints for highway journeys.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_restaurants = []
DEFAULT_ROUTE_ID = "bangalore-mysore"


@app.on_event("startup")
def startup_event() -> None:
    global _restaurants
    _restaurants = load_restaurants()


def _ensure_restaurants():
    if not _restaurants:
        raise HTTPException(
            status_code=503,
            detail="Restaurant data unavailable. Check that data/data.json exists.",
        )


def _route_or_error(route_id: Optional[str]) -> RouteSummary:
    if not route_id:
        raise HTTPException(
            status_code=400,
            detail="route_id is required for this legacy endpoint. Use /recommend with lat, lon, dest_lat, and dest_lon for dynamic routes.",
        )
    try:
        return get_route(route_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown legacy route_id '{route_id}'. Use /recommend with lat, lon, dest_lat, and dest_lon for dynamic routes.",
        ) from exc


def _build_dynamic_route_summary(
    *,
    origin: Coordinate,
    destination: Coordinate,
    route_coordinates: list[Coordinate],
) -> RouteSummary:
    distance_km = _haversine_km(origin.lat, origin.lon, destination.lat, destination.lon)
    return RouteSummary(
        id="dynamic-route",
        origin=f"{origin.lat:.4f}, {origin.lon:.4f}",
        destination=f"{destination.lat:.4f}, {destination.lon:.4f}",
        highway="Dynamic Route",
        distance_km=round(distance_km, 1),
        eta_minutes=max(20, round((distance_km / 55.0) * 60)),
        coordinates=route_coordinates,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

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


@app.get("/", tags=["Info"], summary="API info")
def root() -> JSONResponse:
    return JSONResponse(
        content={
            "message": "Welcome to the Highway Food Discovery API",
            "docs": "/docs",
            "health": "/health",
            "recommend": "/recommend?lat=12.9716&lon=77.5946&dest_lat=12.2958&dest_lon=76.6394",
        }
    )


@app.get("/health", tags=["Health"], summary="Health check")
def health_check() -> JSONResponse:
    return JSONResponse(
        content={
            "status": "ok",
            "restaurants_loaded": len(_restaurants),
            "dynamic_routing": True,
        }
    )


@app.get("/routes", response_model=list[RouteSummary], tags=["Routes"], summary="List supported routes")
def list_routes() -> list[RouteSummary]:
    return [get_route(DEFAULT_ROUTE_ID)]


@app.get("/home", response_model=HomeResponse, tags=["Discovery"], summary="Legacy route home data", deprecated=True)
def home(route_id: str = Query(DEFAULT_ROUTE_ID)) -> HomeResponse:
    _ensure_restaurants()
    route = _route_or_error(route_id)
    route_restaurants = filter_restaurants(_restaurants, route_id=route.id)
    featured_stops = rank_restaurants(
        route_restaurants,
        origin=route.coordinates[0],
        route_coordinates=route.coordinates,
        top_n=4,
    )
    return HomeResponse(
        route=route,
        featured_stops=featured_stops,
        popular_dishes=popular_dishes(route_restaurants),
    )


@app.get("/dishes", response_model=DishSearchResponse, tags=["Discovery"], summary="Legacy route dish search", deprecated=True)
def dishes(
    route_id: str = Query(DEFAULT_ROUTE_ID),
    query: str = Query(default=""),
) -> DishSearchResponse:
    _ensure_restaurants()
    route = _route_or_error(route_id)
    route_restaurants = filter_restaurants(_restaurants, route_id=route.id)
    all_popular = popular_dishes(route_restaurants, limit=10)
    query_lower = query.strip().lower()
    results = [
        dish for dish in all_popular if query_lower in dish.lower()
    ] if query_lower else all_popular[:6]

    if query_lower:
        extra_matches = {
            candidate.title()
            for restaurant in route_restaurants
            for candidate in restaurant.dishes
            if query_lower in candidate.lower()
        }
        results = sorted(set(results).union(extra_matches))

    return DishSearchResponse(
        query=query,
        route_id=route.id,
        popular_dishes=all_popular,
        results=results[:10],
    )


@app.get("/restaurants", response_model=RestaurantListResponse, tags=["Discovery"], summary="Route restaurant list")
def restaurants(
    route_id: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None),
    dest_lat: Optional[float] = Query(default=None),
    dest_lon: Optional[float] = Query(default=None),
    dish: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=20),
) -> RestaurantListResponse:
    _ensure_restaurants()

    if lat is not None and lon is not None and dest_lat is not None and dest_lon is not None:
        origin = Coordinate(lat=lat, lon=lon)
        destination = Coordinate(lat=dest_lat, lon=dest_lon)
        route_coordinates = fetch_route_coordinates(origin, destination)
        route = _build_dynamic_route_summary(
            origin=origin,
            destination=destination,
            route_coordinates=route_coordinates,
        )

        if dish:
            summaries = search_restaurants_by_craving(
                _restaurants,
                origin=origin,
                route_coordinates=route_coordinates,
                craving=dish,
                limit=limit,
            )
        else:
            summaries = rank_restaurants(
                _restaurants,
                origin=origin,
                route_coordinates=route_coordinates,
                top_n=limit,
            )

        return RestaurantListResponse(route=route, dish=dish, restaurants=summaries)

    route = _route_or_error(route_id)
    route_restaurants = filter_restaurants(_restaurants, route_id=route.id, dish=dish)

    if dish:
        sorted_restaurants = sorted(
            route_restaurants,
            key=lambda restaurant: (
                0 if any(dish.lower() in candidate.lower() for candidate in restaurant.dishes) else 1,
                restaurant.distance_from_route_km,
                -restaurant.rating,
            ),
        )
        summaries = [build_summary(restaurant, dish=dish) for restaurant in sorted_restaurants[:limit]]
    else:
        summaries = rank_restaurants(
            route_restaurants,
            origin=route.coordinates[0],
            route_coordinates=route.coordinates,
            top_n=limit,
        )

    return RestaurantListResponse(route=route, dish=dish, restaurants=summaries)


@app.get(
    "/restaurants/{restaurant_id}",
    response_model=RestaurantDetail,
    tags=["Discovery"],
    summary="Restaurant details",
)
def restaurant_detail(
    restaurant_id: str,
    route_id: str = Query(DEFAULT_ROUTE_ID),
) -> RestaurantDetail:
    _ensure_restaurants()
    route = _route_or_error(route_id)
    route_restaurants = filter_restaurants(_restaurants, route_id=route.id)
    restaurant = next(
        (candidate for candidate in route_restaurants if slugify(candidate.name) == restaurant_id),
        None,
    )
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    related = sorted(
        route_restaurants,
        key=lambda candidate: (candidate.distance_from_route_km, -candidate.rating),
    )
    return build_detail(restaurant, route=route, related=related)


@app.get(
    "/recommend",
    response_model=RecommendationResponse,
    tags=["Recommendations"],
    summary="Compatibility endpoint for top ranked stops",
)
def recommend(
    lat: float = Query(..., description="Current latitude", example=12.9716),
    lon: float = Query(..., description="Current longitude", example=77.5946),
    craving: Optional[str] = Query(default=None),
    dest_lat: Optional[float] = Query(default=None, description="Destination latitude"),
    dest_lon: Optional[float] = Query(default=None, description="Destination longitude"),
) -> RecommendationResponse:
    _ensure_restaurants()
    if dest_lat is None or dest_lon is None:
        raise HTTPException(status_code=422, detail="dest_lat and dest_lon are required.")

    origin = Coordinate(lat=lat, lon=lon)
    destination = Coordinate(lat=dest_lat, lon=dest_lon)
    print(
        "[recommend] request",
        {
            "origin": {"lat": round(origin.lat, 4), "lon": round(origin.lon, 4)},
            "destination": {"lat": round(destination.lat, 4), "lon": round(destination.lon, 4)},
            "craving": craving,
        },
    )
    route_coordinates = fetch_route_coordinates(origin, destination)
    print(f"[recommend] route_points={len(route_coordinates)}")
    resolved_craving = craving.strip().lower() if isinstance(craving, str) and craving.strip() else None

    if resolved_craving:
        matched_results = search_restaurants_by_craving(
            _restaurants,
            origin=origin,
            route_coordinates=route_coordinates,
            craving=resolved_craving,
            limit=10,
        )
        if matched_results:
            return RecommendationResponse(status="ok", mode="craving", results=matched_results)

    top_stops = rank_restaurants(
        _restaurants,
        origin=origin,
        route_coordinates=route_coordinates,
        top_n=3,
    )
    if not top_stops:
        return RecommendationResponse(
            status="no_results",
            mode="default",
            results=[],
            message="No restaurants found.",
        )
    return RecommendationResponse(status="ok", mode="default", results=top_stops)
