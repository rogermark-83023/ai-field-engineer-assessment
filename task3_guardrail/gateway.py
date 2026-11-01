import json
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from redactor import StreamRedactor


PROVIDER_URL = os.getenv(
    "LLM_PROVIDER_URL", "http://127.0.0.1:8002/v1/chat/completions"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None)) as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan)


MAX_EVENT_BYTES = 64 * 1024


class UpstreamEventTooLarge(Exception):
    pass


async def read_events(response):
    buffer = bytearray()
    data = []
    size = 0

    async for chunk in response.aiter_bytes():
        for start in range(0, len(chunk), 4096):
            buffer.extend(chunk[start:start + 4096])

            while True:
                pos = buffer.find(b"\n")
                if pos < 0:
                    break

                line = bytes(buffer[:pos]).rstrip(b"\r")
                del buffer[:pos + 1]
                size += pos + 1

                if size > MAX_EVENT_BYTES:
                    raise UpstreamEventTooLarge()

                if not line:
                    if data:
                        yield b"\n".join(data).decode("utf-8")
                    data = []
                    size = 0
                elif line.startswith(b"data:"):
                    value = line[5:]
                    if value.startswith(b" "):
                        value = value[1:]
                    data.append(value)

            if size + len(buffer) > MAX_EVENT_BYTES:
                raise UpstreamEventTooLarge()

    if buffer:
        line = bytes(buffer).rstrip(b"\r")
        if line.startswith(b"data:"):
            value = line[5:]
            if value.startswith(b" "):
                value = value[1:]
            data.append(value)

    if data:
        yield b"\n".join(data).decode("utf-8")


def event(data):
    return f"data: {json.dumps(data)}\n\n"



async def filter_stream(response):
    redactors = {}

    try:
        async for data in read_events(response):
            if data == "[DONE]":
                break

            try:
                packet = json.loads(data)
            except ValueError:
                continue

            if not isinstance(packet, dict):
                continue

            choices = packet.get("choices")

            if not isinstance(choices, list):
                continue

            selected = []

            for choice in choices:
                if not isinstance(choice, dict):
                    continue

                delta = choice.get("delta")

                if not isinstance(delta, dict):
                    continue

                index = choice.get("index", 0)

                if type(index) is not int or index < 0:
                    continue

                redactor = redactors.setdefault(index, StreamRedactor())
                content = delta.get("content")

                clean = redactor.feed(content) if isinstance(content, str) else ""

                finish_reason = choice.get("finish_reason")

                if finish_reason is not None:
                    clean += redactor.finish()

                safe_delta = {}

                if delta.get("role") == "assistant":
                    safe_delta["role"] = "assistant"

                if clean:
                    safe_delta["content"] = clean

                if safe_delta or finish_reason is not None:
                    selected.append({
                        "index": index,
                        "delta": safe_delta,
                        "finish_reason": (
                            finish_reason
                            if finish_reason in (
                                "stop",
                                "length",
                                "content_filter",
                                "tool_calls"
                            )
                            else None
                        )
                    })

            if selected:
                yield event({
                    "id": "filtered-completion",
                    "object": "chat.completion.chunk",
                    "choices": selected
                })

        for index, redactor in redactors.items():
            remaining = redactor.finish()

            if remaining:
                yield event({
                    "id": "filtered-completion",
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": index,
                        "delta": {"content": remaining},
                        "finish_reason": None
                    }]
                })

        yield "data: [DONE]\n\n"

    except (UpstreamEventTooLarge, UnicodeDecodeError):
        yield 'event: error\ndata: {"error":"Invalid upstream stream"}\n\n'

    finally:
        await response.aclose()


@app.post("/v1/chat/completions")
async def chat_completion(request: Request):
    body = await request.body()
    client = request.app.state.client

    try:
        upstream_request = client.build_request(
            "POST",
            PROVIDER_URL,
            content=body,
            headers={"Content-Type": "application/json"}
        )

        upstream = await client.send(upstream_request, stream=True)

    except httpx.HTTPError:
        return JSONResponse(
            status_code=502,
            content={"error": "Provider unavailable"}
        )

    if upstream.status_code != 200:
        await upstream.aclose()
        return JSONResponse(
            status_code=502,
            content={"error": "Provider returned an error"}
        )

    return StreamingResponse(
        filter_stream(upstream),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
