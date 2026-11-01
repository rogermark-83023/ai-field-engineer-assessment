import json
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse


UPSTREAM_URL = "http://127.0.0.1:8001/mcp"

TOKENS = {
    "admin-token": "admin",
    "viewer-token": "viewer"
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=10.0) as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan)


def rpc_error(request_id, code, message):
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    })


@app.post("/mcp")
async def gateway(request: Request):
    authorization = request.headers.get("authorization", "")
    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={"error": "Unauthorized"}
        )

    role = TOKENS.get(parts[1])

    if role is None:
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={"error": "Invalid token"}
        )

    body = await request.body()

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return rpc_error(None, -32700, "Parse error")

    if not isinstance(payload, dict):
        return rpc_error(None, -32600, "Invalid Request")

    request_id = payload.get("id")
    method = payload.get("method")

    if payload.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return rpc_error(request_id, -32600, "Invalid Request")

    if method == "tools/call":
        params = payload.get("params")

        if not isinstance(params, dict):
            return rpc_error(request_id, -32602, "Invalid params")

        name = params.get("name")

        if not isinstance(name, str):
            return rpc_error(request_id, -32602, "Invalid params")

        if name.startswith("admin_") and role != "admin":
            return rpc_error(request_id, -32001, "Unauthorized Tool Call")

    headers = {
        "Content-Type": "application/json",
        "Accept": request.headers.get("accept", "application/json, text/event-stream")
    }

    if headers["Accept"] == "*/*":
        headers["Accept"] = "application/json, text/event-stream"

    for name in (
        "Mcp-Protocol-Version",
        "Mcp-Session-Id",
        "Mcp-Method",
        "Mcp-Name",
        "Last-Event-ID"
    ):
        value = request.headers.get(name)
        if value is not None:
            headers[name] = value

    client = request.app.state.client

    try:
        upstream_request = client.build_request(
            "POST", UPSTREAM_URL, content=body, headers=headers
        )
        response = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        return rpc_error(request_id, -32000, "Downstream timeout")
    except httpx.RequestError:
        return rpc_error(request_id, -32000, "Downstream unavailable")

    response_headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() in {
            "content-type",
            "mcp-session-id",
            "mcp-protocol-version",
            "cache-control",
            "retry-after"
        }
    }

    if "text/event-stream" in response.headers.get("content-type", ""):
        async def stream_body():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(
            stream_body(),
            status_code=response.status_code,
            headers=response_headers
        )

    try:
        content = await response.aread()
    except httpx.HTTPError:
        return rpc_error(request_id, -32000, "Downstream unavailable")
    finally:
        await response.aclose()

    return Response(
        content=content,
        status_code=response.status_code,
        headers=response_headers
    )
