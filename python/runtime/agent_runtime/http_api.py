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
    content: str
    message_id: Optional[str] = None


class AgentRunRequest(BaseModel):
    agent_name: str
    conversation_id: Optional[str] = None
    messages: List[ChatMessageModel]


class AgentRunResponse(BaseModel):
    messages: List[ChatMessageModel]
    status: str
    conversation_id: str


class AgentInfo(BaseModel):
    name: str
    type: str
    description: str


# Global runtime instance
runtime: InProcessActorRuntime = None
client: InProcessActorClient = None

# Flag to indicate whether an Azure OpenAI backed agent was registered
azure_agent_registered: bool = False
azure_agent_name: str = "azure"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the runtime lifecycle"""
    global runtime, client
    
    # Startup
    logger.info("Starting agent runtime...")
    runtime = InProcessActorRuntime()
    client = InProcessActorClient(runtime)
    
    # Register some default agents for testing
    runtime.register_actor_type(
        "mock-ai", 
        lambda actor_id: AgentActor(MockAIAgent("Mock AI Assistant"))
    )
    runtime.register_actor_type(
        "helpful", 
        lambda actor_id: AgentActor(MockAIAgent("Helpful Assistant", [
            "I'm here to help! What would you like to know?",
            "That's a great question. Let me think about it.",
            "I'd be happy to assist you with that.",
            "Here's what I think about your request.",
            "Is there anything else I can help you with?"
        ]))
    )
    runtime.register_actor_type(
        "echo", 
        lambda actor_id: AgentActor(EchoAgent("Echo Assistant"))
    )

    # Optionally register an Azure OpenAI backed agent if env vars are present.
    # Required: AZURE_OPENAI_API_KEY, AZURE_OPENAI_CHAT_DEPLOYMENT_NAME, (AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_BASE_URL)
    # Optional: AZURE_OPENAI_API_VERSION (defaults inside settings), AZURE_OPENAI_TOKEN_ENDPOINT
    import os, sys
    from pathlib import Path
    global azure_agent_registered
    try:
        # Add packages main & azure to path (mirrors agent_actor pattern for direct framework usage)
        packages_root = Path(__file__).resolve().parents[2] / "packages"
        main_pkg = packages_root / "main"
        azure_pkg = packages_root / "azure"
        for p in (main_pkg, azure_pkg):
            p_str = str(p)
            if p_str not in sys.path:
                sys.path.append(p_str)

        # Load optional .env file if present (developer convenience)
        # Search order: repo root/.env then python/.env
        candidate_env_files = [
            Path(__file__).resolve().parents[3] / ".env",  # repo root
            Path(__file__).resolve().parents[2] / ".env",   # python folder
        ]
        for f in candidate_env_files:
            if f.is_file():
                try:
                    for line in f.read_text(encoding="utf-8").splitlines():
                        if not line or line.strip().startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k and v and k not in os.environ:
                                os.environ[k] = v
                    logger.info("Loaded env vars from %s", f)
                    break  # stop at first found
                except Exception as load_exc:  # pragma: no cover
                    logger.warning("Failed loading %s: %s", f, load_exc)

        required_key = os.environ.get("AZURE_OPENAI_API_KEY")
        required_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_OPENAI_BASE_URL")
        if required_key and required_deployment and endpoint:
            try:
                from agent_framework_azure._chat_client import AzureChatClient  # type: ignore
            except Exception as import_exc:  # pragma: no cover - environment dependent
                logger.warning(f"Azure agent not registered (import failure): {import_exc}")
            else:
                api_version = os.environ.get("AZURE_OPENAI_API_VERSION")  # optional
                # Build factory to create a fresh ChatClientAgent per actor instance
                def _azure_actor_factory(actor_id):  # noqa: D401
                    chat_client = AzureChatClient(
                        api_key=required_key,
                        deployment_name=required_deployment,
                        endpoint=endpoint,
                        api_version=api_version,
                    )
                    # Create ChatClientAgent with simple instructions
                    agent = chat_client.create_agent(
                        name="Azure Chat Assistant",
                        instructions=(
                            "You are a helpful AI assistant powered by Azure OpenAI. "
                            "Adopt a light, friendly pirate persona: sprinkle in mild pirate slang like 'Ahoy', 'aye', and 'matey'. "
                            "Stay concise, professional, and easy to read; avoid heavy dialect, excessive 'Arrr', or altering technical terms. "
                            "If giving code or structured data, present it normally (no pirate modifications inside code)."
                        )
                    )
                    return AgentActor(agent)

                runtime.register_actor_type(azure_agent_name, _azure_actor_factory)
                azure_agent_registered = True
                logger.info("Registered Azure OpenAI agent: %s", azure_agent_name)
        else:
            missing = [
                k for k, v in [
                    ("AZURE_OPENAI_API_KEY", required_key),
                    ("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", required_deployment),
                    ("AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_BASE_URL", endpoint),
                ] if not v
            ]
            if missing:
                logger.info("Azure agent not registered; missing env vars: %s", ", ".join(missing))
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Unexpected error while attempting Azure agent registration: {e}")
    
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


@app.get("/agents", response_model=List[AgentInfo])
async def list_agents():
    """List available agent types (static + optional Azure)."""
    agents = [
        AgentInfo(
            name="mock-ai",
            type="mock",
            description="Mock AI assistant for testing"
        ),
        AgentInfo(
            name="helpful", 
            type="mock",
            description="Helpful assistant with predefined responses"
        ),
        AgentInfo(
            name="echo", 
            type="test",
            description="Echo agent that repeats your messages"
        )
    ]
    if azure_agent_registered:
        agents.append(AgentInfo(
            name=azure_agent_name,
            type="azure-openai",
            description="Azure OpenAI chat agent (live model)"
        ))
    return agents


@app.post("/agents/{agent_name}/run", response_model=AgentRunResponse)
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
                "content": msg.content,
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
        
        # Convert response
        response_messages = []
        if response.data and "messages" in response.data:
            for msg_data in response.data["messages"]:
                response_messages.append(
                    ChatMessageModel(
                        role=msg_data["role"],
                        content=msg_data["content"],
                        message_id=msg_data["message_id"]
                    )
                )
        
        return AgentRunResponse(
            messages=response_messages,
            status=response.data.get("status", "completed") if response.data else "completed",
            conversation_id=conversation_id
        )
        
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