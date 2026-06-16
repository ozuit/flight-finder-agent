"""
Flight Finder Agent — GreenNode AgentBase
Helps users find the most suitable flights based on natural language requirements.
Framework: LangGraph + AgentBase Memory (short-term + long-term)
"""

import hmac
import os
from datetime import datetime, date
from typing import Annotated, Optional, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from greennode_agentbase import (
    GreenNodeAgentBaseApp,
    PingStatus,
    RequestContext,
)
from greennode_agentbase.memory import MemoryClient
from greennode_agentbase.memory.models import MemoryRecordSearchRequest
from greennode_agent_bridge import AgentBaseMemoryEvents

from integrations.zalo_bot import ZaloBotClient, ZaloWebhookHandler
from tools.flight_providers import (
    AIRPORT_NAMES,
    MOCK_AIRLINES,
    get_provider,
    resolve_airport,
)
from tools.flight_tracker import FlightTracker

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MEMORY_ID = os.environ.get("MEMORY_ID", "")
MEMORY_STRATEGY_ID = os.environ.get("MEMORY_STRATEGY_ID", "default")

LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")

ZALO_BOT_TOKEN = os.environ.get("ZALO_BOT_TOKEN", "")
ZALO_WEBHOOK_SECRET_TOKEN = os.environ.get("ZALO_WEBHOOK_SECRET_TOKEN", "")
ZALO_PARSE_MODE = os.environ.get("ZALO_PARSE_MODE", "markdown").strip() or None
ZALO_REQUEST_TIMEOUT_SECONDS = float(
    os.environ.get("ZALO_REQUEST_TIMEOUT_SECONDS", "15")
)

_missing_vars = [v for v, val in [
    ("LLM_MODEL", LLM_MODEL),
    ("LLM_BASE_URL", LLM_BASE_URL),
    ("LLM_API_KEY", LLM_API_KEY),
] if not val]
if _missing_vars:
    raise ValueError(
        f"Missing required env vars: {', '.join(_missing_vars)}. "
        "Set them in .env or use /agentbase-llm to get a GreenNode AIP key."
    )

if MEMORY_ID:
    checkpointer = AgentBaseMemoryEvents(memory_id=MEMORY_ID)
    memory_client = MemoryClient()
else:
    checkpointer = None
    memory_client = None

llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
)

flight_provider = get_provider()
flight_tracker = FlightTracker()

app = GreenNodeAgentBaseApp()

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Bạn là trợ lý tìm vé máy bay thông minh. Nhiệm vụ của bạn là:
1. Thu thập đủ thông tin cần thiết trước khi tìm kiếm — hỏi TỪNG CÁI MỘT nếu thiếu.
2. Tìm kiếm chuyến bay phù hợp và gợi ý top 3–5 kèm giải thích tại sao phù hợp.
3. Ghi nhớ và áp dụng sở thích của người dùng để cá nhân hóa kết quả.
4. Hỗ trợ theo dõi giá vé và thông báo khi có thay đổi.
5. Trả lời bằng ngôn ngữ người dùng sử dụng (tiếng Việt hoặc tiếng Anh).

Quy trình xử lý:
1. Gọi `recall_preferences` để kiểm tra sở thích đã lưu (hãng bay, hạng ghế, ngân sách...).
2. Gọi `validate_flight_request` với thông tin hiện có để xác định còn thiếu gì.
3. Nếu thiếu thông tin, hỏi người dùng TỪNG cái một (ưu tiên: điểm đi → điểm đến → ngày → hành khách).
4. Khi đủ thông tin, gọi `search_flights` (áp dụng sở thích đã lưu vào tham số).
5. Trình bày kết quả: xếp hạng top 3–5, GIẢI THÍCH từng lựa chọn (rẻ nhất / nhanh nhất / bay thẳng / phù hợp sở thích...). Mỗi chuyến bay đều có link 🔗 Đặt vé trong kết quả — HIỂN THỊ NGUYÊN VẸN link đó, KHÔNG tự tạo link khác, KHÔNG giải thích tại sao không có link.
6. Khi người dùng muốn theo dõi một chuyến bay: gọi `track_flight` với thông tin chuyến bay đó.
   - Nếu người dùng đang chat qua Zalo, dùng `chat_id` từ session_id (bỏ tiền tố "zalo:").
   - Nếu không xác định được chat_id, dùng user_id làm chat_id.
