import asyncio
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server = Path(__file__).with_name("server.py")

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server)]
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}

            assert names == {"get_customer_record", "trigger_refund"}
            print("Tool discovery passed")

            customer = await session.call_tool(
                "get_customer_record",
                arguments={"customer_id": "CUST-12345"}
            )

            assert not customer.isError
            print("Customer lookup passed")

            refund = await session.call_tool(
                "trigger_refund",
                arguments={
                    "customer_id": "CUST-12345",
                    "amount": 50.0,
                    "reason": "Customer returned the item"
                }
            )

            assert not refund.isError
            print("Refund creation passed")

            invalid = await session.call_tool(
                "trigger_refund",
                arguments={
                    "customer_id": "CUST-12345",
                    "amount": -10,
                    "reason": "Too short"
                }
            )

            assert invalid.isError
            print("Input validation passed")
            
            bad_requests = [
                (
                    "Invalid customer ID",
                    "get_customer_record",
                    {"customer_id": "CUST-1234"}
                ),
                (
                    "Customer ID is not a string",
                    "get_customer_record",
                    {"customer_id": 12345}
                ),
                (
                    "Zero refund amount",
                    "trigger_refund",
                    {
                        "customer_id": "CUST-12345",
                        "amount": 0,
                        "reason": "Customer returned the item"
                    }
                ),
                (
                    "Short refund reason",
                    "trigger_refund",
                    {
                        "customer_id": "CUST-12345",
                        "amount": 50,
                        "reason": "Too short"
                    }
                ),
                (
                    "Unexpected input field",
                    "get_customer_record",
                    {
                        "customer_id": "CUST-12345",
                        "unexpected": True
                    }
                ),
                
                (
                    "Refund amount as text",
                    "trigger_refund",
                    {
                        "customer_id": "CUST-12345",
                        "amount": "50",
                        "reason": "Customer returned the item"
                    }
                ),
                (
                    "Refund amount as Boolean",
                    "trigger_refund",
                    {
                        "customer_id": "CUST-12345",
                        "amount": True,
                        "reason": "Customer returned the item"
                    }
                ),
            ]

            for label, tool_name, arguments in bad_requests:
                result = await session.call_tool(
                    tool_name,
                    arguments=arguments
                )

                assert result.isError, f"{label} was accepted"
                print(f"{label} rejected")

    print("All basic tests passed")


if __name__ == "__main__":
    asyncio.run(main())
