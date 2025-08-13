"""HTTP API layer for the agent runtime"""

from typing import Dict, Any, List
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
    text: str | None = None
    content: str | None = None
    message_id: str | None = None


class AgentRunRequest(BaseModel):
    agent_name: str
    conversation_id: str | None = None
    messages: List[ChatMessageModel]


# Note: We'll use the framework's AgentRunResponse instead of defining our own


# Global runtime instance
runtime: InProcessActorRuntime = None
client: InProcessActorClient = None


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