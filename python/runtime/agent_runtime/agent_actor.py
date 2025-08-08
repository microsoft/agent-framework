"""AgentActor - bridges AI agents with the actor runtime"""

import json
import logging
from typing import Optional, List

# Runtime infrastructure types
from .runtime_abstractions import (
    IActor, IActorRuntimeContext, ActorMessage, ActorRequestMessage, ActorResponseMessage,
    RequestStatus, ActorMessageType
)

# Framework agent types (use directly like .NET)
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../packages/main'))

from agent_framework import AIAgent, ChatMessage, AgentRunResponse, AgentThread, ChatRole, AgentBase

logger = logging.getLogger(__name__)


class AgentActor(IActor):
    """Runtime actor that wraps framework AI agents (direct integration like .NET)"""
    
    THREAD_STATE_KEY = "agent_thread"
    
    def __init__(self, agent: AIAgent):
        """Initialize with framework agent (direct usage, no adapter)"""
        self._agent = agent
        self._thread: Optional[AgentThread] = None
    
    async def run(self, context: IActorRuntimeContext) -> None:
        """Main actor execution loop"""
        agent_name = getattr(self._agent, 'name', None) or getattr(self._agent, 'id', 'unknown')
        logger.info(f"Agent actor started: {context.actor_id} (agent: {agent_name})")
        
        # Restore thread state
        await self._restore_thread_state(context)
        
        # Process messages
        async for message in context.watch_messages():
            if isinstance(message, ActorRequestMessage):
                await self._handle_agent_request(message, context)
    
    async def _restore_thread_state(self, context: IActorRuntimeContext):
        """Restore the agent thread state from storage"""
        thread_data = await context.read_state(self.THREAD_STATE_KEY)
        
        if thread_data:
            try:
                # For now, create new thread - full serialization would need framework support
                self._thread = self._agent.get_new_thread()
                logger.debug("Restored thread state (simplified)")
            except Exception as e:
                logger.error(f"Failed to restore thread state: {e}")
                self._thread = self._agent.get_new_thread()
        else:
            self._thread = self._agent.get_new_thread()
            logger.debug("Created new thread")
    
    async def _handle_agent_request(self, request: ActorRequestMessage, context: IActorRuntimeContext):
        """Handle agent run requests using framework types directly"""
        
        if request.method != "run":
            logger.warning(f"Unsupported method: {request.method}")
            await self._send_error_response(request, context, f"Unsupported method: {request.method}")
            return
        
        try:
            logger.info(f"Processing agent request: {request.message_id}")
            
            # Parse messages from request to framework types
            framework_messages = self._parse_framework_messages(request)
            
            # Call framework agent directly (like .NET does)
            response = await self._agent.run(framework_messages, thread=self._thread)
            
            # Save updated thread state
            await self._save_thread_state(context)
            
            # Convert framework response to runtime format
            response_data = self._convert_framework_response(response)
            
            # Send success response
            actor_response = ActorResponseMessage(
                message_id=request.message_id,
                message_type=ActorMessageType.RESPONSE,
                sender_id=context.actor_id,
                status=RequestStatus.COMPLETED,
                data=response_data
            )
            
            context.complete_request(request.message_id, actor_response)
            logger.info(f"Agent request completed: {request.message_id}")
            
        except Exception as e:
            logger.error(f"Agent request failed: {e}")
            await self._send_error_response(request, context, str(e))
    
    def _parse_framework_messages(self, request: ActorRequestMessage) -> List[ChatMessage]:
        """Convert runtime request to framework ChatMessage objects"""
        messages = []
        try:
            messages_data = request.params.get("messages", []) if request.params else []
            for msg_data in messages_data:
                # Create framework ChatMessage with proper role enum
                role = getattr(ChatRole, msg_data["role"].upper(), ChatRole.USER)
                framework_msg = ChatMessage(
                    role=role,
                    text=msg_data["content"]  # Framework uses 'text' not 'content'
                )
                messages.append(framework_msg)
        except Exception as e:
            logger.error(f"Error parsing framework messages: {e}")
        return messages
    
    def _convert_framework_response(self, framework_response: AgentRunResponse) -> dict:
        """Convert framework AgentRunResponse to runtime data format"""
        try:
            messages_data = []
            
            # Extract messages from framework response
            for framework_msg in framework_response.messages:
                msg_data = {
                    "role": self._extract_role(framework_msg),
                    "content": self._extract_content(framework_msg),
                    "message_id": getattr(framework_msg, 'message_id', None)
                }
                
                # Add timestamp if available
                if hasattr(framework_msg, 'timestamp'):
                    msg_data["timestamp"] = framework_msg.timestamp
                
                messages_data.append(msg_data)
            
            # Build response data
            response_data = {
                "messages": messages_data,
                "status": "completed"
            }
            
            # Add framework metadata if available
            if hasattr(framework_response, 'status'):
                response_data["status"] = framework_response.status
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error converting framework response: {e}")
            return {
                "messages": [{"role": "assistant", "content": f"Response conversion error: {e}"}],
                "status": "failed"
            }
    
    def _extract_role(self, framework_msg: ChatMessage) -> str:
        """Extract role from framework message"""
        try:
            role = framework_msg.role
            # Handle enum vs string
            return role.value if hasattr(role, 'value') else str(role)
        except Exception:
            return "assistant"
    
    def _extract_content(self, framework_msg: ChatMessage) -> str:
        """Extract text content from framework message"""
        try:
            # Framework messages use 'text' attribute primarily
            if hasattr(framework_msg, 'text'):
                return str(framework_msg.text)
            elif hasattr(framework_msg, 'content'):
                return str(framework_msg.content)
            else:
                return str(framework_msg)
        except Exception as e:
            logger.error(f"Error extracting content: {e}")
            return "[Content extraction error]"
    
    async def _save_thread_state(self, context: IActorRuntimeContext):
        """Save framework thread state to runtime storage"""
        try:
            if self._thread:
                # Simplified thread state saving - full implementation would serialize thread
                thread_data = {
                    "thread_id": getattr(self._thread, 'id', None),
                    "last_updated": str(context.actor_id)
                }
                await context.write_state(self.THREAD_STATE_KEY, thread_data)
                logger.debug("Saved thread state (simplified)")
        except Exception as e:
            logger.error(f"Error saving thread state: {e}")
    
    async def _send_error_response(self, request: ActorRequestMessage, context: IActorRuntimeContext, error_msg: str):
        """Send error response"""
        error_response = ActorResponseMessage(
            message_id=request.message_id,
            message_type=ActorMessageType.RESPONSE,
            sender_id=context.actor_id,
            status=RequestStatus.FAILED,
            data={"error": error_msg}
        )
        context.complete_request(request.message_id, error_response)


