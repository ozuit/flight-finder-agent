# Mission

## Problem

Người dùng mất nhiều thời gian tìm kiếm và so sánh vé máy bay phù hợp trên nhiều nền tảng khác nhau. Họ cần một trợ lý AI có thể hiểu yêu cầu tự nhiên, tìm kiếm, lọc và gợi ý các chuyến bay tốt nhất — đồng thời ghi nhớ sở thích cá nhân để cải thiện kết quả theo thời gian.

## Users

- Khách đi công tác: ưu tiên giờ bay, đúng giờ, hạng ghế business.
- Khách du lịch cá nhân/gia đình: ưu tiên giá rẻ, hành lý miễn phí.
- Khách thường xuyên bay: muốn agent nhớ sở thích (hãng bay, hạng ghế, bữa ăn).

## Why Now

LLM + agentic reasoning cho phép tìm kiếm vé máy bay theo ngôn ngữ tự nhiên, không cần form phức tạp. GreenNode AgentBase cung cấp memory & identity để cá nhân hóa kết quả.

## Success

- Agent hiểu và xử lý yêu cầu tìm vé trong ngôn ngữ tự nhiên (tiếng Việt & tiếng Anh).
- Gợi ý top 3–5 chuyến bay phù hợp nhất với giải thích rõ ràng.
- Nhớ sở thích người dùng qua nhiều phiên hội thoại.
- Hỗ trợ tìm kiếm khứ hồi, một chiều, và nhiều chặng.

## Guiding Principles

- **Đơn giản trước**: không over-engineer, không thêm tính năng ngoài yêu cầu.
- **Minh bạch**: luôn giải thích tại sao gợi ý chuyến bay đó.
- **Bảo mật**: không lưu thông tin thanh toán, chỉ lưu sở thích.
