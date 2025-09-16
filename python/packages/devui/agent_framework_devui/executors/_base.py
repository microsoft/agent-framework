# Copyright (c) Microsoft. All rights reserved.

"""Base classes for framework-specific entity discovery, execution, and message mapping."""

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ..models import AgentFrameworkRequest, OpenAIResponse, ResponseStreamEvent
from ..models._discovery_models import EntityInfo

logger = logging.getLogger(__name__)


# ============================================================================
# ENTITY DISCOVERY BASE CLASS
# ============================================================================


class EntityDiscovery(ABC):
    """Base class for framework-specific entity discovery."""

    def __init__(self, framework_name: str, entities_dir: str | None = None):
        """Initialize entity discovery.

        Args:
            framework_name: Name of the framework this discovery handles
            entities_dir: Directory to scan for entities (optional)
        """
        self.framework_name = framework_name
        self.entities_dir = entities_dir
        self._entities: dict[str, EntityInfo] = {}
        self._loaded_objects: dict[str, Any] = {}

    @abstractmethod
    async def discover_entities(self) -> list[EntityInfo]:
        """Framework-specific entity discovery logic.

        Returns:
            List of discovered entities
        """
        ...

    def get_entity_info(self, entity_id: str) -> EntityInfo | None:
        """Get entity metadata.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity information or None if not found
        """
        return self._entities.get(entity_id)

    def get_entity_object(self, entity_id: str) -> Any | None:
        """Get the actual loaded entity object.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity object or None if not found
        """
        return self._loaded_objects.get(entity_id)

    def list_entities(self) -> list[EntityInfo]:
        """List all discovered entities.

        Returns:
            List of all entity information
        """
        return list(self._entities.values())

    def register_entity(self, entity_id: str, entity_info: EntityInfo, entity_object: Any) -> None:
        """Register an entity with both metadata and object.

        Args:
            entity_id: Unique entity identifier
            entity_info: Entity metadata
            entity_object: Actual entity object for execution
        """
        self._entities[entity_id] = entity_info
        self._loaded_objects[entity_id] = entity_object
        logger.debug(f"Registered entity: {entity_id} ({entity_info.type})")

    def _load_env_file(self, env_path: Path) -> bool:
        """Load environment variables from .env file.

        Args:
            env_path: Path to .env file

        Returns:
            True if file was loaded successfully
        """
        if env_path.exists():
            load_dotenv(env_path, override=True)
            logger.debug(f"Loaded .env from {env_path}")
            return True
        return False

    def _generate_entity_id(self, entity: Any, entity_type: str) -> str:
        """Generate entity ID with priority: name -> id -> class_name -> uuid.

        Args:
            entity: Entity object
            entity_type: Type of entity (agent, workflow, etc.)

        Returns:
            Generated entity ID
        """
        import re
        import uuid

        # Priority 1: entity.name
        if hasattr(entity, "name") and entity.name:
            name = str(entity.name).lower().replace(" ", "-").replace("_", "-")
            return f"{entity_type}_{name}"

        # Priority 2: entity.id
        if hasattr(entity, "id") and entity.id:
            entity_id = str(entity.id).lower().replace(" ", "-").replace("_", "-")
            return f"{entity_type}_{entity_id}"

        # Priority 3: class name
        if hasattr(entity, "__class__"):
            class_name = entity.__class__.__name__
            # Convert CamelCase to kebab-case
            class_name = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", class_name).lower()
            return f"{entity_type}_{class_name}"

        # Priority 4: fallback to uuid
        return f"{entity_type}_{uuid.uuid4().hex[:8]}"

    async def create_entity_info_from_object(self, entity_object: Any, entity_type: str | None = None) -> EntityInfo:
        """Create EntityInfo from a raw entity object.

        Base implementation with generic introspection. Framework-specific
        subclasses can override for custom logic.

        Args:
            entity_object: Raw entity object to introspect
            entity_type: Optional entity type override

        Returns:
            EntityInfo extracted from object
        """
        # Determine entity type if not provided
        if entity_type is None:
            entity_type = "agent"
            # Basic workflow detection
            if hasattr(entity_object, "get_executors_list") or hasattr(entity_object, "executors"):
                entity_type = "workflow"

        # Extract basic metadata
        name = getattr(entity_object, "name", "unknown")
        description = getattr(entity_object, "description", "")

        # Generate entity ID
        entity_id = self._generate_entity_id(entity_object, entity_type)

        # Create basic EntityInfo
        return EntityInfo(
            id=entity_id,
            name=name,
            description=description,
            type=entity_type,
            framework=self.framework_name,
            tools=[],  # Base implementation provides empty tools list
            metadata={
                "source": "object_introspection",
                "class_name": entity_object.__class__.__name__
                if hasattr(entity_object, "__class__")
                else str(type(entity_object)),
            },
        )


