import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

async def complete(request: Request, provider: str):
    data = await request.json()
    mode = data.get("simulate", "normal")

    if provider == "primary":
        if mode in ("rate_limit", "backup_failure"):
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests"}
            )

        if mode == "timeout":
            await asyncio.sleep(3.5)

        if mode == "primary_error":
            return JSONResponse(
                status_code=503,
                content={"error": "Service unavailable"}
            )

    if provider == "backup" and mode == "backup_failure":
        return JSONResponse(
            status_code=503,
            content={"error": "Backup unavailable"}
        )

    return {
        "id": f"{provider}-completion",
        "model": f"mock-{provider}",
        "provider": provider,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Response from {provider} model"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 5,
            "total_tokens": 13
        }
    }


@app.post("/primary")
async def primary(request: Request):
    return await complete(request, "primary")


@app.post("/backup")
async def backup(request: Request):
    return await complete(request, "backup")
