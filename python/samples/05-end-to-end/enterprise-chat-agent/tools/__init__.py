"""
Enterprise Chat Agent - Function Tools

This module contains the local tools that the ChatAgent can invoke at runtime.
The agent autonomously decides which tools to use based on the user's message.

Local Tools:
- get_weather: Get weather information for a location
- calculate: Evaluate mathematical expressions
- search_knowledge_base: Search internal company knowledge base

MCP Tools (via Microsoft Learn MCP Server):
- microsoft_docs_search: Search Microsoft documentation
- microsoft_code_sample_search: Search code samples

MCP tools are connected at runtime via MCPStreamableHTTPTool in agent_service.py
"""

from tools.weather import get_weather
from tools.calculator import calculate
from tools.knowledge_base import search_knowledge_base

__all__ = [
    "get_weather",
    "calculate",
    "search_knowledge_base",
]
