import asyncio
import json
import time
import httpx
from redactor import StreamRedactor
from gateway import filter_stream

CASES = [
    (
        "Email",
        "Contact john@example.com now.",
        "Contact [REDACTED] now."
    ),
    (
        "Email with punctuation",
        "Email john@example.com.",
        "Email [REDACTED]."
    ),
    (
        "Email with multiple domain parts",
        "Send to john@example.co.uk today.",
        "Send to [REDACTED] today."
    ),
    (
        "SSN",
        "SSN 123-45-6789 end.",
        "SSN [REDACTED] end."
    ),
    (
        "Credit card with spaces",
        "Card 4111 1111 1111 1111 is a test.",
        "Card [REDACTED] is a test."
    ),
    (
        "Credit card with hyphens",
        "Card 4111-1111-1111-1111 today.",
        "Card [REDACTED] today."
    ),
    (
        "Multiple private values",
        "Email john@example.com. SSN 123-45-6789.",
        "Email [REDACTED]. SSN [REDACTED]."
    ),
    (
        "Normal text",
        "Hello there!",
        "Hello there!"
    ),
    (
        "SSN with spaces",
        "My SSN is 123 45 6789.",
        "My SSN is [REDACTED]."
    ),
    (
        "SSN without separators",
        "My SSN is 123456789.",
        "My SSN is [REDACTED]."
    ),
    
    (
        "Long normal word",
        "A" * 400 + " finished.",
        "A" * 400 + " finished."
    ),
    (
        "Long text before email",
        "A" * 400 + " john@example.com.",
        "A" * 400 + " [REDACTED]."
    )
]

def test_redaction():
    for name, original, expected in CASES:
        for size in (1, 2, 3, 5, 10, 100):
            redactor = StreamRedactor()

            chunks = (
                original[i:i + size]
                for i in range(0, len(original), size)
            )

            actual = "".join(redactor.feed(chunk) for chunk in chunks)
            actual += redactor.finish()

            assert actual == expected, (
                f"{name} failed for chunk size {size}: {actual}"
            )

        print(f"{name} passed")

    redactor = StreamRedactor()
    actual = "".join(
        redactor.feed("hello world ")
        for _ in range(1000)
    )
    actual += redactor.finish()

    assert actual == "hello world " * 1000
    print("Long stream passed")


async def test_gateway():
    url = "http://127.0.0.1:8003/v1/chat/completions"

    chunks = []
    first_chunk = None
    completed = False

    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=10.0) as client:
        async with client.stream("POST", url, json={}) as response:
            assert response.status_code == 200

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data = line[6:]

                if data == "[DONE]":
                    completed = True
                    break

                packet = json.loads(data)

                for choice in packet.get("choices", []):
                    text = choice.get("delta", {}).get("content", "")

                    if text:
                        if first_chunk is None:
                            first_chunk = time.perf_counter()

                        chunks.append(text)

    finished = time.perf_counter()

    result = "".join(chunks)

    expected = (
        "Hello! You can contact me at [REDACTED] "
        "for more information. My SSN is [REDACTED]. "
        "My card number is [REDACTED]. Thank you!"
    )

    assert result == expected
    assert completed
    assert first_chunk is not None
    assert finished - first_chunk >= 0.5

    print("Gateway redaction passed")
    print("Streaming completion passed")
    print(f"Time to first text: {first_chunk - started:.3f}s")
    print(f"Total response time: {finished - started:.3f}s")


class FakeResponse:
    async def aiter_lines(self):
        packet = {
            "id": "john@example.com",
            "debug": "123-45-6789",
            "choices": [{
                "index": 0,
                "delta": {
                    "content": "Hello!",
                    "reasoning_content": "john@example.com"
                },
                "finish_reason": None
            }]
        }

        yield f"data: {json.dumps(packet)}"
        yield ""
        yield "data: [DONE]"
        yield ""

    async def aiter_bytes(self, chunk_size=4096):
        async for line in self.aiter_lines():
            yield (line + "\n").encode()

    async def aclose(self):
        pass


async def test_unfiltered_fields():
    output = "".join([
        chunk async for chunk in filter_stream(FakeResponse())
    ])

    assert "john@example.com" not in output
    assert "123-45-6789" not in output
    assert "reasoning_content" not in output

    packets = [
        json.loads(line[6:])
        for line in output.splitlines()
        if line.startswith("data: {")
    ]

    assert packets[0]["choices"][0]["delta"]["content"] == "Hello!"
    assert "data: [DONE]" in output

    print("Unfiltered response fields blocked")


class OversizedResponse:
    def __init__(self):
        self.closed = False

    async def aiter_bytes(self, chunk_size=4096):
        for _ in range(20):
            yield b"data: " + b"A" * 3990 + b"\n"

    async def aclose(self):
        self.closed = True


async def test_oversized_event():
    response = OversizedResponse()
    output = "".join([chunk async for chunk in filter_stream(response)])

    assert 'event: error' in output
    assert "A" * 100 not in output
    assert "data: [DONE]" not in output
    assert response.closed
    print("Oversized SSE event rejected")


async def main():
    test_redaction()
    await test_unfiltered_fields()
    await test_oversized_event()
    await test_gateway()
    print("All guardrail tests passed")


if __name__ == "__main__":
    asyncio.run(main())