7. Khi người dùng muốn xem danh sách đang theo dõi: gọi `list_tracked_flights`.
8. Khi người dùng muốn huỷ theo dõi: gọi `untrack_flight` với tracking_id.

Quy tắc:
- KHÔNG tìm kiếm khi chưa có điểm đi, điểm đến và ngày bay.
- Hỏi từng câu ngắn gọn, không hỏi nhiều thứ cùng lúc.
- Với hành lý, suất ăn hoặc số ghế: nói rõ "không có dữ liệu" nếu provider không trả về.
- Nếu không có chuyến bay phù hợp ngân sách: thông báo và đề xuất thay đổi tiêu chí.
- Khi người dùng đề cập sở thích (hãng, hạng ghế, bữa ăn, hành lý...), gọi `remember_preference`.
- KHÔNG bịa đặt thông tin — chỉ dùng dữ liệu thực từ `search_flights`.
- Ngày hôm nay: {today}
"""

# ---------------------------------------------------------------------------
# Helper: actor_id and namespace
# ---------------------------------------------------------------------------


def _get_actor_id() -> str:
    config = get_config()
    return config["configurable"].get("actor_id", "anonymous")


def _namespace() -> str:
    return f"/strategies/{MEMORY_STRATEGY_ID}/actors/{_get_actor_id()}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def validate_flight_request(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[str] = None,
    passengers: Optional[int] = None,
    cabin_class: Optional[str] = None,
) -> str:
    """Check if all required information is present before calling search_flights.

    Call this after collecting user input to verify what's still missing.
    Returns either a list of missing fields to ask for, or confirms readiness to search.

    Args:
        origin: Departure city or IATA code provided by user so far (or None if not yet given).
        destination: Arrival city or IATA code provided by user so far (or None if not yet given).
        departure_date: Date in YYYY-MM-DD format (or None if not yet given).
        passengers: Number of passengers (or None if not yet given).
        cabin_class: ECONOMY/PREMIUM_ECONOMY/BUSINESS/FIRST (or None if not yet given).
    """
    missing = []
    if not origin:
        missing.append("điểm khởi hành (VD: Hà Nội, Đà Nẵng, HAN)")
    if not destination:
        missing.append("điểm đến")
    if not departure_date:
        missing.append("ngày bay (định dạng YYYY-MM-DD)")

    if missing:
        return "Còn thiếu thông tin: " + "; ".join(missing) + ". Hãy hỏi người dùng từng thông tin một."

    try:
        datetime.strptime(departure_date, "%Y-%m-%d")
    except ValueError:
        return f"Ngày '{departure_date}' không đúng định dạng YYYY-MM-DD. Hãy hỏi lại ngày bay."

    origin_code = resolve_airport(origin)
    if not origin_code:
        return (
            f"Không nhận ra điểm đi '{origin}'. "
            "Gọi list_supported_airports rồi hỏi người dùng chọn lại."
        )

    dest_code = resolve_airport(destination)
    if not dest_code:
        return (
            f"Không nhận ra điểm đến '{destination}'. "
            "Gọi list_supported_airports rồi hỏi người dùng chọn lại."
        )

    return (
        f"Hợp lệ: {origin_code} → {dest_code}, ngày {departure_date}, "
        f"{passengers or 1} hành khách, hạng {cabin_class or 'ECONOMY'}. Sẵn sàng tìm kiếm."
    )


@tool
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    passengers: int = 1,
    cabin_class: str = "ECONOMY",
    max_budget_usd: Optional[float] = None,
    return_date: Optional[str] = None,
    max_stops: Optional[int] = None,
    preferred_airline: Optional[str] = None,
    earliest_departure: Optional[str] = None,
    latest_departure: Optional[str] = None,
) -> str:
    """Search for available flights matching the user's criteria.

    Args:
        origin: Departure city name or IATA code (e.g. "Hà Nội", "HAN", "Hanoi").
        destination: Arrival city name or IATA code (e.g. "Đà Nẵng", "DAD").
        departure_date: Departure date in YYYY-MM-DD format.
        passengers: Number of passengers (default 1).
        cabin_class: Seat class — ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST (default ECONOMY).
        max_budget_usd: Maximum total price in USD (optional).
        return_date: Return date in YYYY-MM-DD format for round trips (optional).
        max_stops: Maximum number of layovers (0 = direct only, 1 = max 1 stop, etc.).
        preferred_airline: Preferred airline name — matching results shown first (e.g. "Vietnam Airlines").
        earliest_departure: Earliest acceptable departure time in HH:MM format (e.g. "06:00").
        latest_departure: Latest acceptable departure time in HH:MM format (e.g. "20:00").

    Returns:
        Formatted list of available flights sorted by price with match explanations.
    """
    try:
        offers = flight_provider.search(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            passengers=passengers,
            cabin_class=cabin_class,
            max_price_usd=max_budget_usd,
            return_date=return_date,
        )
    except Exception as exc:
        return f"Lỗi khi tìm kiếm chuyến bay: {exc}"

    # Apply advanced filters
    if max_stops is not None:
        offers = [o for o in offers if o.stops <= max_stops]

    if earliest_departure:
        offers = [o for o in offers if o.departure_time[:5] >= earliest_departure]

    if latest_departure:
        offers = [o for o in offers if o.departure_time[:5] <= latest_departure]

    if preferred_airline:
        airline_lower = preferred_airline.lower()
        preferred = [o for o in offers if airline_lower in o.airline.lower()]
        others = [o for o in offers if airline_lower not in o.airline.lower()]
        offers = preferred + others

    if not offers:
        return (
            f"Không tìm thấy chuyến bay từ {origin} đến {destination} ngày {departure_date} "
            f"trong hạng {cabin_class}"
            + (f" với ngân sách ≤ ${max_budget_usd}" if max_budget_usd else "")
            + "."
        )

    origin_label = AIRPORT_NAMES.get(resolve_airport(origin) or "", origin)
    dest_label = AIRPORT_NAMES.get(resolve_airport(destination) or "", destination)

    top = offers[:5]
    cheapest_id = min(top, key=lambda o: o.price_usd).flight_id
    fastest_id = min(top, key=lambda o: o.duration_minutes).flight_id
    direct_ids = {o.flight_id for o in top if o.stops == 0}

    lines = [
        f"Tìm thấy {len(offers)} chuyến bay từ {origin_label} → {dest_label} "
        f"ngày {departure_date} (hạng {cabin_class}, {passengers} HK):\n"
    ]
    for i, f in enumerate(top, 1):
        if f.stops == 0:
            stops_label = "Bay thẳng"
        elif f.stop_cities:
            stops_label = f"{f.stops} điểm dừng ({', '.join(f.stop_cities)})"
        else:
            stops_label = f"{f.stops} điểm dừng"
        baggage_label = (
            f"{f.baggage_allowance_kg}kg"
            if f.baggage_allowance_kg is not None
            else "Không có dữ liệu hành lý"
        )
        meal_label = (
            "Có suất ăn"
            if f.meal_included is True
            else "Không có suất ăn"
            if f.meal_included is False
            else "Không có dữ liệu suất ăn"
        )
        seats_label = (
            f"Còn {f.seats_available} ghế"
            if f.seats_available is not None
            else "Không có dữ liệu số ghế"
        )

        tags = []
        if f.flight_id == cheapest_id:
            tags.append("Rẻ nhất")
        if f.flight_id == fastest_id:
            tags.append("Nhanh nhất")
        if f.flight_id in direct_ids:
            tags.append("Bay thẳng")
        if preferred_airline and preferred_airline.lower() in f.airline.lower():
            tags.append("Hãng ưa thích")
        tag_str = f" [{', '.join(tags)}]" if tags else ""

        booking_line = f"   🔗 Đặt vé: {f.booking_url}" if f.booking_url else ""
        lines.append(
            f"{i}. [{f.flight_id}] {f.airline} {f.flight_number}{tag_str}\n"
            f"   ✈ {f.departure_time} → {f.arrival_time} ({f.duration_minutes//60}h{f.duration_minutes%60:02d}m, {stops_label})\n"
            f"   💺 {f.cabin_class} | 🧳 {baggage_label} | {meal_label}\n"
            f"   💰 ${f.price_usd:,.2f} (~{f.price_vnd:,}đ) | {seats_label}\n"
            + (booking_line + "\n" if booking_line else "")
        )

    return "\n".join(lines)


@tool
def get_flight_details(flight_id: str) -> str:
    """Get additional details for a specific flight offer.

    Args:
        flight_id: The flight_id returned by search_flights.

    Returns:
        Detailed itinerary information available from SerpAPI/Google Flights.
    """
    details = flight_provider.get_details(flight_id)
    if not details:
        return f"Không tìm thấy thông tin chi tiết cho chuyến bay {flight_id}."
    lines = [f"Chi tiết chuyến bay {flight_id}:"]
    for k, v in details.items():
        if k != "flight_id":
            if isinstance(v, list):
                v = "; ".join(str(item) for item in v)
            lines.append(f"  • {k}: {v}")
    return "\n".join(lines)


@tool
def list_supported_airports() -> str:
    """List all supported airport codes and city names.

    Returns:
        A formatted list of IATA codes and city names.
    """
    lines = ["Các sân bay được hỗ trợ:\n"]
    for code, city in AIRPORT_NAMES.items():
        lines.append(f"  {code} — {city}")
    return "\n".join(lines)


@tool
def list_supported_airlines() -> str:
    """List all airlines supported by the flight search system with their IATA codes.

    Returns:
        A formatted list of airline names and their two-letter IATA codes.
    """
    lines = ["Các hãng bay được hỗ trợ:\n"]
    for airline_name, code in MOCK_AIRLINES:
        lines.append(f"  {code} — {airline_name}")
    return "\n".join(lines)


@tool
def remember_preference(fact: str) -> str:
    """Store a user preference or important fact in long-term memory.

    Use this when the user mentions preferences like favorite airline, seat class,
    meal preference, baggage needs, or loyalty program membership.

    Args:
        fact: The preference or fact to remember (e.g. "Thích bay Vietnam Airlines hạng Business").
    """
    if not memory_client:
        return "Memory chưa được cấu hình (MEMORY_ID chưa được set)."
    memory_client.insert_memory_records_directly(
        id=MEMORY_ID,
        namespace=_namespace(),
        request=[fact],
    )
    return f"Đã ghi nhớ: {fact}"


@tool
def recall_preferences(query: str) -> str:
    """Search long-term memory for user preferences relevant to the current query.

    Always call this at the start of a flight search to personalize results.

    Args:
        query: What to search for, e.g. "hãng bay ưa thích" or "preferred airline".
    """
    if not memory_client:
        return "Chưa có sở thích nào được lưu (MEMORY_ID chưa được set)."
    results = memory_client.search_memory_records(
        id=MEMORY_ID,
        namespace=_namespace(),
        request=MemoryRecordSearchRequest(query=query, limit=10),
    )
    if not results:
        return "Chưa có sở thích nào được lưu."
    return "Sở thích đã lưu:\n" + "\n".join(
        f"  - {r.memory} (score: {r.score:.2f})" for r in results
    )


@tool
def track_flight(
    origin: str,
    destination: str,
    departure_date: str,
    current_price_usd: float,
    passengers: int = 1,
    cabin_class: str = "ECONOMY",
    flight_number: str = "",
    airline: str = "",
    chat_id: str = "",
) -> str:
    """Start tracking the price of a flight route and notify the user on changes.

    Call this when the user asks to watch/monitor a flight for price changes.
    The user will receive a Zalo notification whenever the price changes significantly.

    Args:
        origin: Departure airport IATA code (e.g. "HAN").
        destination: Arrival airport IATA code (e.g. "SGN").
        departure_date: Date in YYYY-MM-DD format.
        current_price_usd: Current cheapest price in USD (use price from search_flights).
        passengers: Number of passengers (default 1).
        cabin_class: ECONOMY/PREMIUM_ECONOMY/BUSINESS/FIRST (default ECONOMY).
        flight_number: Specific flight number to track (optional, used for display).
        airline: Airline name (optional, used for display).
        chat_id: Zalo chat_id for notifications. Leave empty to auto-detect from session.
    """
    user_id = _get_actor_id()
    # Derive chat_id from session when not explicitly passed
    if not chat_id:
        config = get_config()
        thread_id = config["configurable"].get("thread_id", "")
        # Zalo sessions are formatted as "zalo:<chat_id>"
        if thread_id.startswith("zalo:"):
            chat_id = thread_id[len("zalo:"):]
        else:
            chat_id = user_id

    entry = flight_tracker.add(
        user_id=user_id,
        chat_id=chat_id,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        passengers=passengers,
        cabin_class=cabin_class,
        last_price_usd=current_price_usd,
        flight_number=flight_number,
        airline=airline,
    )
    return (
        f"✅ Đã bắt đầu theo dõi:\n"
        f"  ✈ {origin} → {destination} | {departure_date} | {cabin_class}\n"
        f"  💰 Giá hiện tại: ${current_price_usd:,.2f}\n"
        f"  🔔 Bạn sẽ nhận thông báo qua Zalo khi giá thay đổi hơn $5.\n"
        f"  _(Mã theo dõi: {entry.tracking_id} — dùng mã này để huỷ theo dõi)_"
    )


@tool
def untrack_flight(tracking_id: str) -> str:
    """Stop tracking a flight by its tracking ID.

    Args:
        tracking_id: The tracking ID returned by track_flight (e.g. "a1b2c3d4").
    """
    removed = flight_tracker.remove(tracking_id)
    if removed:
        return f"✅ Đã huỷ theo dõi chuyến bay (mã: {tracking_id})."
    return f"Không tìm thấy chuyến bay với mã theo dõi '{tracking_id}'."


@tool
def list_tracked_flights() -> str:
    """List all flights currently being tracked for the current user.

    Returns a formatted list with tracking IDs, routes, dates, and last known prices.
    """
    user_id = _get_actor_id()
    entries = flight_tracker.list_for_user(user_id)
    if not entries:
        return "Bạn chưa theo dõi chuyến bay nào. Hãy dùng track_flight để bắt đầu."

    lines = [f"Danh sách chuyến bay đang theo dõi ({len(entries)} chuyến):\n"]
    for e in entries:
        last_checked = e.last_checked_at or "Chưa kiểm tra"
        flight_label = f"{e.airline} {e.flight_number}".strip() or "Bất kỳ hãng nào"
        lines.append(
            f"• [{e.tracking_id}] {flight_label}\n"
            f"  ✈ {e.origin} → {e.destination} | {e.departure_date} | {e.cabin_class}\n"
            f"  💰 Giá cuối: ${e.last_price_usd:,.2f} (~{int(e.last_price_usd*25000):,}đ)\n"
            f"  🕐 Kiểm tra lần cuối: {last_checked}\n"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LangGraph Definition
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    validate_flight_request,
    search_flights,
    get_flight_details,
    list_supported_airports,
    list_supported_airlines,
    remember_preference,
    recall_preferences,
    track_flight,
    untrack_flight,
    list_tracked_flights,
]

llm_with_tools = llm.bind_tools(ALL_TOOLS)


class State(TypedDict):
    messages: Annotated[list, add_messages]


def chatbot(state: State) -> dict:
    system = SystemMessage(content=SYSTEM_PROMPT.format(today=date.today().isoformat()))
    messages = [system] + state["messages"]
    return {"messages": [llm_with_tools.invoke(messages)]}


graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", ToolNode(ALL_TOOLS))
graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")

graph = graph_builder.compile(checkpointer=checkpointer)

# ---------------------------------------------------------------------------
# AgentBase Handler
# ---------------------------------------------------------------------------


def invoke_flight_agent(message: str, user_id: str, session_id: str) -> str:
    """Run one conversational turn and return the assistant's text response."""
    if MEMORY_ID and (not user_id or not session_id):
        raise ValueError("Memory mode requires both user_id and session_id.")

    config = {
        "configurable": {
            "thread_id": session_id or "default-session",
            "actor_id": user_id or "anonymous",
        }
    }
    result = graph.invoke({"messages": [("user", message)]}, config)
    ai_message = result["messages"][-1]
    content = ai_message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_blocks = []
        for block in content:
            if isinstance(block, str):
                text_blocks.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                text_blocks.append(block["text"])
        if text_blocks:
            return "\n".join(text_blocks)
    return str(content)


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Flight Finder agent entrypoint.

    Request body:
        {"message": "Tìm vé từ Hà Nội đi Đà Nẵng ngày 20/7 cho 2 người"}

    Headers (required when MEMORY_ID is set):
        X-GreenNode-AgentBase-User-Id: <user_id>
        X-GreenNode-AgentBase-Session-Id: <session_id>
    """
    if MEMORY_ID and (not context.user_id or not context.session_id):
        return {
            "status": "error",
            "error": (
                "Memory mode requires X-GreenNode-AgentBase-User-Id "
                "and X-GreenNode-AgentBase-Session-Id headers."
            ),
        }

    message = payload.get("message", "")
    if not message:
        return {"status": "error", "error": "Missing 'message' field in request body."}

    try:
        return {
            "status": "success",
            "response": invoke_flight_agent(
                message,
                context.user_id or "anonymous",
                context.session_id or "default-session",
            ),
            "session_id": context.session_id,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


zalo_bot_client = (
    ZaloBotClient(
        ZALO_BOT_TOKEN,
        parse_mode=ZALO_PARSE_MODE,
        timeout_seconds=ZALO_REQUEST_TIMEOUT_SECONDS,
    )
    if ZALO_BOT_TOKEN
    else None
)
zalo_webhook_handler = ZaloWebhookHandler(
    secret_token=ZALO_WEBHOOK_SECRET_TOKEN,
    agent_runner=invoke_flight_agent,
    bot_client=zalo_bot_client,
)
app.add_route("/webhooks/zalo", zalo_webhook_handler.handle, methods=["POST"])


# ---------------------------------------------------------------------------
# Price-alert check endpoint (call via scheduler / cron)
# ---------------------------------------------------------------------------

PRICE_ALERT_SECRET = os.environ.get("PRICE_ALERT_SECRET", "")


async def _check_price_alerts_handler(request):
    """POST /check-price-alerts — trigger a price check for all tracked flights.

    Protected by PRICE_ALERT_SECRET header (X-Alert-Secret) when the env var is set.
    Intended to be called by an external scheduler (e.g. every 30 min).
    """
    from starlette.responses import JSONResponse as _JSONResponse

    if PRICE_ALERT_SECRET:
        received = request.headers.get("X-Alert-Secret", "")
        if not hmac.compare_digest(received, PRICE_ALERT_SECRET):
            return _JSONResponse({"ok": False, "error": "Unauthorized."}, status_code=403)

    changes = await flight_tracker.check_all_and_notify(
        flight_provider=flight_provider,
        bot_client=zalo_bot_client,
    )
    return _JSONResponse(
        {
            "ok": True,
            "checked": len(flight_tracker.all()),
            "changes": len(changes),
            "details": changes,
            "timestamp": datetime.now().isoformat(),
        }
    )


app.add_route("/check-price-alerts", _check_price_alerts_handler, methods=["POST"])


# ---------------------------------------------------------------------------
# Web Chat UI
# ---------------------------------------------------------------------------

import pathlib as _pathlib
from starlette.responses import FileResponse as _FileResponse
from starlette.staticfiles import StaticFiles as _StaticFiles

_STATIC_DIR = _pathlib.Path(__file__).parent / "static"


async def _chat_ui_handler(request):
    return _FileResponse(_STATIC_DIR / "chat.html")


app.add_route("/chat", _chat_ui_handler, methods=["GET"])
app.mount("/static", _StaticFiles(directory=str(_STATIC_DIR)), name="static")


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
