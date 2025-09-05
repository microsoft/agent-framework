#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""
Example of using Agent Framework Debug UI with directory-based discovery.

This demonstrates the ADK-style approach where agents are discovered
from the filesystem following standard conventions.

IMPORTANT: This example requires agent_framework to be installed in your Python environment.
If you get import errors, make sure to:
1. Install the agent framework: pip install agent-framework
2. Or run with the correct Python environment that has agent_framework installed

Usage:
    python examples/directory_mode.py                              # Uses ./examples/sample_agents (relative to script)
    AGENTS_DIR=/path/to/agents python examples/directory_mode.py   # Uses custom directory
    
The script automatically looks for agents in a 'sample_agents' directory relative to its own location,
making it work regardless of where you run it from.
"""

import os
from pathlib import Path

from devui import create_debug_server

def main():
    """Main function demonstrating directory-based agent discovery."""
    
    print("🚀 Agent Framework Debug UI - Directory Mode Example")
    print("="*60)
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    
    # Look for agents relative to this script's location by default
    default_agents_dir = script_dir / "sample_agents"
    agents_dir = os.environ.get('AGENTS_DIR', str(default_agents_dir))
    agents_path = Path(agents_dir).resolve()
    
    print(f"Scanning for agents in: {agents_path}")
    
    if not agents_path.exists():
        print(f"⚠️  Agents directory does not exist: {agents_path}")
        print(f"   Create it with sample agents using:")
        print(f"   mkdir -p {agents_path}")
        print(f"   # Then add agent directories following conventions")
        print(f"   # Or run with: AGENTS_DIR=/path/to/your/agents python examples/directory_mode.py")
        print(f"   # This script looks for agents relative to: {script_dir}")
        return
    
    # Check if there are any potential agent directories
    agent_dirs = [
        d for d in agents_path.iterdir() 
        if d.is_dir() and not d.name.startswith('.') and d.name != '__pycache__'
    ]
    
    if not agent_dirs:
        print(f"⚠️  No agent directories found in {agents_path}")
        print(f"   Expected structure:")
        print(f"   {agents_path}/")
        print(f"   ├── my_agent/")
        print(f"   │   ├── __init__.py")
        print(f"   │   ├── agent.py")
        print(f"   │   └── .env")
        print(f"   └── my_workflow/")
        print(f"       ├── __init__.py")
        print(f"       └── workflow.py")
        return
    
    print(f"Found {len(agent_dirs)} potential agent directories:")
    for agent_dir in agent_dirs:
        print(f"  • {agent_dir.name}")
    print()
    
    # Create debug server with directory scanning
    print("Creating debug server with directory scanning...")
    app = create_debug_server(agents_dir=str(agents_path))
    
    print(f"🌐 Starting server on http://localhost:8080")
    print(f"📊 API documentation: http://localhost:8080/docs")
    print(f"❤️  Health check: http://localhost:8080/health")
    print()
    print("Available endpoints:")
    print("  • GET  /agents                 - List discovered agents")
    print("  • POST /agents/{id}/run/stream - Execute agent with streaming")
    print("  • GET  /sessions/{id}/traces   - View execution traces")
    print()
    
    # Run the server
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1", 
        port=8080,
        log_level="info"
    )

if __name__ == "__main__":
    main()