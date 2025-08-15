"""
Web Chat Agent Host

This is the sample-specific agent host that configures and exposes agents for the web chat sample.
It mirrors the .NET AgentWebChat.AgentHost project structure.

This host:
1. Configures the agents needed by this sample
2. Starts the HTTP API runtime
3. Exposes agent discovery and execution endpoints
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

# Add runtime to path
runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if runtime_path not in sys.path:
    sys.path.append(runtime_path)

from agent_runtime.runtime import InProcessActorRuntime, InProcessActorClient
from agent_runtime.agent_actor import AgentActor, ActorId

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    print("FastAPI and Pydantic are required. Install with: pip install fastapi pydantic uvicorn")
    raise

logger = logging.getLogger(__name__)


# Request/Response models (reused from http_api)
class ChatMessageModel(BaseModel):
    role: str
    text: Optional[str] = None
    content: Optional[str] = None
    message_id: Optional[str] = None


class AgentRunRequest(BaseModel):
    agent_name: str
    conversation_id: Optional[str] = None
    messages: List[ChatMessageModel]


class AgentInfo(BaseModel):
    name: str
    type: str
    description: str


# Global runtime instance
runtime: InProcessActorRuntime = None
client: InProcessActorClient = None


def configure_agents():
    """Configure agents for the web chat sample - like .NET AgentHost Program.cs"""
    global runtime
    
    if not runtime:
        return
    
    # Register Azure agents if configured
    _register_azure_agents_if_configured()
    
    logger.info("Configured agents for web chat sample")


def _load_env_files():
    """Load .env files for configuration"""
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
                break
            except Exception as e:
                logger.warning("Failed loading %s: %s", f, e)


def _register_azure_agents_if_configured():
    """Register Azure agents if environment variables are present"""
    _load_env_files()
    
    # Check for Azure environment variables
    required_key = os.environ.get("AZURE_OPENAI_API_KEY")
    required_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("AZURE_OPENAI_BASE_URL")
    
    if required_key and required_deployment and endpoint:
        try:
            # Add packages to path
            packages_root = Path(__file__).resolve().parents[2] / "packages"
            main_pkg = packages_root / "main"
            azure_pkg = packages_root / "azure"
            for p in (main_pkg, azure_pkg):
                p_str = str(p)
                if p_str not in sys.path:
                    sys.path.append(p_str)
            
            from agent_framework_azure._chat_client import AzureChatClient  # type: ignore
            
            api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
            
            def pirate_agent_factory(actor_id):
                chat_client = AzureChatClient(
                    api_key=required_key,
                    deployment_name=required_deployment,
                    endpoint=endpoint,
                    api_version=api_version,
                )
                agent = chat_client.create_agent(
                    name="Pirate Assistant",
                    instructions=(
                        "You are a helpful AI assistant powered by Azure OpenAI. "
                        "Adopt a light, friendly pirate persona: sprinkle in mild pirate slang like 'Ahoy', 'aye', and 'matey'. "
                        "Stay concise, professional, and easy to read; avoid heavy dialect, excessive 'Arrr', or altering technical terms. "
                        "If giving code or structured data, present it normally (no pirate modifications inside code)."
                    )
                )
                return AgentActor(agent)
            
            def travel_agent_factory(actor_id):
                chat_client = AzureChatClient(
                    api_key=required_key,
                    deployment_name=required_deployment,
                    endpoint=endpoint,
                    api_version=api_version,
                )
                agent = chat_client.create_agent(
                    name="Travel Assistant",
                    instructions=(
                        "You are a knowledgeable and enthusiastic travel assistant powered by Azure OpenAI. "
                        "Help users plan trips, find destinations, suggest activities, and provide travel advice. "
                        "Be warm, encouraging, and share interesting facts about places. "
                        "Always consider practical aspects like budget, time, and accessibility when making recommendations."
                    )
                )
                return AgentActor(agent)
            
            runtime.register_actor_type("pirate", pirate_agent_factory)
            runtime.register_actor_type("travel", travel_agent_factory)
            logger.info("Registered Azure OpenAI agents: pirate and travel")
            
        except ImportError as e:
            logger.warning(f"Azure agent not registered (import failure): {e}")
        except Exception as e:
            logger.error(f"Failed to register Azure agent: {e}")
    else:
        missing = []
        if not required_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not required_deployment:
            missing.append("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        if not endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_BASE_URL")
        logger.info("Azure agent not registered; missing env vars: %s", ", ".join(missing))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the agent host lifecycle"""
    global runtime, client
    
    # Startup
    logger.info("Starting web chat agent host...")
    runtime = InProcessActorRuntime()
    client = InProcessActorClient(runtime)
    
    # Configure agents for this sample
    configure_agents()
    
    await runtime.start()
    logger.info("Web chat agent host started")
    
    yield
    
    # Shutdown
    if runtime:
        logger.info("Stopping web chat agent host...")
        await runtime.stop()
        logger.info("Web chat agent host stopped")


# Create FastAPI app for this sample's agent host
app = FastAPI(
    title="Web Chat Agent Host API",
    description="Agent host for the Python web chat sample",
    version="0.1.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "message": "Web Chat Agent Host API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/agents", response_model=List[AgentInfo])
async def list_agents():
    """List available agents configured by this sample"""
    if not runtime:
        return []
    
    # Get registered agent types from runtime
    agent_factories = getattr(runtime, '_actor_factories', {})
    agents = []
    
    for name in agent_factories.keys():
        if name == "pirate":
            agents.append(AgentInfo(name="pirate", type="azure-openai", description="Friendly pirate assistant with Azure OpenAI"))
        elif name == "travel":
            agents.append(AgentInfo(name="travel", type="azure-openai", description="Knowledgeable travel planning assistant with Azure OpenAI"))
        else:
            agents.append(AgentInfo(name=name, type="unknown", description=f"Agent: {name}"))
    
    return agents


@app.post("/agents/{agent_name}/run")
async def run_agent(agent_name: str, request: AgentRunRequest):
    """Run an agent with the provided messages"""
    
    if not runtime or not client:
        raise HTTPException(status_code=503, detail="Agent host not available")
    
    try:
        # Create actor ID
        conversation_id = request.conversation_id or f"webchat-{agent_name}"
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
        
        # Return the response data
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
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🚀 Starting Web Chat Agent Host")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("🔍 Agents endpoint: http://localhost:8000/agents")
    
    uvicorn.run(
        "agent_host:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=False
    )