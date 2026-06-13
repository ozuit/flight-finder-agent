# Roadmap

## Now

- [x] Scaffold dự án (LangGraph + Memory)
- [x] Implement flight search tools (mock + SerpAPI Google Flights)
- [x] Multi-turn conversation: hỏi thêm thông tin còn thiếu (`validate_flight_request` tool + slot-filling flow)
- [x] Gợi ý top 3–5 chuyến bay với giải thích (tag Rẻ nhất / Nhanh nhất / Bay thẳng / Hãng ưa thích)
- [x] Nhớ sở thích người dùng qua long-term memory (`remember_preference` + `recall_preferences`)

## Next

- [x] Filter nâng cao: số điểm dừng (`max_stops`), thời gian bay (`earliest/latest_departure`), hãng bay ưa thích (`preferred_airline`)
- [ ] Hỗ trợ tìm kiếm nhiều chặng (multi-city)
- [ ] Thông báo giá giảm cho tuyến bay yêu thích

## Done

- Scaffold LangGraph + GreenNode AgentBase
- Flight search: MockFlightProvider + SerpApiFlightProvider
- Zalo Bot webhook integration
- Long-term memory (MemoryClient) + short-term (checkpointer)
- Unit tests: flight providers, Zalo webhook handler
