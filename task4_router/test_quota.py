import asyncio
import httpx

URL = "http://127.0.0.1:8005/v1/chat/completions"

async def main():
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "hello " * 60000
            }
        ],
        "max_tokens": 64
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            URL,
            json=payload,
            headers={
                "Authorization": "Bearer tenant-a-key"
            }
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    print("Oversized token request rejected")
    print("Gateway rate limiting passed")


if __name__ == "__main__":
    asyncio.run(main())
