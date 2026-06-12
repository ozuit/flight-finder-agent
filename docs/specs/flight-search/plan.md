# Feature: Flight Search Agent — Plan

## Task Groups

### Group 1: Core Agent Graph
1. Định nghĩa LangGraph `State` với message history.
2. Xây dựng `chatbot` node với tool-calling LLM.
3. Compile graph với `AgentBaseMemoryEvents` checkpointer.
4. Wire `handler` và `health_check` vào `GreenNodeAgentBaseApp`.

### Group 2: Flight Search Tools
1. `search_flights(origin, destination, departure_date, return_date, passengers, cabin_class, budget)` — tìm các chuyến bay phù hợp.
2. `get_flight_details(flight_id)` — lấy chi tiết một chuyến bay.
3. `list_airlines()` — danh sách hãng bay hỗ trợ.
4. Provider pattern: `MockFlightProvider` (dev/test) và `SerpApiFlightProvider` (prod).

### Group 3: Memory & Personalization
1. `remember(fact)` — lưu sở thích người dùng (hạng ghế, hãng bay ưa thích, hành lý).
2. `recall(query)` — truy xuất sở thích cho tìm kiếm cá nhân hóa.
3. Agent tự động gọi `recall` khi bắt đầu tìm kiếm để load sở thích.

### Group 4: System Prompt & Response Format
1. System prompt hướng dẫn agent: hỏi thông tin còn thiếu, so sánh chuyến bay, giải thích gợi ý.
2. Response format chuẩn: danh sách chuyến bay với các trường key (hãng, giờ, thời gian bay, giá, điểm dừng).
