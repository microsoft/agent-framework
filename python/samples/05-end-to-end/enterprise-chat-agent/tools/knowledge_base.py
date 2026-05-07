"""
Knowledge Base Search Tool

Provides search functionality over a knowledge base.
In a production scenario, this would integrate with Azure AI Search,
Cosmos DB, or another search service.
"""

from agent_framework import tool

# Simulated knowledge base entries
KNOWLEDGE_BASE = [
    {
        "id": "kb_001",
        "title": "Order Status FAQ",
        "content": (
            "To check your order status, log into your account and visit the "
            "'My Orders' section. Track your package using the tracking number sent to your email."
        ),
        "category": "orders",
    },
    {
        "id": "kb_002",
        "title": "Return Policy",
        "content": (
            "Items can be returned within 30 days of purchase. "
            "Items must be unused and in original packaging. Refunds processed in 5-7 business days."
        ),
        "category": "returns",
    },
    {
        "id": "kb_003",
        "title": "Shipping Information",
        "content": (
            "Standard shipping takes 5-7 business days. "
            "Express shipping (2-3 days) available for an additional fee. Free shipping on orders over $50."
        ),
        "category": "shipping",
    },
    {
        "id": "kb_004",
        "title": "Payment Methods",
        "content": (
            "We accept Visa, Mastercard, American Express, PayPal, and Apple Pay. "
            "All transactions are securely processed."
        ),
        "category": "payments",
    },
    {
        "id": "kb_005",
        "title": "Account Management",
        "content": (
            "To update your account information, go to Settings > Profile. "
            "You can change your email, password, and notification preferences there."
        ),
        "category": "account",
    },
]


@tool
def search_knowledge_base(
    query: str,
    category: str | None = None,
    max_results: int = 3,
) -> list[dict]:
    """
    Search the knowledge base for relevant information.

    Args:
        query: The search query.
        category: Optional category to filter results (e.g., "orders", "returns").
        max_results: Maximum number of results to return.

    Returns:
        A list of matching knowledge base entries.
    """
    query_lower = query.lower()
    results = []

    for entry in KNOWLEDGE_BASE:
        # Filter by category if specified
        if category and entry["category"] != category.lower():
            continue

        # Simple keyword matching (replace with vector search in production)
        if (
            query_lower in entry["title"].lower()
            or query_lower in entry["content"].lower()
            or any(word in entry["content"].lower() for word in query_lower.split())
        ):
            results.append(
                {
                    "id": entry["id"],
                    "title": entry["title"],
                    "content": entry["content"],
                    "category": entry["category"],
                    "relevance_score": 0.85,  # Simulated score
                }
            )

    # Sort by relevance (simulated) and limit results
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:max_results]
