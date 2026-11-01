from fastapi import FastAPI, Request

app = FastAPI()
calls = []

TOOLS = [
    {
        "name": "get_customer_record",
        "description": "Look up a customer",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"}
            },
            "required": ["customer_id"]
        }
    },
    {
        "name": "admin_reset_key",
        "description": "Reset an API key",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


@app.post("/mcp")
async def handle_mcp(request: Request):
    data = await request.json()
    method = data.get("method")
    request_id = data.get("id")

    if method == "tools/list":
        result = {"tools": TOOLS}

    elif method == "tools/call":
        params = data.get("params") or {}
        name = params.get("name")

        if name not in {tool["name"] for tool in TOOLS}:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": "Unknown tool"
                }
            }

        calls.append(name)

        result = {
            "content": [
                {
                    "type": "text",
                    "text": f"{name} executed"
                }
            ],
            "isError": False
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }


@app.get("/stats")
async def stats():
    return {"calls": len(calls)}
