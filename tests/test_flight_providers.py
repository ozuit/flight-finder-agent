import os
import unittest
from unittest.mock import patch

from tools.flight_providers import SerpApiFlightProvider, get_provider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params):
        self.calls.append((url, params))
        return FakeResponse(self.payload)


SERPAPI_RESPONSE = {
    "search_metadata": {
        "status": "Success",
        "google_flights_url": "https://www.google.com/travel/flights/example",
    },
    "best_flights": [
        {
            "flights": [
                {
                    "departure_airport": {
                        "id": "HAN",
                        "time": "2026-07-20 08:00",
                    },
                    "arrival_airport": {
                        "id": "DAD",
                        "time": "2026-07-20 09:25",
                    },
                    "duration": 85,
                    "airplane": "Airbus A321",
                    "airline": "Vietnam Airlines",
                    "travel_class": "Business",
                    "flight_number": "VN 165",
                    "extensions": ["Wi-Fi for a fee"],
                }
            ],
            "total_duration": 85,
            "price": 240,
            "type": "Round trip",
            "carbon_emissions": {"this_flight": 84000},
        }
    ],
    "other_flights": [
        {
            "flights": [
                {
                    "departure_airport": {
                        "id": "HAN",
                        "time": "2026-07-20 10:00",
                    },
                    "arrival_airport": {
                        "id": "SGN",
                        "time": "2026-07-20 12:10",
                    },
                    "duration": 130,
                    "airplane": "Airbus A320",
                    "airline": "VietJet Air",
                    "travel_class": "Business",
                    "flight_number": "VJ 123",
                    "extensions": [],
                },
                {
                    "departure_airport": {
                        "id": "SGN",
                        "time": "2026-07-20 13:20",
                    },
                    "arrival_airport": {
                        "id": "DAD",
                        "time": "2026-07-20 14:40",
                    },
                    "duration": 80,
                    "airplane": "Airbus A321",
                    "airline": "VietJet Air",
                    "travel_class": "Business",
                    "flight_number": "VJ 456",
                    "extensions": ["In-seat power"],
                },
            ],
            "layovers": [{"id": "SGN", "duration": 70}],
            "total_duration": 280,
            "price": 120,
            "type": "Round trip",
        }
    ],
}


class SerpApiFlightProviderTest(unittest.TestCase):
    def make_provider(self):
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"}, clear=False):
            provider = SerpApiFlightProvider()
        provider._client = FakeClient(SERPAPI_RESPONSE)
        return provider

    def test_search_maps_and_sorts_google_flights_results(self):
        provider = self.make_provider()

        offers = provider.search(
            origin="Hà Nội",
            destination="Đà Nẵng",
            departure_date="2026-07-20",
            return_date="2026-07-25",
            passengers=2,
            cabin_class="BUSINESS",
        )

        self.assertEqual([offer.price_usd for offer in offers], [120.0, 240.0])
        self.assertEqual(offers[0].origin, "HAN")
        self.assertEqual(offers[0].destination, "DAD")
        self.assertEqual(offers[0].stops, 1)
        self.assertEqual(offers[0].stop_cities, ["SGN"])
        self.assertIsNone(offers[0].seats_available)
        self.assertIsNone(offers[0].baggage_allowance_kg)
        self.assertTrue(offers[0].flight_id.startswith("serpapi-"))

        _, params = provider._client.calls[0]
        self.assertEqual(params["departure_id"], "HAN")
        self.assertEqual(params["arrival_id"], "DAD")
        self.assertEqual(params["type"], "1")
        self.assertEqual(params["return_date"], "2026-07-25")
        self.assertEqual(params["travel_class"], "3")
        self.assertEqual(params["adults"], "2")
        self.assertEqual(params["currency"], "USD")

        details = provider.get_details(offers[0].flight_id)
        self.assertEqual(details["provider"], "SerpAPI / Google Flights")
        self.assertEqual(details["return_date"], "2026-07-25")
        self.assertIn("SGN: 70 phút", details["layovers"])

    def test_search_applies_maximum_budget(self):
        provider = self.make_provider()

        offers = provider.search(
            origin="HAN",
            destination="DAD",
            departure_date="2026-07-20",
            max_price_usd=150,
        )

        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].price_usd, 120.0)
        _, params = provider._client.calls[0]
        self.assertEqual(params["type"], "2")
        self.assertNotIn("return_date", params)

    def test_factory_selects_serpapi(self):
        with patch.dict(
            os.environ,
            {
                "FLIGHT_API_PROVIDER": "serpapi",
                "SERPAPI_API_KEY": "test-key",
            },
            clear=False,
        ):
            provider = get_provider()

        self.assertIsInstance(provider, SerpApiFlightProvider)


if __name__ == "__main__":
    unittest.main()
