import asyncio
import json
import httpx

from gateway import app


async def main():
    forwarded = []

    async def upstream(request):
        body = await request.aread()
        forwarded.append((request.headers, json.loads(body)))
        request_id = forwarded[-1][1]["id"]

        if request_id == 2:
            content = 'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n\n'
            return httpx.Response(
                200,
                content=content,
                headers={
                    "Content-Type": "text/event-stream",
                    "Mcp-Session-Id": "session-123"
                }
            )

        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": []}
            },
            headers={"Mcp-Session-Id": "session-123"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
        app.state.client = upstream_client

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway"
        ) as client:
            headers = {
                "Authorization": "Bearer viewer-token",
                "Accept": "application/json, text/event-stream",
                "Mcp-Protocol-Version": "2025-06-18",
                "Mcp-Session-Id": "session-123"
            }

            response = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers=headers
            )

            assert response.status_code == 200
            assert response.json()["result"] == {"tools": []}
            assert response.headers["mcp-session-id"] == "session-123"
            assert forwarded[-1][0]["mcp-protocol-version"] == "2025-06-18"
            assert forwarded[-1][0]["mcp-session-id"] == "session-123"
            print("MCP headers forwarded")

            response = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                headers=headers
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["mcp-session-id"] == "session-123"
            assert '"id":2' in response.text
            assert response.text.startswith("data: ")
            print("SSE response forwarded")

            before = len(forwarded)
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "admin_reset_key", "arguments": {}}
                },
                headers=headers
            )

            assert response.json()["error"]["code"] == -32001
            assert len(forwarded) == before
            print("Unauthorized tool blocked")

    print("All transport tests passed")


if __name__ == "__main__":
    asyncio.run(main())
