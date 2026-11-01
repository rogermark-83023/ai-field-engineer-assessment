import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from rate_limiter import RateLimiter

async def main():
    with TemporaryDirectory() as folder:
        current_time = [1000.0]

        limiter = RateLimiter(
            Path(folder) / "usage.db",
            clock=lambda: current_time[0]
        )

        await limiter.setup()

        assert await limiter.reserve("tenant-a", 20_000) is not None
        assert await limiter.reserve("tenant-a", 30_000) is not None
        assert await limiter.reserve("tenant-a", 1) is None
        assert await limiter.used("tenant-a") == 50_000
        print("Token limit passed")

        assert await limiter.reserve("tenant-b", 10_000) is not None
        assert await limiter.used("tenant-b") == 10_000
        print("Tenant isolation passed")

        current_time[0] += 59
        assert await limiter.reserve("tenant-a", 1) is None

        current_time[0] += 1
        assert await limiter.reserve("tenant-a", 50_000) is not None
        print("Sliding window passed")

        results = await asyncio.gather(*(
            limiter.reserve("parallel", 6_000) for _ in range(10)
        ))

        assert sum(result is not None for result in results) == 8
        assert await limiter.used("parallel") == 48_000
        print("Concurrent requests passed")

        
        first = await limiter.reserve("overrun", 49_990)
        second = await limiter.reserve("overrun", 10)

        assert first is not None
        assert second is not None

        within_limit = await limiter.reconcile(second, 20)

        assert within_limit is False
        assert await limiter.used("overrun") == 50_010
        assert await limiter.reserve("overrun", 1) is None

        print("Unexpected token overuse handled")

    print("All rate limiter tests passed")


if __name__ == "__main__":
    asyncio.run(main())
