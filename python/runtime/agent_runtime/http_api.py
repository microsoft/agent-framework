"""HTTP API layer for the agent runtime"""

from typing import Dict, Any, List, Optional
import asyncio
import logging
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    print("FastAPI and Pydantic are required for HTTP API. Install with: pip install fastapi pydantic uvicorn")
    raise

from .runtime import InProcessActorRuntime, InProcessActorClient
from .agent_actor import AgentActor, MockAIAgent, EchoAgent
from .runtime_abstractions import ActorId


logger = logging.getLogger(__name__)


# Request/Response models
class ChatMessageModel(BaseModel):
    role: str
    text: Optional[str] = None
    content: Optional[str] = None
    message_id: Optional[str] = None


class AgentRunRequest(BaseModel):
    agent_name: str
    conversation_id: Optional[str] = None
    messages: List[ChatMessageModel]


# Note: We'll use the framework's AgentRunResponse instead of defining our own


class AgentInfo(BaseModel):
    name: str
    type: str
    description: str


# Global runtime instance
runtime: InProcessActorRuntime = None
client: InProcessActorClient = None


# Agents will be registered by applications via the registration endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the runtime lifecycle"""
    global runtime, client
    
    # Startup
    logger.info("Starting agent runtime...")
    runtime = InProcessActorRuntime()
    client = InProcessActorClient(runtime)
    
    # No agents registered by default - applications must register their own
    
    await runtime.start()
    logger.info("Agent runtime started")
    
    yield
    
    # Shutdown  
    logger.info("Stopping agent runtime...")
    await runtime.stop()
    logger.info("Agent runtime stopped")


# Create FastAPI app
app = FastAPI(
    title="Agent Runtime API",
    description="HTTP API for the Python Agent Runtime",
    version="0.1.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Agent Runtime API",
        "version": "0.1.0",
        "status": "running"
    }


@app.post("/agents/register")
async def register_agent(registration: AgentRegistration):
    """Register a new agent type with the runtime."""
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")
    
    # Create the appropriate agent factory based on type
    if registration.factory_type == "mock":
        factory = lambda actor_id: AgentActor(MockAIAgent(registration.description))
    elif registration.factory_type == "helpful":
        responses = [
            "I'm here to help! What would you like to know?",
            "That's a great question. Let me think about it.",
            "I'd be happy to assist you with that.",
            "Here's what I think about your request.",
            "Is there anything else I can help you with?"
        ]
        factory = lambda actor_id: AgentActor(MockAIAgent(registration.description, responses))
    elif registration.factory_type == "echo":
        factory = lambda actor_id: AgentActor(EchoAgent(registration.description))
    else:
        raise HTTPException(status_code=400, detail=f"Unknown factory type: {registration.factory_type}")
    
    # Register with runtime
    runtime.register_actor_type(registration.name, factory)
    
    # Track registration
    registered_agents[registration.name] = {
        "type": registration.type,
        "description": registration.description,
        "factory_type": registration.factory_type
    }
    
    logger.info(f"Registered agent: {registration.name} ({registration.type})")
    return {"status": "registered", "name": registration.name}


@app.get("/agents", response_model=List[AgentInfo])
async def list_agents():
    """List available registered agent types."""
    return [
        AgentInfo(
            name=name,
            type=info.get("type", "unknown"),
            description=info.get("description", f"Agent: {name}")
        )
        for name, info in registered_agents.items()
    ]


@app.post("/agents/{agent_name}/run")
async def run_agent(agent_name: str, request: AgentRunRequest):
    """Run an agent with the provided messages"""
    
    if not runtime or not client:
        raise HTTPException(status_code=503, detail="Runtime not available")
    
    try:
        # Create actor ID
        conversation_id = request.conversation_id or f"http-{agent_name}"
        actor_id = ActorId(agent_name, conversation_id)
        
        # Prepare messages
        messages_data = [
            {
                "role": msg.role,
                "text": (msg.text if msg.text is not None else (msg.content or "")),
                "message_id": msg.message_id
            }
            for msg in request.messages
        ]
        
        # Send request to actor
        response_handle = await client.send_request(
            actor_id,
            "run",
            {"messages": messages_data}
        )
        
        # Get response
        response = await response_handle.get_response()
        
        if response.status.value == "failed":
            error_msg = response.data.get("error", "Unknown error") if response.data else "Unknown error"
            raise HTTPException(status_code=500, detail=f"Agent failed: {error_msg}")
        
        # Return the response data directly - it should already be in AgentRunResponse format
        return response.data
        
    except Exception as e:
        logger.error(f"Error running agent {agent_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "runtime_running": runtime is not None and runtime._running
    }


if __name__ == "__main__":
    import uvicorn
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🚀 Starting Agent Runtime HTTP API")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("🔍 Test endpoint: http://localhost:8000/agents")
    
    uvicorn.run(
        "agent_runtime.http_api:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False
    )