# ============================================================================
# MESSAGE MAPPER BASE CLASS
# ============================================================================


class MessageMapper(ABC):
    """Base class for mapping framework messages/responses to OpenAI format."""

    def __init__(self) -> None:
        """Initialize message mapper."""
        self.sequence_counter = 0
        self._conversion_contexts: dict[int, dict[str, Any]] = {}

    @abstractmethod
    async def convert_event(self, raw_event: Any, request: AgentFrameworkRequest) -> Sequence[Any]:
        """Convert a single framework event to OpenAI events.

        Args:
            raw_event: Framework-specific event or message
            request: Original request for context

        Returns:
            Sequence of OpenAI response stream events or compatible events
        """
        ...

    @abstractmethod
    async def aggregate_to_response(self, events: Sequence[Any], request: AgentFrameworkRequest) -> OpenAIResponse:
        """Aggregate streaming events into final OpenAI response.

        Args:
            events: Sequence of OpenAI stream events or compatible events
            request: Original request for context

        Returns:
            Final aggregated OpenAI response
        """
        ...

    def _get_or_create_context(self, request: AgentFrameworkRequest) -> dict[str, Any]:
        """Get or create conversion context for this request.

        Args:
            request: Request to get context for

        Returns:
            Conversion context dictionary
        """
        request_key = id(request)
        if request_key not in self._conversion_contexts:
            self._conversion_contexts[request_key] = {
                "sequence_counter": 0,
                "item_id": f"msg_{uuid.uuid4().hex[:8]}",
                "content_index": 0,
                "output_index": 0,
            }
        return self._conversion_contexts[request_key]

    def _next_sequence(self, context: dict[str, Any]) -> int:
        """Get next sequence number for events.

        Args:
            context: Conversion context

        Returns:
            Next sequence number
        """
        context["sequence_counter"] += 1
        return int(context["sequence_counter"])


# ============================================================================
# FRAMEWORK EXECUTOR BASE CLASS
# ============================================================================


class EntityNotFoundError(Exception):
    """Raised when an entity is not found."""

    pass


class FrameworkExecutor(ABC):
    """Base class for framework-specific executors."""

    def __init__(self, entity_discovery: EntityDiscovery, message_mapper: MessageMapper):
        """Initialize framework executor.

        Args:
            entity_discovery: Entity discovery instance
            message_mapper: Message mapper instance
        """
        self.entity_discovery = entity_discovery
        self.message_mapper = message_mapper
        self.framework_name = self.entity_discovery.framework_name

    @abstractmethod
    async def execute_entity(self, entity_id: str, request: AgentFrameworkRequest) -> AsyncGenerator[Any, None]:
        """Execute the entity and yield raw framework events.

        Args:
            entity_id: ID of entity to execute
            request: Request to execute

        Yields:
            Raw framework events/messages
        """
        yield  # Make this a proper async generator

    async def execute_streaming(self, request: AgentFrameworkRequest) -> AsyncGenerator[ResponseStreamEvent, None]:
        """Execute request and stream results in OpenAI format.

        Args:
            request: Request to execute

        Yields:
            OpenAI response stream events
        """
        try:
            entity_id = request.get_entity_id()
            if not entity_id:
                logger.error("No entity_id specified in request")
                return

            # Validate entity exists
            if not self.entity_discovery.get_entity_info(entity_id):
                logger.error(f"Entity '{entity_id}' not found")
                return

            # Execute entity and convert events
            async for raw_event in self.execute_entity(entity_id, request):
                openai_events = await self.message_mapper.convert_event(raw_event, request)
                for event in openai_events:
                    yield event

        except Exception as e:
            logger.exception(f"Error in streaming execution: {e}")
            # Could yield error event here

    async def execute_sync(self, request: AgentFrameworkRequest) -> OpenAIResponse:
        """Execute request synchronously and return complete response.

        Args:
            request: Request to execute

        Returns:
            Final aggregated OpenAI response
        """
        # Collect all streaming events
        events = [event async for event in self.execute_streaming(request)]

        # Aggregate into final response
        return await self.message_mapper.aggregate_to_response(events, request)

    async def discover_entities(self) -> list[EntityInfo]:
        """Discover all available entities.

        Returns:
            List of discovered entities
        """
        return await self.entity_discovery.discover_entities()

    def get_entity_info(self, entity_id: str) -> EntityInfo:
        """Get entity information.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity information

        Raises:
            EntityNotFoundError: If entity is not found
        """
        entity_info = self.entity_discovery.get_entity_info(entity_id)
        if entity_info is None:
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        return entity_info
