
# AI Gateway and MCP Assessment

Four Python implementations covering MCP tools, access control, streaming PII redaction, and resilient LLM routing.

## Requirements

- Python 3.11+
- pip

## Installation

Create a virtual environment:

```powershell
py -m venv .venv
```

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Task 1 - MCP Server

A stdio MCP server with two tools:

- `get_customer_record`
- `trigger_refund`

Uses Pydantic for input validation and the official MCP Python SDK.

Run tests:

```powershell
.\.venv\Scripts\python.exe test_server.py
.\.venv\Scripts\python.exe test_protocol.py
```

## Task 2 - MCP Security Gateway

An HTTP JSON-RPC gateway with role-based authorization.

Viewer requests to tools starting with `admin_` are rejected. Authorized requests are forwarded to the mock MCP server.

Start the mock server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn mock_server:app --app-dir task2_gateway --host 127.0.0.1 --port 8001
```

Start the gateway in another terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn gateway:app --app-dir task2_gateway --host 127.0.0.1 --port 8000
```

Run tests:

```powershell
.\.venv\Scripts\python.exe task2_gateway\test_gateway.py
.\.venv\Scripts\python.exe task2_gateway\test_transport.py
```

Test credentials:

- Admin: `admin-token`
- Viewer: `viewer-token`

## Task 3 - Streaming PII Guardrail

An LLM streaming proxy that detects and redacts email addresses, SSNs, and credit-card patterns across response chunks.

Start the mock provider:

```powershell
.\.venv\Scripts\python.exe -m uvicorn mock_provider:app --app-dir task3_guardrail --host 127.0.0.1 --port 8002
```

Start the gateway:

```powershell
.\.venv\Scripts\python.exe -m uvicorn gateway:app --app-dir task3_guardrail --host 127.0.0.1 --port 8003
```

Run tests:

```powershell
.\.venv\Scripts\python.exe task3_guardrail\test_guardrail.py
```

## Task 4 - Rate Limiting and Model Fallback

An LLM router with:

- SQLite-backed sliding-window rate limiting
- 50,000 tokens per minute per tenant
- Automatic fallback on HTTP 429
- Three-second primary timeout
- Standardized gateway error responses

Start the mock model providers:

```powershell
.\.venv\Scripts\python.exe -m uvicorn mock_models:app --app-dir task4_router --host 127.0.0.1 --port 8004
```

Start the router:

```powershell
.\.venv\Scripts\python.exe -m uvicorn router:app --app-dir task4_router --host 127.0.0.1 --port 8005
```

Run tests:

```powershell
.\.venv\Scripts\python.exe task4_router\test_rate_limiter.py
.\.venv\Scripts\python.exe task4_router\test_router.py
.\.venv\Scripts\python.exe task4_router\test_quota.py
```

Test API keys:

- `tenant-a-key`
- `tenant-b-key`

## Notes

All customer records, credentials, and model providers are local test data. No real refunds or external AI requests are performed.

The test credentials are not intended for production authentication.


## Implementation Notes

The project uses mock MCP tools, local test credentials, and simulated LLM providers.

The MCP gateway uses fixed tokens for demonstration. Production authentication would require verified credentials.

The streaming guardrail uses pattern matching to redact common PII formats. It does not cover every possible sensitive-data format. It rejects SSE events larger than 64 KB.

The model router reserves estimated token usage and updates it when a provider reports actual usage. Token counts may vary between model providers.

The SQLite rate limiter is designed for a local deployment. A distributed deployment would need additional coordination and testing.
