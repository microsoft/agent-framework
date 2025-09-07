# Copyright (c) Microsoft. All rights reserved.

"""Workflow processing utilities for Agent Framework DevUI."""

import inspect
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent_framework.workflow import Workflow

logger = logging.getLogger(__name__)


def extract_workflow_input_info(workflow: 'Workflow') -> Dict[str, Any]:
    """Extract input schema and metadata from a workflow."""
    try:
        start_executor = workflow.get_start_executor()
        start_executor_id = start_executor.id
        
        # Use the framework's pre-extracted message types from handler registration
        # This is more reliable than manual signature inspection
        if not start_executor._handlers:
            raise ValueError(f"Start executor {start_executor_id} has no handlers")
        
        message_types = list(start_executor._handlers.keys())
        if not message_types:
            raise ValueError(f"Start executor {start_executor_id} has no registered message types")
        
        # For start executors, typically there's one main input type
        # If multiple, we take the first one (could be enhanced to pick most specific)
        input_type = message_types[0]
        
        # Generate schema and type name
        input_type_name = get_type_name(input_type)
        input_schema = generate_schema(input_type)
        
        # If it's a basic type (not Pydantic), try to extract parameter names from handler function
        if input_schema.get("type") in ["string", "integer", "number", "boolean", "array"] and "properties" not in input_schema:
            enhanced_schema = _enhance_schema_with_function_signature(start_executor, input_type, input_schema)
            if enhanced_schema:
                input_schema = enhanced_schema
        
        return {
            "input_schema": input_schema,
            "input_type_name": input_type_name,
            "start_executor_id": start_executor_id,
        }
        
    except Exception as e:
        logger.error(f"Error extracting input info from workflow: {e}")
        # Return fallback info
        return {
            "input_schema": {"type": "object", "description": "Unknown input type"},
            "input_type_name": "unknown",
            "start_executor_id": getattr(workflow, 'start_executor_id', 'unknown'),
        }


def get_type_name(type_annotation: Any) -> str:
    """Get a human-readable name for a type annotation."""
    if hasattr(type_annotation, '__name__'):
        return type_annotation.__name__
    elif hasattr(type_annotation, '_name'):
        return type_annotation._name
    else:
        return str(type_annotation)


def generate_schema(type_annotation: Any) -> Dict[str, Any]:
    """Generate JSON Schema for a type annotation."""
    
    # Handle Pydantic models
    if hasattr(type_annotation, 'model_json_schema'):
        try:
            return type_annotation.model_json_schema()
        except Exception:
            pass
    
    # Handle basic Python types
    if type_annotation == str:
        return {"type": "string"}
    elif type_annotation == int:
        return {"type": "integer"}
    elif type_annotation == float:
        return {"type": "number"}
    elif type_annotation == bool:
        return {"type": "boolean"}
    elif type_annotation == list:
        return {"type": "array"}
    elif type_annotation == dict:
        return {"type": "object"}
    
    # Fallback for complex or unknown types
    return {
        "type": "object",
        "description": f"Complex type: {get_type_name(type_annotation)}"
    }


def generate_mermaid_diagram(workflow: 'Workflow') -> Optional[str]:
    """Generate mermaid diagram for workflow."""
    try:
        from agent_framework_workflow._viz import WorkflowViz
        viz = WorkflowViz(workflow)
        return viz.to_mermaid()
    except Exception as e:
        logger.debug(f"Could not generate mermaid diagram: {e}")
        return None


def extract_workflow_executors(workflow: 'Workflow') -> List[str]:
    """Extract executor names from a workflow."""
    executors = []
    
    try:
        if hasattr(workflow, 'get_executors_list'):
            executor_objects = workflow.get_executors_list()
            executors = [getattr(ex, 'id', str(ex)) for ex in executor_objects]
    except Exception as e:
        logger.debug(f"Error extracting executors from workflow {type(workflow)}: {e}")
        executors = []
            
    return executors

# Keep old function for backwards compatibility
def extract_workflow_tools(workflow: 'Workflow') -> List[str]:
    """Extract executor names from a workflow (deprecated - use extract_workflow_executors)."""
    return extract_workflow_executors(workflow)


def extract_agent_tools(agent: Any) -> List[str]:
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


def _enhance_schema_with_function_signature(executor: Any, input_type: Any, base_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Enhance basic type schema with parameter names from handler function signature."""
    try:
        # Find the handler method for this input type
        handler_func = None
        if hasattr(executor, '_handlers') and input_type in executor._handlers:
            handler_info = executor._handlers[input_type]
            # The handler info should contain the actual function reference
            if hasattr(handler_info, 'func'):
                handler_func = handler_info.func
            elif callable(handler_info):
                handler_func = handler_info
        
        # If we can't find the handler function, try to find any handler method
        if handler_func is None:
            # Look for methods decorated with @handler
            for attr_name in dir(executor):
                if attr_name.startswith('_'):
                    continue
                attr = getattr(executor, attr_name)
                if callable(attr) and hasattr(attr, '__annotations__'):
                    # Check if this method handles our input type
                    sig = inspect.signature(attr)
                    for param_name, param in sig.parameters.items():
                        if param_name in ['self', 'ctx']:  # Skip self and context parameters
                            continue
                        if param.annotation == input_type:
                            handler_func = attr
                            break
                    if handler_func:
                        break
        
        if handler_func is None:
            return None
            
        # Extract parameter information from the function signature
        sig = inspect.signature(handler_func)
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            # Skip self and context parameters
            if param_name in ['self', 'ctx'] or 'context' in param_name.lower():
                continue
                
            # Only process parameters that match our input type
            if param.annotation == input_type:
                # Create property schema for this parameter
                param_schema = dict(base_schema)  # Copy the base schema
                
                # Add description if available from docstring or annotation
                if hasattr(param, 'description'):
                    param_schema['description'] = param.description
                elif handler_func.__doc__:
                    # Try to extract parameter description from docstring
                    # This is a simple heuristic - could be enhanced with proper docstring parsing
                    doc_lines = handler_func.__doc__.strip().split('\n')
                    for line in doc_lines:
                        if param_name.lower() in line.lower():
                            param_schema['description'] = line.strip()
                            break
                
                properties[param_name] = param_schema
                
                # Check if parameter has default value
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                else:
                    param_schema['default'] = param.default
        
        # If we found parameter names, create an object schema
        if properties:
            return {
                "type": "object",
                "properties": properties,
                "required": required
            }
            
    except Exception as e:
        logger.debug(f"Could not enhance schema with function signature: {e}")
        
    return None