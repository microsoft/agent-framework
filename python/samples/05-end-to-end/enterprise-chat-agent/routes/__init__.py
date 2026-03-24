# Copyright (c) Microsoft. All rights reserved.

"""
Route blueprints for Enterprise Chat Agent.

This package contains Azure Functions blueprints organized by resource:
- threads: Thread CRUD operations
- messages: Message send/retrieve operations
- health: Health check endpoint
"""

from routes.threads import bp as threads_bp
from routes.messages import bp as messages_bp
from routes.health import bp as health_bp

__all__ = ["threads_bp", "messages_bp", "health_bp"]
