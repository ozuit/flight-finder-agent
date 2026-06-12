# flight-finder-agent

Trợ lý AI tìm vé máy bay thông minh, xây dựng trên **GreenNode AgentBase** với **LangGraph + Memory**.

Agent hiểu yêu cầu bằng tiếng Việt và tiếng Anh, tìm kiếm và gợi ý các chuyến bay phù hợp nhất, đồng thời ghi nhớ sở thích cá nhân qua nhiều phiên hội thoại.

---

## Tính năng

- **Tìm kiếm tự nhiên**: "Tìm vé từ Hà Nội đi Đà Nẵng ngày 20/7 cho 2 người, hạng Economy dưới $100"
- **Gợi ý thông minh**: Top 3–5 chuyến bay kèm giải thích tại sao phù hợp
- **Hỗ trợ khứ hồi** và một chiều
- **Nhớ sở thích**: lưu hãng bay ưa thích, hạng ghế, nhu cầu hành lý
- **Đa ngôn ngữ**: tự động phát hiện tiếng Việt / tiếng Anh
- **Dữ liệu Google Flights qua SerpAPI**: hỗ trợ chuyến bay thật, một chiều và khứ hồi
- **Mock provider**: chạy test không cần API key

---

## Prerequisites

- Python 3.10+ (**yêu cầu bắt buộc** — `greennode-agent-bridge` không hỗ trợ Python 3.9)
  - macOS với Homebrew: `brew install python@3.11`
  - Hoặc dùng pyenv: `pyenv install 3.11`
- GreenNode IAM Service Account ([tạo tại đây](https://iam.console.vngcloud.vn/service-accounts))

---

## Cài đặt

```bash
# 1. Clone hoặc cd vào thư mục dự án
cd flight-finder-agent

# 2. Tạo virtualenv với Python 3.10+
# macOS (Homebrew):
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate

# Linux / pyenv:
python3.11 -m venv venv
source venv/bin/activate

# Windows PowerShell:
# py -3.11 -m venv venv; venv\Scripts\Activate.ps1

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Cấu hình environment
cp .env.example .env
# Chỉnh sửa .env với thông tin của bạn
```

---

## Cấu hình

Chỉnh sửa file `.env`:

```env
# LLM (bắt buộc)
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1  # GreenNode AIP
LLM_MODEL=gpt-4o-mini   # hoặc model bạn chọn

# GreenNode credentials (bắt buộc cho deploy)
GREENNODE_CLIENT_ID=your-client-id
GREENNODE_CLIENT_SECRET=your-client-secret

# Memory (tuỳ chọn — để trống nếu không dùng)
MEMORY_ID=your-memory-store-id

# Flight provider (Google Flights qua SerpAPI)
FLIGHT_API_PROVIDER=serpapi
SERPAPI_API_KEY=your-serpapi-key
SERPAPI_GL=vn
SERPAPI_HL=vi
```

### Sử dụng SerpAPI Google Flights

Lấy API key tại [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key), sau đó:

```env
FLIGHT_API_PROVIDER=serpapi
SERPAPI_API_KEY=your-serpapi-key
SERPAPI_GL=vn
SERPAPI_HL=vi
SERPAPI_DEEP_SEARCH=false
```

Đặt `SERPAPI_DEEP_SEARCH=true` khi cần kết quả gần với giao diện Google Flights hơn. Chế độ này có thời gian phản hồi lâu hơn.

Để chạy hoàn toàn offline bằng dữ liệu giả:

```env
FLIGHT_API_PROVIDER=mock
```

---

## Chạy local

```bash
python3 -m venv venv && source venv/bin/activate
python3 main.py
# Agent khởi động tại http://127.0.0.1:8080
```

### Ví dụ request

**Tìm vé một chiều:**

```bash
curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-GreenNode-AgentBase-User-Id: user-001" \
  -H "X-GreenNode-AgentBase-Session-Id: session-001" \
  -d '{"message": "Tìm vé từ Hà Nội đi Đà Nẵng ngày 2026-07-20 cho 2 người"}'
```

**Tìm vé có ngân sách:**

```bash
curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-GreenNode-AgentBase-User-Id: user-001" \
  -H "X-GreenNode-AgentBase-Session-Id: session-001" \
  -d '{"message": "Find business class flights from HAN to SIN next Friday, budget $500"}'
```

**Lưu sở thích:**

```bash
curl -X POST http://127.0.0.1:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-GreenNode-AgentBase-User-Id: user-001" \
  -H "X-GreenNode-AgentBase-Session-Id: session-001" \
  -d '{"message": "Tôi thích bay Vietnam Airlines, hạng Business, cần 30kg hành lý"}'
```

**Health check:**

```bash
curl http://127.0.0.1:8080/health
```

---

## Cấu trúc dự án

```
flight-finder-agent/
├── main.py                         # Agent entrypoint (LangGraph graph + handler)
├── tools/
│   ├── __init__.py
│   └── flight_providers.py         # SerpAPI + Mock providers
├── docs/specs/                     # Spec-Driven Development specs
│   ├── mission.md                  # Project mission & goals
│   ├── tech-stack.md               # Technology decisions
│   ├── roadmap.md                  # Now / Next / Later
│   └── flight-search/
│       ├── plan.md                 # Feature task groups
│       ├── requirements.md         # Scope & decisions
│       └── validation.md           # Acceptance criteria
├── Dockerfile
├── requirements.txt
├── .env.example
├── .greennode.json
├── .gitignore
└── .dockerignore
```

---

## Deploy lên GreenNode AgentBase

```bash
# Dùng /agentbase-deploy skill trong Claude Code
/agentbase-deploy
```

Hoặc thủ công:

1. Build & push Docker image lên [GreenNode vCR](https://vcr.console.vngcloud.vn)
2. Tạo Runtime tại [AgentBase Console](https://aiplatform.console.vngcloud.vn/runtime)
3. Trỏ Endpoint vào Runtime

---

## Thêm Memory (tuỳ chọn)

Dùng skill `/agentbase-memory` để tạo memory store:

```bash
# Trong Claude Code session:
/agentbase-memory create
# Lấy MEMORY_ID và cập nhật .env
```

---

## Tools có sẵn

| Tool                      | Mô tả                                                          |
| ------------------------- | -------------------------------------------------------------- |
| `search_flights`          | Tìm chuyến bay theo origin, destination, ngày, hạng, ngân sách |
| `get_flight_details`      | Lấy chi tiết máy bay, tiện nghi, chính sách hủy vé             |
| `list_supported_airports` | Danh sách sân bay được hỗ trợ                                  |
| `remember_preference`     | Lưu sở thích người dùng vào long-term memory                   |
| `recall_preferences`      | Truy xuất sở thích đã lưu để cá nhân hóa kết quả               |

---

## Sân bay được hỗ trợ (Mock)

Trong nước: HAN, SGN, DAD, CXR, DLI, PQC, UIH, HPH

Quốc tế: BKK, SIN, NRT, ICN, HKG, CDG, LHR, LAX, JFK, DXB, SYD, KUL
