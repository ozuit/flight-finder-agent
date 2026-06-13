"""Flight price tracking — persistent storage and price-check logic."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from integrations.zalo_bot import ZaloBotClient
    from tools.flight_providers import FlightOffer

logger = logging.getLogger(__name__)

TRACKER_FILE = os.environ.get("FLIGHT_TRACKER_FILE", "flight_tracker.json")

# Minimum price change (USD) to trigger a notification
PRICE_CHANGE_THRESHOLD_USD = float(
    os.environ.get("PRICE_CHANGE_THRESHOLD_USD", "5.0")
)


@dataclass
class TrackedFlight:
    tracking_id: str
    user_id: str
    # Zalo chat_id to push notifications to (may differ from user_id)
    chat_id: str
    origin: str
    destination: str
    departure_date: str
    passengers: int
    cabin_class: str
    # Snapshot price at the time of tracking
    last_price_usd: float
    flight_number: str = ""
    airline: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_checked_at: Optional[str] = None


class FlightTracker:
    """Thread-safe JSON-backed store for tracked flights."""

    def __init__(self, filepath: str = TRACKER_FILE) -> None:
        self._filepath = filepath
        self._data: dict[str, TrackedFlight] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self._filepath):
            return
        try:
            with open(self._filepath, encoding="utf-8") as fh:
                raw: dict = json.load(fh)
            self._data = {k: TrackedFlight(**v) for k, v in raw.items()}
        except Exception:
            logger.exception("Could not load tracker file %s", self._filepath)

    def _save(self) -> None:
        tmp = self._filepath + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(
                    {k: asdict(v) for k, v in self._data.items()},
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
            os.replace(tmp, self._filepath)
        except Exception:
            logger.exception("Could not save tracker file %s", self._filepath)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        user_id: str,
        chat_id: str,
        origin: str,
        destination: str,
        departure_date: str,
        passengers: int,
        cabin_class: str,
        last_price_usd: float,
        flight_number: str = "",
        airline: str = "",
    ) -> TrackedFlight:
        tracking_id = str(uuid.uuid4())[:8]
        entry = TrackedFlight(
            tracking_id=tracking_id,
            user_id=user_id,
            chat_id=chat_id,
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            passengers=passengers,
            cabin_class=cabin_class,
            last_price_usd=last_price_usd,
            flight_number=flight_number,
            airline=airline,
        )
        self._data[tracking_id] = entry
        self._save()
        return entry

    def remove(self, tracking_id: str) -> bool:
        if tracking_id in self._data:
            del self._data[tracking_id]
            self._save()
            return True
        return False

    def list_for_user(self, user_id: str) -> list[TrackedFlight]:
        return [t for t in self._data.values() if t.user_id == user_id]

    def all(self) -> list[TrackedFlight]:
        return list(self._data.values())

    def update_price(self, tracking_id: str, new_price_usd: float) -> None:
        if tracking_id in self._data:
            self._data[tracking_id].last_price_usd = new_price_usd
            self._data[tracking_id].last_checked_at = datetime.now().isoformat()
            self._save()

    # ------------------------------------------------------------------
    # Price check & notification
    # ------------------------------------------------------------------

    async def check_all_and_notify(
        self,
        flight_provider,
        bot_client: Optional["ZaloBotClient"],
    ) -> list[dict]:
        """Check current prices for all tracked flights and notify on changes.

        Returns a list of change records (useful for the /check-price-alerts endpoint).
        """
        changes: list[dict] = []
        for entry in self.all():
            try:
                offers = flight_provider.search(
                    origin=entry.origin,
                    destination=entry.destination,
                    departure_date=entry.departure_date,
                    passengers=entry.passengers,
                    cabin_class=entry.cabin_class,
                )
            except Exception:
                logger.exception(
                    "Price check failed for tracking_id=%s", entry.tracking_id
                )
                continue

            if not offers:
                continue

            # Use cheapest available price for that route as the reference
            current_price = min(o.price_usd for o in offers)
            delta = current_price - entry.last_price_usd

            if abs(delta) < PRICE_CHANGE_THRESHOLD_USD:
                self.update_price(entry.tracking_id, current_price)
                continue

            direction = "giảm" if delta < 0 else "tăng"
            change_record = {
                "tracking_id": entry.tracking_id,
                "user_id": entry.user_id,
                "route": f"{entry.origin} → {entry.destination}",
                "departure_date": entry.departure_date,
                "old_price_usd": entry.last_price_usd,
                "new_price_usd": current_price,
                "delta_usd": delta,
            }
            changes.append(change_record)

            if bot_client:
                msg = _format_price_change_notification(
                    entry=entry,
                    current_price=current_price,
                    delta=delta,
                    direction=direction,
                )
                try:
                    await bot_client.send_message(entry.chat_id, msg)
                except Exception:
                    logger.exception(
                        "Failed to send Zalo notification for tracking_id=%s",
                        entry.tracking_id,
                    )

            self.update_price(entry.tracking_id, current_price)

        return changes


def _format_price_change_notification(
    entry: TrackedFlight,
    current_price: float,
    delta: float,
    direction: str,
) -> str:
    old_vnd = int(entry.last_price_usd * 25000)
    new_vnd = int(current_price * 25000)
    arrow = "📉" if delta < 0 else "📈"
    flight_label = (
        f"{entry.airline} {entry.flight_number} — "
        if entry.airline or entry.flight_number
        else ""
    )
    return (
        f"{arrow} **Cập nhật giá vé!**\n\n"
        f"✈ {flight_label}{entry.origin} → {entry.destination}\n"
        f"📅 Ngày bay: {entry.departure_date}\n"
        f"💰 Giá {direction}: "
        f"${entry.last_price_usd:,.2f} (~{old_vnd:,}đ) → "
        f"${current_price:,.2f} (~{new_vnd:,}đ) "
        f"({'−' if delta < 0 else '+'}{abs(delta):,.2f} USD)\n\n"
        f"_(Mã theo dõi: {entry.tracking_id})_"
    )
