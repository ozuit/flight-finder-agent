"""Flight data providers: Mock (dev/test) and SerpAPI."""

from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class FlightOffer:
    flight_id: str
    airline: str
    airline_code: str
    flight_number: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    stops: int
    stop_cities: list[str]
    cabin_class: str
    price_usd: float
    price_vnd: int
    seats_available: Optional[int]
    baggage_allowance_kg: Optional[int]
    meal_included: Optional[bool]

    def to_dict(self) -> dict:
        return {
            "flight_id": self.flight_id,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "origin": self.origin,
            "destination": self.destination,
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "duration": f"{self.duration_minutes // 60}h {self.duration_minutes % 60}m",
            "stops": self.stops,
            "stop_cities": self.stop_cities,
            "cabin_class": self.cabin_class,
            "price_usd": self.price_usd,
            "price_vnd": self.price_vnd,
            "seats_available": self.seats_available,
            "baggage_kg": self.baggage_allowance_kg,
            "meal_included": self.meal_included,
        }


# IATA airport codes → city names (Vietnamese airports + major international)
AIRPORT_NAMES: dict[str, str] = {
    "HAN": "Hà Nội (Nội Bài)",
    "SGN": "Hồ Chí Minh (Tân Sơn Nhất)",
    "DAD": "Đà Nẵng",
    "CXR": "Nha Trang (Cam Ranh)",
    "DLI": "Đà Lạt",
    "PQC": "Phú Quốc",
    "UIH": "Quy Nhơn",
    "HPH": "Hải Phòng (Cát Bi)",
    "BKK": "Bangkok (Suvarnabhumi)",
    "SIN": "Singapore (Changi)",
    "NRT": "Tokyo (Narita)",
    "ICN": "Seoul (Incheon)",
    "HKG": "Hong Kong",
    "CDG": "Paris (Charles de Gaulle)",
    "LHR": "London (Heathrow)",
    "LAX": "Los Angeles",
    "JFK": "New York (JFK)",
    "DXB": "Dubai",
    "SYD": "Sydney",
    "KUL": "Kuala Lumpur (KLIA)",
}

# City name aliases → IATA code
CITY_ALIASES: dict[str, str] = {
    "hà nội": "HAN",
    "hanoi": "HAN",
    "ha noi": "HAN",
    "nội bài": "HAN",
    "hồ chí minh": "SGN",
    "ho chi minh": "SGN",
    "sài gòn": "SGN",
    "saigon": "SGN",
    "tp.hcm": "SGN",
    "hcm": "SGN",
    "đà nẵng": "DAD",
    "da nang": "DAD",
    "danang": "DAD",
    "nha trang": "CXR",
    "đà lạt": "DLI",
    "da lat": "DLI",
    "dalat": "DLI",
    "phú quốc": "PQC",
    "phu quoc": "PQC",
    "quy nhơn": "UIH",
    "quy nhon": "UIH",
    "hải phòng": "HPH",
    "hai phong": "HPH",
    "bangkok": "BKK",
    "singapore": "SIN",
    "tokyo": "NRT",
    "seoul": "ICN",
    "hong kong": "HKG",
    "paris": "CDG",
    "london": "LHR",
    "los angeles": "LAX",
    "new york": "JFK",
    "dubai": "DXB",
    "sydney": "SYD",
    "kuala lumpur": "KUL",
}

MOCK_AIRLINES = [
    ("Vietnam Airlines", "VN"),
    ("VietJet Air", "VJ"),
    ("Bamboo Airways", "QH"),
    ("Pacific Airlines", "BL"),
    ("Thai Airways", "TG"),
    ("Singapore Airlines", "SQ"),
    ("Cathay Pacific", "CX"),
    ("Korean Air", "KE"),
    ("Japan Airlines", "JL"),
    ("Emirates", "EK"),
]


def resolve_airport(name: str) -> Optional[str]:
    """Resolve city name or IATA code to IATA code."""
    code = name.strip().upper()
    if code in AIRPORT_NAMES:
        return code
    normalized = name.strip().lower()
    return CITY_ALIASES.get(normalized)


