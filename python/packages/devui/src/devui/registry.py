# Copyright (c) Microsoft. All rights reserved.

"""Agent registry supporting both directory-based and in-memory agents."""

import inspect
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework import AgentProtocol
    from agent_framework.workflow import Workflow
    from .discovery import DirectoryScanner

from .models import AgentInfo, WorkflowInfo
from .utils.workflow import (
    extract_workflow_input_info,
    generate_mermaid_diagram,
    extract_workflow_executors,
    extract_agent_tools
)

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
                tools=extract_agent_tools(agent),
                has_env=False,
                module_path=None
            )
            agents.append(info)
            
        return agents
    
    def list_workflows(self) -> List[WorkflowInfo]:
        """Return list of all workflows with metadata."""
        workflows: List[WorkflowInfo] = []
        
        # Add directory-discovered workflows
        if self.directory_scanner:
            try:
                directory_items = self.directory_scanner.discover_agents()
                # Filter to only workflows and convert to WorkflowInfo
                for item in directory_items:
                    if item.type == "workflow":
                        # Check if item is already a WorkflowInfo object
                        if isinstance(item, WorkflowInfo):
                            workflows.append(item)
                        else:
                            # Get the actual workflow object to extract input info
                            workflow_obj = self.get_workflow(item.id)
                            if workflow_obj:
                                input_info = extract_workflow_input_info(workflow_obj)
                                # Use executors instead of tools for WorkflowInfo
                                executors = getattr(item, 'executors', getattr(item, 'tools', []))
                                workflow_info = WorkflowInfo(
                                    id=item.id,
                                    name=item.name,
                                    description=item.description,
                                    source="directory",
                                    executors=executors,
                                    has_env=item.has_env,
                                    module_path=item.module_path,
                                    workflow_dump=workflow_obj.model_dump(),
                                    mermaid_diagram=generate_mermaid_diagram(workflow_obj),
                                    input_schema=input_info["input_schema"],
                                    input_type_name=input_info["input_type_name"],
                                    start_executor_id=input_info["start_executor_id"]
                                )
                                workflows.append(workflow_info)
            except Exception as e:
                logger.error(f"Error discovering directory workflows: {e}")
        
        # Add in-memory workflows
        for workflow_id, workflow in self.workflows.items():
            try:
                input_info = extract_workflow_input_info(workflow)
                info = WorkflowInfo(
                    id=workflow_id,
                    name=getattr(workflow, 'name', None),
                    description=getattr(workflow, 'description', None),
                    source="in_memory",
                    executors=extract_workflow_executors(workflow),
                    has_env=False,
                    module_path=None,
                    workflow_dump=workflow.model_dump(),
                    mermaid_diagram=generate_mermaid_diagram(workflow),
                    input_schema=input_info["input_schema"],
                    input_type_name=input_info["input_type_name"],
                    start_executor_id=input_info["start_executor_id"]
                )
                workflows.append(info)
            except Exception as e:
                logger.error(f"Error processing workflow {workflow_id}: {e}")
            
        return workflows
    
    def list_all_items(self) -> List[AgentInfo]:
        """Return list of agents only. Use list_workflows() for workflows."""
        return self.list_agents()
    
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
        
