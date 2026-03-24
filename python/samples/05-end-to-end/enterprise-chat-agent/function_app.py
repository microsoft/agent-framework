# Copyright (c) Microsoft. All rights reserved.

"""
Enterprise Chat Agent - Azure Functions Application

This sample demonstrates a production-ready Chat API using Microsoft Agent Framework
with Azure Functions. The agent is configured with multiple tools and autonomously
decides which tools to invoke based on user intent.

Key Features:
- Azure Functions HTTP triggers for REST API endpoints
- ChatAgent with runtime tool selection
- Cosmos DB for persistent thread and message storage
- OpenTelemetry observability with automatic and custom spans
"""

import azure.functions as func

from services import init_observability
from routes import threads_bp, messages_bp, health_bp

# Initialize observability once at startup
init_observability()

# Create the Function App and register blueprints
app = func.FunctionApp()
app.register_functions(threads_bp)
app.register_functions(messages_bp)
app.register_functions(health_bp)
