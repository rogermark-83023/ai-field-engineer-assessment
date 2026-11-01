import asyncio
import httpx

GATEWAY_URL = "http://127.0.0.1:8000/mcp"
SERVER_URL = "http://127.0.0.1:8001/mcp"
STATS_URL = "http://127.0.0.1:8001/stats"

async def main():
    async with httpx.AsyncClient(timeout=10.0) as client:

        async def send(payload, token="viewer-token", url=GATEWAY_URL):
            return await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"}
            )

        async def get_call_count():
            response = await client.get(STATS_URL)
            response.raise_for_status()
            return response.json()["calls"]

        list_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }

        response = await client.post(
            GATEWAY_URL,
            json=list_request
        )

        assert response.status_code == 401
        print("Missing token rejected")

        response = await send(list_request, "invalid-token")

        assert response.status_code == 401
        print("Invalid token rejected")

        gateway_response = await send(list_request)
        server_response = await client.post(
            SERVER_URL,
            json=list_request
        )

        assert gateway_response.status_code == server_response.status_code
        assert gateway_response.json() == server_response.json()
        print("Tool listing forwarded correctly")

        admin_request = {
            "jsonrpc": "2.0",
            "id": "viewer-request",
            "method": "tools/call",
            "params": {
                "name": "admin_reset_key",
                "arguments": {}
            }
        }

        before = await get_call_count()

        response = await send(admin_request)
        data = response.json()

        assert data["id"] == "viewer-request"
        assert data["error"]["code"] == -32001
        assert data["error"]["message"] == "Unauthorized Tool Call"
        assert await get_call_count() == before
        print("Viewer blocked from admin tool")
        print("Blocked request did not reach the server")

        normal_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_customer_record",
                "arguments": {
                    "customer_id": "CUST-12345"
                }
            }
        }

        response = await send(normal_request)
        data = response.json()

        assert response.status_code == 200
        assert data["id"] == 3
        assert data["result"]["isError"] is False
        assert await get_call_count() == before + 1
        print("Viewer allowed to use normal tool")

        response = await send(admin_request, "admin-token")
        data = response.json()

        assert response.status_code == 200
        assert data["result"]["isError"] is False
        assert await get_call_count() == before + 2
        print("Admin allowed to use admin tool")

        invalid_request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "arguments": {}
            }
        }

        response = await send(invalid_request)
        data = response.json()

        assert data["error"]["code"] == -32602
        print("Invalid tool parameters rejected")

        response = await client.post(
            GATEWAY_URL,
            content="{invalid-json",
            headers={
                "Authorization": "Bearer viewer-token",
                "Content-Type": "application/json"
            }
        )

        assert response.json()["error"]["code"] == -32700
        print("Malformed JSON rejected")

        print("All gateway tests passed")


if __name__ == "__main__":
    asyncio.run(main())
