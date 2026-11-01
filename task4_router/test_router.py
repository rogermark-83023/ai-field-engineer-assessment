import asyncio
import sqlite3
import time
from contextlib import closing
from pathlib import Path
import httpx

URL = "http://127.0.0.1:8005/v1/chat/completions"
DB_PATH = Path(__file__).with_name("usage.db")

PAYLOAD = {
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "max_tokens": 64
}


def latest_usage(tenant):
    with closing(sqlite3.connect(DB_PATH)) as db:
        row = db.execute(
            "SELECT tokens FROM token_usage "
            "WHERE tenant = ? ORDER BY id DESC LIMIT 1",
            (tenant,)
        ).fetchone()

    return row[0] if row else None

def reservation_count(tenant):
    with closing(sqlite3.connect(DB_PATH)) as db:
        row = db.execute(
            "SELECT COUNT(*) FROM token_usage WHERE tenant = ?",
            (tenant,)
        ).fetchone()

    return row[0]

async def main():
    async with httpx.AsyncClient(timeout=12.0) as client:

        async def send(mode, key="tenant-a-key"):
            return await client.post(
                URL,
                json={**PAYLOAD, "simulate": mode},
                headers={"Authorization": f"Bearer {key}"}
            )

        response = await send("normal")

        assert response.status_code == 200
        assert response.json()["provider"] == "primary"
        print("Primary model passed")

        response = await send("rate_limit")

        assert response.status_code == 200
        assert response.json()["provider"] == "backup"
        print("429 fallback passed")

        started = time.perf_counter()
        response = await send("timeout")
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        assert response.json()["provider"] == "backup"
        assert elapsed >= 2.9
        print(f"Timeout fallback passed ({elapsed:.2f}s)")

        assert latest_usage("tenant-a") == 13
        print("SQLite token reconciliation passed")

        response = await send("normal", "tenant-b-key")

        assert response.status_code == 200
        assert latest_usage("tenant-b") == 13
        print("Second tenant passed")

        
        before = reservation_count("tenant-a")

        response = await send("primary_error")

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "UPSTREAM_ERROR"
        print("Primary failure handled")

        response = await send("backup_failure")

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "UPSTREAM_ERROR"
        assert "traceback" not in response.text.lower()
        print("Backup failure handled safely")

        assert reservation_count("tenant-a") == before
        print("Failed reservations released")

        response = await client.post(URL, json=PAYLOAD)

        assert response.status_code == 401
        print("Missing API key rejected")

        response = await send("normal", "wrong-key")

        assert response.status_code == 401
        print("Invalid API key rejected")

        response = await client.post(
            URL,
            json={**PAYLOAD, "max_tokens": 0},
            headers={"Authorization": "Bearer tenant-a-key"}
        )

        assert response.status_code == 400
        print("Invalid request rejected")

        response = await client.post(
            URL,
            content="{invalid",
            headers={
                "Authorization": "Bearer tenant-a-key",
                "Content-Type": "application/json"
            }
        )

        assert response.status_code == 400
        print("Invalid JSON rejected")

    print("All model router tests passed")


if __name__ == "__main__":
    asyncio.run(main())
