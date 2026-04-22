"""
Pydantic models for the Highway Food discovery API.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lat: float
    lon: float


class RouteSummary(BaseModel):
    id: str
    origin: str
    destination: str
    highway: str
    distance_km: float = Field(..., ge=0)
    eta_minutes: int = Field(..., ge=0)
    coordinates: List[Coordinate]


class Restaurant(BaseModel):
    """Represents a restaurant/food stop loaded from data.json."""

    name: str
    lat: float
    lon: float
    distance_from_route_km: float = Field(..., ge=0)
    detour_km: float = Field(..., ge=0)
    famous_for: str
    dishes: List[str]
    rating: float = Field(..., ge=0, le=5)
    washroom: bool
    parking: bool
    fast_service: bool
    type: str
    distance_from_bangalore_km: Optional[float] = Field(default=None, ge=0)
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None


class RestaurantSummary(BaseModel):
    id: str
    name: str
    famous_for: str
    rating: float
    distance_km: Optional[float] = None
    distance_from_route_km: float
    detour_km: float
    time_to_reach_minutes: int
    distance_from_origin_km: Optional[float] = None
    matching_dishes: List[str] = []
    phone: str
    address: str
    is_open: bool
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None
    hours: Optional[str] = None
    tags: List[str]
    score: Optional[float] = None
    reason: Optional[str] = None
    lat: float
    lon: float


class RestaurantDetail(RestaurantSummary):
    dishes: List[str]
    highway: str
    hours: str
    about: str
    amenities: List[str]
    suggested_stops: List[RestaurantSummary]


class RecommendedStop(RestaurantSummary):
    pass


class RecommendationResponse(BaseModel):
    status: str = "ok"
    mode: str
    results: List[RecommendedStop]
    message: Optional[str] = None


class DirectionsResponse(BaseModel):
    status: str = "ok"
    route: RouteSummary
    message: Optional[str] = None


class HomeResponse(BaseModel):
    route: RouteSummary
    featured_stops: List[RestaurantSummary]
    popular_dishes: List[str]


class DishSearchResponse(BaseModel):
    query: str = ""
    route_id: str
    popular_dishes: List[str]
    results: List[str]


class RestaurantListResponse(BaseModel):
    route: RouteSummary
    dish: Optional[str] = None
    restaurants: List[RestaurantSummary]
