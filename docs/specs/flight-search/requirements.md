# Feature: Flight Search Agent — Requirements

## Scope

### In Scope
- Tìm kiếm chuyến bay một chiều và khứ hồi.
- Lọc theo: điểm đi, điểm đến, ngày bay, số hành khách, hạng ghế (Economy/Business/First), ngân sách.
- Gợi ý top 3–5 chuyến bay với điểm phù hợp và giải thích.
- Nhớ sở thích người dùng qua long-term memory.
- Hỗ trợ tiếng Việt và tiếng Anh.
- Mock provider cho dev/test (không cần API key thật).
- SerpAPI Google Flights provider cho dữ liệu thật.

### Out of Scope
- Đặt vé (booking) — chỉ tìm kiếm và gợi ý.
- Thanh toán.
- Quản lý hành trình đã đặt.
- Nhiều chặng (multi-city) — để Next.
- Push notification giá giảm — để Later.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| LangGraph + Memory | Stateful conversation, tool-calling, memory persistence |
| Mock + SerpAPI provider | Dev/test không cần API key; prod lấy dữ liệu Google Flights qua SerpAPI |
| Trả lời ngôn ngữ theo user | UX tốt hơn cho người dùng Việt Nam |
| Top 3–5 gợi ý, không liệt kê hết | Tránh overwhelm, tập trung vào quality |

## Assumptions

- SerpAPI account có API key và đủ search credit cho môi trường chạy thật.
- `FLIGHT_API_PROVIDER=serpapi` là cấu hình mặc định; dùng `mock` cho dev/test offline.
- `thread_id` = session_id, `actor_id` = user_id (từ AgentBase context).

## Open Questions

- Giá và tiện ích hiển thị phụ thuộc dữ liệu Google Flights mà SerpAPI trả về.
