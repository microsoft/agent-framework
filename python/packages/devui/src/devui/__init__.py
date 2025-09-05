# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework Debug UI - Public API.

Provides high-level convenience functions for debugging Agent Framework
agents and workflows with minimal setup.
"""

import logging
import webbrowser
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework import AgentProtocol
    from agent_framework.workflow import Workflow
    from fastapi import FastAPI

from .discovery import DirectoryScanner
from .execution import ExecutionEngine
from .models import AgentInfo, DebugStreamEvent, RunAgentRequest, SessionInfo, ThreadInfo
from .registry import AgentRegistry
from .server import AgentFrameworkDebugServer, create_debug_server
from .sessions import SessionManager
from .tracing import TracingManager

logger = logging.getLogger(__name__)

__version__ = "0.1.0"

# Main convenience function
def debug(
    agents: Optional[Dict[str, 'AgentProtocol']] = None,
    workflows: Optional[Dict[str, 'Workflow']] = None, 
    agents_dir: Optional[str] = None,
    port: int = 8080,
    auto_open: bool = False,
    host: str = "127.0.0.1"
) -> None:
    """Launch Agent Framework debug UI with type-safe agent/workflow registration.
    
    This is the main entry point for debugging Agent Framework agents and workflows.
    Supports both in-memory registration and directory-based discovery.
    
    Args:
        agents: Dictionary of agent_id -> AgentProtocol for in-memory registration
        workflows: Dictionary of workflow_id -> Workflow for in-memory registration
        agents_dir: Optional directory to scan for agents (following conventions)
        port: Port to run the debug server on
        auto_open: Whether to automatically open browser
        host: Host to bind the server to
        
    Example:
        ```python
        from agent_framework import ChatClientAgent
        from agent_framework.openai import OpenAIChatClient
        from devui import debug
        
        # Create agent
        agent = ChatClientAgent(
            name="WeatherAgent",
            chat_client=OpenAIChatClient(),
            tools=[get_weather]
        )
        
        # Launch debug UI
        debug(agents={"weather": agent}, auto_open=True)
        ```
    """
    import uvicorn
    
    # Create server instance
    server = DebugServer(agents_dir=agents_dir, port=port, host=host)
    
    # Register in-memory agents and workflows
    if agents:
        for agent_id, agent in agents.items():
            server.register_agent(agent_id, agent)
            
    if workflows:
        for workflow_id, workflow in workflows.items():
            server.register_workflow(workflow_id, workflow)
    
    # Start server
    server.start(auto_open=auto_open)

class DebugServer:
    """Main debug server class for programmatic control with strict typing.
    
    Provides fine-grained control over the debug server for advanced use cases.
    """
    
    def __init__(
        self, 
        agents_dir: Optional[str] = None, 
        port: int = 8080,
        host: str = "127.0.0.1"
    ) -> None:
        """Initialize debug server.
        
        Args:
            agents_dir: Optional directory to scan for agents
            port: Port to run server on
            host: Host to bind server to
        """
        self._server = AgentFrameworkDebugServer(agents_dir=agents_dir)
        self.port = port
        self.host = host
        self._app: Optional['FastAPI'] = None
        
    def register_agent(self, agent_id: str, agent: 'AgentProtocol') -> None:
        """Register an in-memory agent with type validation.
        
        Args:
            agent_id: Unique identifier for the agent
            agent: Agent Framework agent instance
        """
        self._server.register_agent(agent_id, agent)
        
    def register_workflow(self, workflow_id: str, workflow: 'Workflow') -> None:
        """Register an in-memory workflow with type validation.
        
        Args:
            workflow_id: Unique identifier for the workflow  
            workflow: Agent Framework workflow instance
        """
        self._server.register_workflow(workflow_id, workflow)
        
    def get_app(self) -> 'FastAPI':
        """Get the FastAPI application instance.
        
        Returns:
            FastAPI application that can be embedded or extended
        """
        if self._app is None:
            self._app = self._server.create_app()
        return self._app
        
    def start(self, auto_open: bool = False) -> None:
        """Start the debug server.
        
        Args:
            auto_open: Whether to automatically open browser to debug UI
        """
        import uvicorn
        
        app = self.get_app()
        
        if auto_open:
            # Open browser after short delay
            def open_browser():
                import time
                time.sleep(1.5)  # Give server time to start
                webbrowser.open(f"http://{self.host}:{self.port}")
                
            import threading
            threading.Thread(target=open_browser, daemon=True).start()
            
        logger.info(f"Starting Agent Framework Debug Server on {self.host}:{self.port}")
        
        uvicorn.run(
            app,
            host=self.host,
            port=self.port,
            log_level="info"
        )

def main():
    """CLI entry point for devui command."""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Launch Agent Framework Debug UI")
    parser.add_argument("directory", nargs="?", default=".", 
                       help="Directory to scan for agents (default: current directory)")
    parser.add_argument("--port", "-p", type=int, default=8080, 
                       help="Port to run server on (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", 
                       help="Host to bind server to (default: 127.0.0.1)")
    parser.add_argument("--no-open", action="store_true", 
                       help="Don't automatically open browser")
    
    args = parser.parse_args()
    
    # Convert to absolute path
    agents_dir = os.path.abspath(args.directory)
    
    print(f"🔍 Scanning {agents_dir} for agents...")
    
    # Quick discovery check to provide feedback
    from .discovery import DirectoryScanner
    scanner = DirectoryScanner(agents_dir)
    discovered = scanner.discover_agents()
    
    if discovered:
        print(f"📋 Found {len(discovered)} agents/workflows:")
        for item in discovered:
            print(f"   • {item.id} ({item.type})")
    else:
        print(f"⚠️  No agents found in {agents_dir}")
        print(f"   Make sure the directory contains valid agent/workflow modules")
        print(f"   See documentation for directory structure requirements")
    
    print(f"🚀 Starting devui on http://{args.host}:{args.port}")
    
    # Launch debug UI
    debug(
        agents_dir=agents_dir,
        port=args.port,
        host=args.host,
        auto_open=not args.no_open
    )

# Export main public API
__all__ = [
    "debug",
    "DebugServer", 
    "AgentFrameworkDebugServer",
    "create_debug_server"
]