# Copyright (c) Microsoft. All rights reserved.

"""Directory-based agent discovery for Agent Framework."""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from agent_framework import AgentProtocol
    from agent_framework.workflow import Workflow

from .models import AgentInfo

logger = logging.getLogger(__name__)

class DirectoryScanner:
    """Scans filesystem for agents following Agent Framework conventions.
    
    Discovers agents and workflows from standardized directory structures,
    similar to ADK's discovery mechanism but adapted for Agent Framework.
    """
    
    def __init__(self, agents_dir: str) -> None:
        """Initialize scanner with agents directory."""
        self.agents_dir = Path(agents_dir).resolve()
        self._agent_cache: Dict[str, Any] = {}
        
    def discover_agents(self) -> List[AgentInfo]:
        """Discover all agents and workflows in the agents directory."""
        if not self.agents_dir.exists():
            logger.warning(f"Agents directory does not exist: {self.agents_dir}")
            return []
            
        discovered: List[AgentInfo] = []
        
        # Scan all subdirectories
        for item in self.agents_dir.iterdir():
            if not item.is_dir() or item.name.startswith('.') or item.name == '__pycache__':
                continue
                
            agent_id = item.name
            logger.debug(f"Scanning directory: {agent_id}")
            
            try:
                # Load the module and extract info
                module = self._load_agent_module(item)
                if module is None:
                    logger.debug(f"No valid module found for {agent_id}")
                    continue
                    
                agent_info = self._extract_agent_info(module, agent_id, str(item))
                if agent_info:
                    discovered.append(agent_info)
                    # Cache the module for later use
                    self._agent_cache[agent_id] = module
                else:
                    logger.debug(f"No valid agent or workflow found in {agent_id}")
                    
            except Exception as e:
                logger.warning(f"Error scanning {agent_id}: {e}")
                continue
                
        logger.debug(f"Discovered {len(discovered)} agents/workflows from directory")
        return discovered
    
    def get_agent_object(self, agent_id: str) -> Optional[Any]:
        """Get the actual agent/workflow object for execution."""
        if agent_id in self._agent_cache:
            module = self._agent_cache[agent_id]
            return self._find_agent_in_module(module)
            
        # Try to load fresh if not in cache
        agent_path = self.agents_dir / agent_id
        if agent_path.exists():
            module = self._load_agent_module(agent_path)
            if module:
                self._agent_cache[agent_id] = module
                return self._find_agent_in_module(module)
                
        return None
    
    def clear_cache(self) -> None:
        """Clear the agent cache for hot reloading."""
        # Remove from sys.modules
        for agent_id in list(self._agent_cache.keys()):
            patterns = [agent_id, f"{agent_id}.agent", f"{agent_id}.workflow"]
            for pattern in patterns:
                if pattern in sys.modules:
                    del sys.modules[pattern]
                    logger.debug(f"Removed {pattern} from sys.modules")
                    
        self._agent_cache.clear()
        logger.info("Cleared directory agent cache")
    
    def _load_env_for_agent(self, agent_path: Path) -> bool:
        """Load .env file for an agent, walking up directory tree."""
        env_file = agent_path / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
            logger.debug(f"Loaded .env for agent at {env_file}")
            return True
            
        # Walk up to project root looking for .env
        parent = agent_path.parent
        while parent != parent.parent:  # Until we hit filesystem root
            env_file = parent / ".env"
            if env_file.exists():
                load_dotenv(env_file, override=True)
                logger.debug(f"Loaded .env for agent from {env_file}")
                return True
            parent = parent.parent
        
        return False
    
    def _load_agent_module(self, agent_path: Path) -> Optional[Any]:
        """Load Python module for an agent directory."""
        if not agent_path.is_dir():
            return None
            
        # Add agents directory to path if not already there
        if str(self.agents_dir) not in sys.path:
            sys.path.insert(0, str(self.agents_dir))
            
        agent_id = agent_path.name
        
        # Load environment first
        self._load_env_for_agent(agent_path)
        
        # Try different import patterns following Agent Framework conventions
        import_patterns = [
            agent_id,                    # Direct module import
            f"{agent_id}.agent",         # agent.py submodule
            f"{agent_id}.workflow",      # workflow.py submodule  
        ]
        
        # Try all patterns and find the first one with actual agent/workflow objects
        for pattern in import_patterns:
            try:
                # Check if module exists first
                spec = importlib.util.find_spec(pattern)
                if spec is None:
                    continue
                    
                module = importlib.import_module(pattern)
                logger.debug(f"Successfully imported {pattern} for {agent_id}")
                
                # Check if this module has agent/workflow objects
                if self._find_agent_in_module(module) is not None:
                    logger.debug(f"Found agent/workflow object in {pattern}")
                    return module
                else:
                    logger.debug(f"No agent/workflow object found in {pattern}")
                
            except ModuleNotFoundError:
                logger.debug(f"Import pattern {pattern} not found")
                continue
            except Exception as e:
                logger.warning(f"Error importing {pattern}: {e}")
                continue
                
        return None
    
    def _find_agent_in_module(self, module: Any) -> Optional[Any]:
        """Find the agent or workflow object in a loaded module."""
        # Import here to avoid circular imports
        try:
            from agent_framework import AgentProtocol
        except ImportError:
            AgentProtocol = None
        
        # Look for explicit variable names
        candidates = [
            ('agent', getattr(module, 'agent', None)),
            ('workflow', getattr(module, 'workflow', None)),
        ]
        
        for obj_type, obj in candidates:
            if obj is None:
                continue
                
            # Use proper type checking
            if obj_type == 'agent':
                # Check if it's an Agent Framework agent using isinstance if available
                if AgentProtocol and hasattr(AgentProtocol, '__instancecheck__'):
                    try:
                        if isinstance(obj, AgentProtocol):
                            return obj
                    except (TypeError, AttributeError):
                        pass
                # Fallback to duck typing for agent protocol
                if hasattr(obj, 'run_stream') and hasattr(obj, 'id') and hasattr(obj, 'name'):
                    return obj
                    
            elif obj_type == 'workflow':
                # Check for workflow - must have run_stream method  
                if hasattr(obj, 'run_stream'):
                    return obj
        
        return None
    
    def _extract_agent_info(self, module: Any, agent_id: str, module_path: str) -> Optional[AgentInfo]:
        """Extract metadata from a loaded module."""
        obj = self._find_agent_in_module(module)
        if not obj:
            return None
            
        # Determine type
        obj_type = "workflow" if hasattr(obj, 'executors') else "agent"
        
        # Extract tools/executors
        tools = self._extract_tools_from_object(obj, obj_type)
        
        return AgentInfo(
            id=agent_id,
            name=getattr(obj, 'name', None),
            description=getattr(obj, 'description', None),
            type=obj_type,
            source="directory",
            tools=tools,
            has_env=(Path(module_path) / ".env").exists(),
            module_path=module_path
        )
    
    def _extract_tools_from_object(self, obj: Any, obj_type: str) -> List[str]:
        """Extract tool names from an agent or workflow."""
        tools = []
        
        if obj_type == "agent":
            # For agents, try to find tools in chat_options or direct tools attribute
            agent_tools = None
            if hasattr(obj, 'chat_options') and hasattr(obj.chat_options, 'tools'):
                agent_tools = obj.chat_options.tools
            elif hasattr(obj, 'tools'):
                agent_tools = obj.tools
                
            if agent_tools:
                for tool in agent_tools:
                    if hasattr(tool, '__name__'):
                        tools.append(tool.__name__)
                    elif hasattr(tool, 'name'):
                        tools.append(tool.name)
                    else:
                        tools.append(str(tool))
                        
        elif obj_type == "workflow":
            # For workflows, try to list executors
            if hasattr(obj, 'get_executors'):
                try:
                    executors = obj.get_executors()
                    tools = [getattr(ex, 'id', str(ex)) for ex in executors]
                except Exception as e:
                    logger.debug(f"Could not extract executors: {e}")
                    tools = []
                    
        return tools