# Mock agent implementations for testing (like .NET has MockAgent)
class MockAIAgent(AgentBase):
    """Mock AI agent that simulates different responses (for testing like .NET MockAgent)"""
    
    def __init__(self, name: str = "mock", responses: Optional[List[str]] = None, **kwargs):
        super().__init__(name=name, **kwargs)
        self._responses = responses or [
            "Hello! How can I help you today?",
            "That's an interesting question!",
            "I understand what you're asking.",
            "Let me think about that...",
            "Here's what I think:"
        ]
        self._response_index = 0
    
    def get_new_thread(self) -> AgentThread:
        """Create a new conversation thread"""
        # This would normally be implemented by the framework
        # For now, return a simple object
        return type('AgentThread', (), {'messages': []})()
    
    async def run(
        self, 
        messages: List[ChatMessage] = None, 
        *, 
        thread: Optional[AgentThread] = None, 
        **kwargs
    ) -> AgentRunResponse:
        """Provide mock responses"""
        import asyncio
        
        if thread is None:
            thread = self.get_new_thread()
        
        # Add incoming messages to thread
        if messages:
            for message in messages:
                thread.messages.append(message)
        
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        # Generate response
        response_text = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1
        
        response_message = ChatMessage(
            role=ChatRole.ASSISTANT,
            text=response_text
        )
        thread.messages.append(response_message)
        
        return AgentRunResponse(
            messages=[response_message]
        )


class EchoAgent(AgentBase):
    """Echo agent for testing (like .NET test agents)"""
    
    def __init__(self, name: str = "echo", **kwargs):
        super().__init__(name=name, **kwargs)
    
    def get_new_thread(self) -> AgentThread:
        """Create a new conversation thread"""
        return type('AgentThread', (), {'messages': []})()
    
    async def run(
        self, 
        messages: List[ChatMessage] = None, 
        *, 
        thread: Optional[AgentThread] = None, 
        **kwargs
    ) -> AgentRunResponse:
        """Echo back the user's messages"""
        if thread is None:
            thread = self.get_new_thread()
        
        # Add incoming messages to thread
        if messages:
            for message in messages:
                thread.messages.append(message)
            
            # Get the last user message
            last_message = messages[-1]
            echo_content = f"Echo: {last_message.text}"
        else:
            echo_content = "Echo: (no message)"
        
        # Create response message
        response_message = ChatMessage(
            role=ChatRole.ASSISTANT,
            text=echo_content
        )
        
        # Add to thread
        thread.messages.append(response_message)
        
        return AgentRunResponse(
            messages=[response_message]
        )