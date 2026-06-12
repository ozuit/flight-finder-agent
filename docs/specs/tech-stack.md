# Tech Stack

## Runtime

- **Platform**: GreenNode AgentBase
- **Language**: Python 3.13
- **HTTP Server**: `greennode-agentbase` (`GreenNodeAgentBaseApp`)
- **Port**: 8080

## AI Framework

- **Graph Engine**: LangGraph (stateful, tool-calling)
- **LLM Bridge**: `langchain-openai` (OpenAI-compatible API)
- **LLM Provider**: GreenNode AI Platform (hoặc OpenAI)
- **Memory**: `greennode-agent-bridge` + `AgentBaseMemoryEvents`
  - Short-term: checkpointer (conversation history per session)
  - Long-term: `MemoryClient` SDK (`remember`/`recall` tools)

## Flight Data

- **Primary**: SerpAPI Google Flights API
- **Fallback**: Mock data tĩnh cho dev/test (không cần API key)
- Cấu hình qua env var `FLIGHT_API_PROVIDER=serpapi|mock`

## Dependencies

```
greennode-agentbase
greennode-agent-bridge[langgraph]
langgraph>=1.0.0,<2.0.0
langchain>=1.2.0,<2.0.0
langchain-openai>=1.1.0,<2.0.0
python-dotenv
httpx
```

## Conventions

- `main.py`: entrypoint duy nhất, chứa graph definition và handler.
- `tools/`: các tool function tìm kiếm vé, tách file theo nhóm chức năng.
- `docs/specs/`: tài liệu spec, không được xóa.
- Biến môi trường: tất cả config qua `.env` / env vars, không hardcode.

## Hard Constraints

- Không lưu thông tin thanh toán của người dùng.
- Health endpoint `GET /health` luôn phải trả về HTTP 200.
- Agent phải trả lời bằng ngôn ngữ người dùng dùng (vi/en tự động detect).