class MockFlightProvider:
    """Generates realistic mock flight data for dev/test."""

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        passengers: int = 1,
        cabin_class: str = "ECONOMY",
        max_price_usd: Optional[float] = None,
        return_date: Optional[str] = None,
    ) -> list[FlightOffer]:
        random.seed(f"{origin}{destination}{departure_date}")
        origin_code = resolve_airport(origin) or origin.upper()
        dest_code = resolve_airport(destination) or destination.upper()

        # Determine route type for realistic pricing
        is_domestic = origin_code in AIRPORT_NAMES and dest_code in AIRPORT_NAMES
        is_domestic = is_domestic and all(
            c in ["HAN", "SGN", "DAD", "CXR", "DLI", "PQC", "UIH", "HPH"]
            for c in [origin_code, dest_code]
        )

        base_price = 30 if is_domestic else 200
        price_range = (base_price, base_price * 4)

        # Multiplier by cabin class
        cabin_multipliers = {
            "ECONOMY": 1.0,
            "PREMIUM_ECONOMY": 1.8,
            "BUSINESS": 3.5,
            "FIRST": 6.0,
        }
        cabin_mult = cabin_multipliers.get(cabin_class.upper(), 1.0)

        airlines = random.sample(MOCK_AIRLINES, min(5, len(MOCK_AIRLINES)))
        offers: list[FlightOffer] = []

        for i, (airline_name, code) in enumerate(airlines):
            price_usd = round(
                random.uniform(*price_range) * cabin_mult * passengers, 2
            )
            if max_price_usd and price_usd > max_price_usd:
                continue

            duration = random.randint(60, 180) if is_domestic else random.randint(180, 720)
            stops = 0 if random.random() > 0.4 else 1
            stop_cities = []
            if stops:
                stop_cities = [random.choice(["SGN", "BKK", "SIN", "KUL"])]
                duration += 90  # layover

            dep_hour = random.randint(5, 22)
            dep_minute = random.choice([0, 15, 30, 45])
            dep_dt = datetime.strptime(departure_date, "%Y-%m-%d").replace(
                hour=dep_hour, minute=dep_minute
            )
            arr_dt = dep_dt + timedelta(minutes=duration)

            offers.append(
                FlightOffer(
                    flight_id=f"{code}{random.randint(100,999)}-{i}",
                    airline=airline_name,
                    airline_code=code,
                    flight_number=f"{code}{random.randint(100,999)}",
                    origin=origin_code,
                    destination=dest_code,
                    departure_time=dep_dt.strftime("%Y-%m-%dT%H:%M"),
                    arrival_time=arr_dt.strftime("%Y-%m-%dT%H:%M"),
                    duration_minutes=duration,
                    stops=stops,
                    stop_cities=stop_cities,
                    cabin_class=cabin_class.upper(),
                    price_usd=price_usd,
                    price_vnd=int(price_usd * 25000),
                    seats_available=random.randint(1, 30),
                    baggage_allowance_kg=23 if cabin_class.upper() == "ECONOMY" else 32,
                    meal_included=cabin_class.upper() != "ECONOMY" or random.random() > 0.5,
                )
            )

        return sorted(offers, key=lambda f: f.price_usd)

    def get_details(self, flight_id: str) -> Optional[dict]:
        """Return extra details for a flight (mock)."""
        return {
            "flight_id": flight_id,
            "aircraft": random.choice(["Boeing 737", "Airbus A320", "Boeing 787", "Airbus A350"]),
            "wifi": random.choice([True, False]),
            "power_outlets": True,
            "entertainment": random.choice(["Personal screen", "None", "Streaming"]),
            "cancellation_policy": "Free cancellation within 24h of booking",
        }


