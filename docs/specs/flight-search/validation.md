# Feature: Flight Search Agent — Validation

## Acceptance Criteria

- [ ] Agent trả lời khi nhận yêu cầu tìm vé bằng tiếng Việt
      verify: `curl -X POST .../invocations -d '{"message": "Tìm vé từ Hà Nội đi Đà Nẵng ngày 20/7"}'`
      → response chứa danh sách chuyến bay với giá và giờ bay.

- [ ] Agent hỏi thêm thông tin khi thiếu điểm đến
      verify: `curl ... -d '{"message": "Tìm vé đi Đà Lạt"}'` (thiếu ngày)
      → response hỏi ngày bay.

- [ ] Agent nhớ sở thích người dùng qua phiên mới
      verify:
        1. Session 1: "Tôi thích bay Vietnam Airlines hạng Business"
        2. Session 2: tìm vé → response ưu tiên Vietnam Airlines Business.

- [ ] Mock provider hoạt động không cần API key
      verify: `FLIGHT_API_PROVIDER=mock python3 main.py` khởi động thành công.
      `curl .../invocations -d '{"message": "Tìm vé HAN-SGN ngày mai"}'` → kết quả mock.

- [ ] Health endpoint luôn trả 200
      verify: `curl -s -o /dev/null -w "%{http_code}" .../health` → `200`.

- [ ] Agent trả lời bằng tiếng Anh khi user dùng tiếng Anh
      verify: `curl ... -d '{"message": "Find flights from Hanoi to Ho Chi Minh City tomorrow"}'`
      → response bằng tiếng Anh.
