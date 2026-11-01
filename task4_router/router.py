import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
import tiktoken
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rate_limiter import RateLimiter

PRIMARY_URL = "http://127.0.0.1:8004/primary"
BACKUP_URL = "http://127.0.0.1:8004/backup"

API_KEYS = {
    "tenant-a-key": "tenant-a",
    "tenant-b-key": "tenant-b"
}

encoding = tiktoken.encoding_for_model("gpt-4o-mini")
limiter = RateLimiter(Path(__file__).with_name("usage.db"))


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "mock-primary"
    messages: list[Message] = Field(min_length=1)
    max_tokens: int = Field(default=128, gt=0, le=4096, strict=True)
    simulate: Literal[
        "normal",
        "rate_limit",
        "timeout",
        "primary_error",
        "backup_failure"
    ] = "normal"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await limiter.setup()

    async with httpx.AsyncClient() as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan)


def gateway_error(status, code, message):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message
            }
        }
    )


def count_tokens(messages, max_tokens):
    prompt_tokens = 3

    for message in messages:
        prompt_tokens += 4
        prompt_tokens += len(encoding.encode(message.role))
        prompt_tokens += len(encoding.encode(message.content))

    return prompt_tokens + max_tokens


async def call_provider(client, url, payload, timeout):
    async with asyncio.timeout(timeout):
        return await client.post(url, json=payload)


@app.post("/v1/chat/completions")
async def route_completion(request: Request):
    authorization = request.headers.get("authorization", "")
    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return gateway_error(401, "UNAUTHORIZED", "Invalid API key")

    tenant = API_KEYS.get(parts[1])

    if tenant is None:
        return gateway_error(401, "UNAUTHORIZED", "Invalid API key")

    try:
        data = await request.json()
    except ValueError:
        return gateway_error(400, "INVALID_REQUEST", "Invalid JSON")

    try:
        payload = CompletionRequest.model_validate(data)
    except ValidationError:
        return gateway_error(
            400,
            "INVALID_REQUEST",
            "Invalid completion request"
        )

    tokens = count_tokens(payload.messages, payload.max_tokens)
    reservation_id = await limiter.reserve(tenant, tokens)

    if reservation_id is None:
        return gateway_error(
            429,
            "RATE_LIMIT_EXCEEDED",
            "Token limit exceeded"
        )

    
    completed = False

    try:
        body = payload.model_dump()
        client = request.app.state.client

        try:
            response = await call_provider(
                client,
                PRIMARY_URL,
                body,
                3.0
            )
        except (TimeoutError, httpx.TimeoutException):
            response = None
        except httpx.RequestError:
            return gateway_error(
                502,
                "UPSTREAM_ERROR",
                "Model provider unavailable"
            )

        if response is None or response.status_code == 429:
            try:
                response = await call_provider(
                    client,
                    BACKUP_URL,
                    body,
                    5.0
                )
            except (TimeoutError, httpx.RequestError):
                return gateway_error(
                    502,
                    "UPSTREAM_ERROR",
                    "Both model providers failed"
                )

        if response.status_code != 200:
            return gateway_error(
                502,
                "UPSTREAM_ERROR",
                "Model provider unavailable"
            )

        try:
            result = response.json()
        except ValueError:
            return gateway_error(
                502,
                "INVALID_UPSTREAM_RESPONSE",
                "Invalid model response"
            )

        if not isinstance(result, dict):
            return gateway_error(
                502,
                "INVALID_UPSTREAM_RESPONSE",
                "Invalid model response"
            )

        usage = result.get("usage", {})
        actual_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None

        
        if type(actual_tokens) is int and actual_tokens > 0:
            within_limit = await limiter.reconcile(
                reservation_id, actual_tokens
            )

            completed = True

            if not within_limit:
                return gateway_error(
                    502,
                    "UPSTREAM_USAGE_EXCEEDED",
                    "Provider exceeded the token budget"
                )
        else:
            completed = True

        return result

    finally:
        if not completed:
            await limiter.release(reservation_id)