class SerpApiFlightProvider:
    """
    SerpAPI Google Flights provider.
    Requires SERPAPI_API_KEY.
    Docs: https://serpapi.com/google-flights-api
    """

    SEARCH_URL = "https://serpapi.com/search.json"

    def __init__(self):
        import httpx
        self.api_key = os.environ.get("SERPAPI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "SERPAPI_API_KEY is required for SerpAPI provider. "
                "Get one at https://serpapi.com/manage-api-key, or set "
                "FLIGHT_API_PROVIDER=mock to use mock data."
            )
        self.gl = os.environ.get("SERPAPI_GL", "vn")
        self.hl = os.environ.get("SERPAPI_HL", "vi")
        self.deep_search = os.environ.get("SERPAPI_DEEP_SEARCH", "").lower() in {
            "1",
            "true",
            "yes",
        }
        self._client = httpx.Client(timeout=30)
        self._details: dict[str, dict] = {}

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        passengers: int = 1,
        cabin_class: str = "ECONOMY",
        max_price_usd: Optional[float] = None,
        return_date: Optional[str] = None,
    ) -> list[FlightOffer]:
        origin_code = resolve_airport(origin) or origin.upper()
        dest_code = resolve_airport(destination) or destination.upper()

        cabin_map = {
            "ECONOMY": "1",
            "PREMIUM_ECONOMY": "2",
            "BUSINESS": "3",
            "FIRST": "4",
        }
        params = {
            "engine": "google_flights",
            "api_key": self.api_key,
            "departure_id": origin_code,
            "arrival_id": dest_code,
            "outbound_date": departure_date,
            "type": "1" if return_date else "2",
            "travel_class": cabin_map.get(cabin_class.upper(), "1"),
            "adults": str(passengers),
            "currency": "USD",
            "sort_by": "2",
            "gl": self.gl,
            "hl": self.hl,
        }
        if return_date:
            params["return_date"] = return_date
        if self.deep_search:
            params["deep_search"] = "true"

        resp = self._client.get(self.SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"SerpAPI error: {data['error']}")

        raw_offers = data.get("best_flights", []) + data.get("other_flights", [])
        google_flights_url = data.get("search_metadata", {}).get("google_flights_url", "")

        offers: list[FlightOffer] = []
        for raw in raw_offers:
            try:
                price_usd = float(raw["price"])
                if max_price_usd and price_usd > max_price_usd:
                    continue

                segments = raw["flights"]
                first_seg = segments[0]
                last_seg = segments[-1]
                airlines = list(dict.fromkeys(
                    segment.get("airline", "") for segment in segments if segment.get("airline")
                ))
                flight_numbers = [
                    segment.get("flight_number", "")
                    for segment in segments
                    if segment.get("flight_number")
                ]
                first_flight_number = flight_numbers[0] if flight_numbers else ""
                airline_code = first_flight_number.split(" ")[0]
                stop_cities = [
                    layover.get("id", layover.get("name", ""))
                    for layover in raw.get("layovers", [])
                ]
                stop_cities = [city for city in stop_cities if city]
                flight_id = self._flight_id(raw)
                offer = FlightOffer(
                    flight_id=flight_id,
                    airline=" / ".join(airlines) or "Unknown airline",
                    airline_code=airline_code,
                    flight_number=" / ".join(flight_numbers),
                    origin=first_seg["departure_airport"]["id"],
                    destination=last_seg["arrival_airport"]["id"],
                    departure_time=first_seg["departure_airport"]["time"].replace(" ", "T"),
                    arrival_time=last_seg["arrival_airport"]["time"].replace(" ", "T"),
                    duration_minutes=int(raw.get("total_duration", 0)),
                    stops=max(len(segments) - 1, len(stop_cities)),
                    stop_cities=stop_cities,
                    cabin_class=cabin_class.upper(),
                    price_usd=price_usd,
                    price_vnd=int(price_usd * 25000),
                    seats_available=None,
                    baggage_allowance_kg=None,
                    meal_included=None,
                )
                offers.append(offer)
                self._details[flight_id] = self._build_details(
                    raw=raw,
                    return_date=return_date,
                    google_flights_url=google_flights_url,
                )
            except (KeyError, IndexError, TypeError, ValueError):
                continue

        return sorted(offers, key=lambda f: f.price_usd)

    def get_details(self, flight_id: str) -> Optional[dict]:
        return self._details.get(flight_id)

    @staticmethod
    def _flight_id(raw: dict) -> str:
        serialized = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
        return f"serpapi-{digest}"

    @staticmethod
    def _build_details(raw: dict, return_date: Optional[str], google_flights_url: str) -> dict:
        segments = raw.get("flights", [])
        itinerary = []
        aircraft = []
        amenities = []
        for segment in segments:
            departure = segment.get("departure_airport", {})
            arrival = segment.get("arrival_airport", {})
            itinerary.append(
                f"{departure.get('id', '?')} {departure.get('time', '')} -> "
                f"{arrival.get('id', '?')} {arrival.get('time', '')} "
                f"({segment.get('flight_number', '')})"
            )
            if segment.get("airplane"):
                aircraft.append(segment["airplane"])
            amenities.extend(segment.get("extensions", []))

        layovers = [
            f"{layover.get('id', layover.get('name', '?'))}: "
            f"{layover.get('duration', 0)} phút"
            for layover in raw.get("layovers", [])
        ]
        emissions = raw.get("carbon_emissions", {})
        return {
            "provider": "SerpAPI / Google Flights",
            "trip_type": raw.get("type", "Round trip" if return_date else "One way"),
            "return_date": return_date or "N/A",
            "itinerary": itinerary,
            "layovers": layovers or ["Bay thẳng"],
            "aircraft": list(dict.fromkeys(aircraft)) or ["Không có dữ liệu"],
            "amenities": list(dict.fromkeys(amenities)) or ["Không có dữ liệu"],
            "carbon_emissions_grams": emissions.get("this_flight", "Không có dữ liệu"),
            "google_flights_url": google_flights_url or "Không có dữ liệu",
        }


def get_provider():
    """Return the configured flight provider based on FLIGHT_API_PROVIDER env var."""
    provider_name = os.environ.get("FLIGHT_API_PROVIDER", "mock").lower()
    if provider_name in {"serpapi", "serp_api"}:
        return SerpApiFlightProvider()
    return MockFlightProvider()
