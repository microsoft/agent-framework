# Copyright (c) Microsoft. All rights reserved.

"""Mock invoice data and tool functions for the A2A server sample.

Provides mock invoice data and query tools for the A2A server sample,
enabling invoice-related queries through the A2A protocol.
"""

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field


@dataclass
class Product:
    """A product line item on an invoice."""

    name: str
    quantity: int
    price_per_unit: float

    @property
    def total_price(self) -> float:
        return self.quantity * self.price_per_unit

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "price_per_unit": self.price_per_unit,
            "total_price": self.total_price,
        }


@dataclass
class Invoice:
    """An invoice record with products."""

    transaction_id: str
    invoice_id: str
    company_name: str
    invoice_date: datetime
    products: list[Product] = field(default_factory=list)

    @property
    def total_invoice_price(self) -> float:
        return sum(p.total_price for p in self.products)

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "invoice_id": self.invoice_id,
            "company_name": self.company_name,
            "invoice_date": self.invoice_date.strftime("%Y-%m-%d"),
            "products": [p.to_dict() for p in self.products],
            "total_invoice_price": self.total_invoice_price,
        }


def _random_date_within_last_two_months() -> datetime:
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=60)
    random_days = random.randint(0, 60)
    return start_date + timedelta(days=random_days)


def _build_invoices() -> list[Invoice]:
    """Build 10 mock invoices."""
    return [
        Invoice(
            "TICKET-XYZ987",
            "INV789",
            "Contoso",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 150, 10.00),
                Product("Hats", 200, 15.00),
                Product("Glasses", 300, 5.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ111",
            "INV111",
            "XStore",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 2500, 12.00),
                Product("Hats", 1500, 8.00),
                Product("Glasses", 200, 20.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ222",
            "INV222",
            "Cymbal Direct",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 1200, 14.00),
                Product("Hats", 800, 7.00),
                Product("Glasses", 500, 25.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ333",
            "INV333",
            "Contoso",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 400, 11.00),
                Product("Hats", 600, 15.00),
                Product("Glasses", 700, 5.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ444",
            "INV444",
            "XStore",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 800, 10.00),
                Product("Hats", 500, 18.00),
                Product("Glasses", 300, 22.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ555",
            "INV555",
            "Cymbal Direct",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 1100, 9.00),
                Product("Hats", 900, 12.00),
                Product("Glasses", 1200, 15.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ666",
            "INV666",
            "Contoso",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 2500, 8.00),
                Product("Hats", 1200, 10.00),
                Product("Glasses", 1000, 6.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ777",
            "INV777",
            "XStore",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 1900, 13.00),
                Product("Hats", 1300, 16.00),
                Product("Glasses", 800, 19.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ888",
            "INV888",
            "Cymbal Direct",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 2200, 11.00),
                Product("Hats", 1700, 8.50),
                Product("Glasses", 600, 21.00),
            ],
        ),
        Invoice(
            "TICKET-XYZ999",
            "INV999",
            "Contoso",
            _random_date_within_last_two_months(),
            [
                Product("T-Shirts", 1400, 10.50),
                Product("Hats", 1100, 9.00),
                Product("Glasses", 950, 12.00),
            ],
        ),
    ]


# Module-level singleton so dates are stable for the lifetime of the server
INVOICES = _build_invoices()


@tool(approval_mode="never_require")
def query_invoices(
    company_name: Annotated[str, Field(description="The company name to filter invoices by.")],
    start_date: Annotated[str | None, Field(description="Optional start date (YYYY-MM-DD) to filter invoices.")] = None,
    end_date: Annotated[str | None, Field(description="Optional end date (YYYY-MM-DD) to filter invoices.")] = None,
) -> str:
    """Retrieves invoices for the specified company and optionally within the specified time range."""
    results = [i for i in INVOICES if i.company_name.lower() == company_name.lower()]

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        results = [i for i in results if i.invoice_date >= start]

    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        results = [i for i in results if i.invoice_date < end]

    return json.dumps([i.to_dict() for i in results], indent=2)


@tool(approval_mode="never_require")
def query_by_transaction_id(
    transaction_id: Annotated[str, Field(description="The transaction ID to look up (e.g. TICKET-XYZ987).")],
) -> str:
    """Retrieves invoice using the transaction id."""
    results = [i for i in INVOICES if i.transaction_id.lower() == transaction_id.lower()]
    return json.dumps([i.to_dict() for i in results], indent=2)


@tool(approval_mode="never_require")
def query_by_invoice_id(
    invoice_id: Annotated[str, Field(description="The invoice ID to look up (e.g. INV789).")],
) -> str:
    """Retrieves invoice using the invoice id."""
    results = [i for i in INVOICES if i.invoice_id.lower() == invoice_id.lower()]
    return json.dumps([i.to_dict() for i in results], indent=2)
