from typing import Annotated
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field, StringConstraints

class StrictFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()

        for tool in tools:
            tool.inputSchema["additionalProperties"] = False

        return tools

    async def call_tool(self, name: str, arguments: dict):
        tools = await self.list_tools()
        tool = next((item for item in tools if item.name == name), None)

        if tool is not None:
            allowed = set(tool.inputSchema.get("properties", {}))
            extra = set(arguments) - allowed

            if extra:
                raise ToolError(
                    f"Unexpected input fields: {', '.join(sorted(extra))}"
                )

        return await super().call_tool(name, arguments)


mcp = StrictFastMCP("customer-service")

CustomerId = Annotated[
    str,
    StringConstraints(pattern=r"^CUST-[0-9]{5}$", strict=True)
]

RefundReason = Annotated[
    str,
    StringConstraints(min_length=10, strip_whitespace=True, strict=True)
]

CUSTOMERS = {
    "CUST-12345": {
        "customer_id": "CUST-12345",
        "name": "John Smith",
        "status": "active"
    },
    "CUST-67890": {
        "customer_id": "CUST-67890",
        "name": "Jane Miller",
        "status": "active"
    }
}

REFUNDS = []


@mcp.tool(description="Get a customer record by ID")
def get_customer_record(customer_id: CustomerId) -> dict:
    customer = CUSTOMERS.get(customer_id)

    if customer is None:
        raise ToolError("Customer not found")

    return customer


@mcp.tool(description="Create a customer refund")
def trigger_refund(
    customer_id: CustomerId,
    amount: Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)],
    reason: RefundReason
) -> dict:
    if customer_id not in CUSTOMERS:
        raise ToolError("Customer not found")

    refund = {
        "refund_id": uuid4().hex,
        "customer_id": customer_id,
        "amount": amount,
        "reason": reason,
        "status": "created"
    }

    REFUNDS.append(refund)
    return refund


if __name__ == "__main__":
    mcp.run(transport="stdio")
