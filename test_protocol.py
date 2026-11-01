import asyncio
import json
import sys
from pathlib import Path

async def main():
    server = Path(__file__).with_name("server.py")

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(server),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async def send(message):
        data = json.dumps(message) + "\n"
        process.stdin.write(data.encode())
        await process.stdin.drain()

    async def request(message):
        await send(message)

        line = await asyncio.wait_for(
            process.stdout.readline(),
            timeout=10
        )

        assert line, "Server did not respond"

        response = json.loads(line)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == message["id"]
        assert ("result" in response) != ("error" in response)

        return response

    try:
        response = await request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "assessment-test",
                    "version": "1.0"
                }
            }
        })

        assert "result" in response
        print("Initialization passed")

        await send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        response = await request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })

        assert len(response["result"]["tools"]) == 2
        print("JSON-RPC tool discovery passed")

        response = await request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "arguments": {}
            }
        })

        assert response["error"]["code"] == -32602
        print("Invalid JSON-RPC parameters rejected")

        response = await request({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_customer_record",
                "arguments": {
                    "customer_id": "CUST-12345",
                    "unexpected": True
                }
            }
        })

        assert response["result"]["isError"] is True
        print("Invalid tool input rejected")

        process.stdin.close()
        await asyncio.wait_for(process.wait(), timeout=10)

        remaining = await process.stdout.read()

        for line in remaining.splitlines():
            response = json.loads(line)
            assert response["jsonrpc"] == "2.0"

        assert process.returncode == 0
        print("Stdout isolation passed")
        print("All protocol tests passed")

    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


if __name__ == "__main__":
    asyncio.run(main())
