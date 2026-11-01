import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/v1/chat/completions")
async def chat_completion():
    async def generate():
        chunks = [
            "Hello! ",
            "You can contact me at ",
            "john@",
            "example.com",
            " for more information. ",
            "My SSN is ",
            "123-",
            "45-",
            "6789",
            ". My card number is ",
            "4111 1111 ",
            "1111 1111",
            ". Thank you!"
        ]

        for text in chunks:
            payload = {
                "id": "mock-completion",
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": text},
                        "finish_reason": None
                    }
                ]
            }

            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.1)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )
