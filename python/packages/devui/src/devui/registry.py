# Copyright (c) Microsoft. All rights reserved.

"""Agent registry supporting both directory-based and in-memory agents."""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework import AgentProtocol
    from agent_framework.workflow import Workflow
    from .discovery import DirectoryScanner

from .models import AgentInfo

logger = logging.getLogger(__name__)

class AgentRegistry:
    """Type-safe registry with separate agent and workflow collections.
    
    Supports both directory-scanned and in-memory registered items
    with clean type separation.
    """
    
    def __init__(self, agents_dir: Optional[str] = None) -> None:
        """Initialize the registry with optional directory scanner."""
        self.directory_scanner: Optional['DirectoryScanner'] = None
        self.agents: Dict[str, 'AgentProtocol'] = {}
        self.workflows: Dict[str, 'Workflow'] = {}
        
        if agents_dir:
            # Lazy import to avoid circular dependencies
            from .discovery import DirectoryScanner
            self.directory_scanner = DirectoryScanner(agents_dir)
    
    def register_agent(self, agent_id: str, agent: 'AgentProtocol') -> None:
        """Register an in-memory agent with type validation."""
        # Import here to avoid circular dependencies
        from agent_framework import AgentProtocol
        
        if not isinstance(agent, AgentProtocol):
            raise TypeError(f"Expected AgentProtocol, got {type(agent)}")
            
        self.agents[agent_id] = agent
        logger.info(f"Registered in-memory agent: {agent_id}")
    
    def register_workflow(self, workflow_id: str, workflow: 'Workflow') -> None:
        """Register an in-memory workflow with type validation."""
        # Import here to avoid circular dependencies  
        from agent_framework.workflow import Workflow
        
        if not isinstance(workflow, Workflow):
            raise TypeError(f"Expected Workflow, got {type(workflow)}")
            
        self.workflows[workflow_id] = workflow
        logger.info(f"Registered in-memory workflow: {workflow_id}")
    
    def get_agent(self, agent_id: str) -> Optional['AgentProtocol']:
        """Get agent by ID from either in-memory or directory source."""
        # Check in-memory first (faster)
        if agent_id in self.agents:
            return self.agents[agent_id]
            
        # Check directory-based
        if self.directory_scanner:
            try:
                item = self.directory_scanner.get_agent_object(agent_id)
                # Verify it's actually an agent
                if item:
                    from agent_framework import AgentProtocol
                    if isinstance(item, AgentProtocol):
                        return item
            except Exception as e:
                logger.error(f"Error loading directory agent {agent_id}: {e}")
                
        return None
    
    def get_workflow(self, workflow_id: str) -> Optional['Workflow']:
        """Get workflow by ID from either in-memory or directory source."""
        # Check in-memory first (faster)
        if workflow_id in self.workflows:
            return self.workflows[workflow_id]
            
        # Check directory-based
        if self.directory_scanner:
            try:
                item = self.directory_scanner.get_agent_object(workflow_id)
                # Verify it's actually a workflow
                if item:
                    from agent_framework.workflow import Workflow
                    if isinstance(item, Workflow):
                        return item
            except Exception as e:
                logger.error(f"Error loading directory workflow {workflow_id}: {e}")
                
        return None
    
    def list_agents(self) -> List[AgentInfo]:
        """Return list of all agents with metadata."""
        agents: List[AgentInfo] = []
        
        # Add directory-discovered agents
        if self.directory_scanner:
            try:
                directory_items = self.directory_scanner.discover_agents()
                # Filter to only agents
                for item in directory_items:
                    if item.type == "agent":
                        agents.append(item)
            except Exception as e:
                logger.error(f"Error discovering directory agents: {e}")
        
        # Add in-memory agents
        for agent_id, agent in self.agents.items():
            info = AgentInfo(
                id=agent_id,
                name=getattr(agent, 'name', None),
                description=getattr(agent, 'description', None),
                type="agent",
                source="in_memory",
                tools=self._extract_agent_tools(agent),
                has_env=False,
                module_path=None
            )
            agents.append(info)
            
        return agents
    
    def list_workflows(self) -> List[AgentInfo]:
        """Return list of all workflows with metadata."""
        workflows: List[AgentInfo] = []
        
        # Add directory-discovered workflows
        if self.directory_scanner:
            try:
                directory_items = self.directory_scanner.discover_agents()
                # Filter to only workflows
                for item in directory_items:
                    if item.type == "workflow":
                        workflows.append(item)
            except Exception as e:
                logger.error(f"Error discovering directory workflows: {e}")
        
        # Add in-memory workflows
        for workflow_id, workflow in self.workflows.items():
            info = AgentInfo(
                id=workflow_id,
                name=getattr(workflow, 'name', None),
                description=getattr(workflow, 'description', None),
                type="workflow",
                source="in_memory",
                tools=self._extract_workflow_tools(workflow),
                has_env=False,
                module_path=None
            )
            workflows.append(info)
            
        return workflows
    
    def list_all_items(self) -> List[AgentInfo]:
        """Return combined list of agents and workflows."""
        return self.list_agents() + self.list_workflows()
    
    def remove_agent(self, agent_id: str) -> bool:
        """Remove an in-memory agent."""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"Removed in-memory agent: {agent_id}")
            return True
        return False
    
    def remove_workflow(self, workflow_id: str) -> bool:
        """Remove an in-memory workflow."""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            logger.info(f"Removed in-memory workflow: {workflow_id}")
            return True
        return False
        
    def clear_cache(self) -> None:
        """Clear caches for hot reloading."""
        if self.directory_scanner:
            self.directory_scanner.clear_cache()
        
    def _extract_agent_tools(self, agent: 'AgentProtocol') -> List[str]:
        """Extract tool names from an agent."""
        tools = []
        
        try:
            # For agents, check chat_options.tools first
            chat_options = getattr(agent, 'chat_options', None)
            if chat_options and hasattr(chat_options, 'tools'):
                for tool in chat_options.tools:
                    if hasattr(tool, '__name__'):
                        tools.append(tool.__name__)
                    elif hasattr(tool, 'name'):
                        tools.append(tool.name)
                    else:
                        tools.append(str(tool))
            else:
                # Fallback to direct tools attribute
                agent_tools = getattr(agent, 'tools', None)
                if agent_tools:
                    for tool in agent_tools:
                        if hasattr(tool, '__name__'):
                            tools.append(tool.__name__)
                        elif hasattr(tool, 'name'):
                            tools.append(tool.name)
                        else:
                            tools.append(str(tool))
                            
        except Exception as e:
            logger.debug(f"Error extracting tools from agent {type(agent)}: {e}")
            tools = []
                
        return tools
    
    def _extract_workflow_tools(self, workflow: 'Workflow') -> List[str]:
        """Extract executor names from a workflow."""
        tools = []
        
        try:
            if hasattr(workflow, 'get_executors_list'):
                executors = workflow.get_executors_list()
                tools = [getattr(ex, 'id', str(ex)) for ex in executors]
        except Exception as e:
            logger.debug(f"Error extracting tools from workflow {type(workflow)}: {e}")
            tools = []
                
        return tools