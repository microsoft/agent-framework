# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework entity discovery implementation."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from .models._discovery_models import EntityInfo

logger = logging.getLogger(__name__)


class EntityDiscovery:
    """Discovery for Agent Framework entities - agents and workflows."""

    def __init__(self, entities_dir: str | None = None):
        """Initialize entity discovery.

        Args:
            entities_dir: Directory to scan for entities (optional)
        """
        self.entities_dir = entities_dir
        self._entities: dict[str, EntityInfo] = {}
        self._loaded_objects: dict[str, Any] = {}
        self._remote_cache_dir = Path.home() / ".agent_framework_devui" / "remote_cache"

    async def discover_entities(self) -> list[EntityInfo]:
        """Scan for Agent Framework entities.

        Returns:
            List of discovered entities
        """
        if not self.entities_dir:
            logger.info("No Agent Framework entities directory configured")
            return []

        entities_dir = Path(self.entities_dir).resolve()  # noqa: ASYNC240
        await self._scan_entities_directory(entities_dir)

        logger.info(f"Discovered {len(self._entities)} Agent Framework entities")
        return self.list_entities()

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

    async def create_entity_info_from_object(
        self, entity_object: Any, entity_type: str | None = None, source: str = "in_memory"
    ) -> EntityInfo:
        """Create EntityInfo from Agent Framework entity object.

        Args:
            entity_object: Agent Framework entity object
            entity_type: Optional entity type override
            source: Source of entity (directory, in_memory, remote)

        Returns:
            EntityInfo with Agent Framework specific metadata
        """
        # Determine entity type if not provided
        if entity_type is None:
            entity_type = "agent"
            # Check if it's a workflow
            if hasattr(entity_object, "get_executors_list") or hasattr(entity_object, "executors"):
                entity_type = "workflow"

        # Extract metadata with improved fallback naming
        name = getattr(entity_object, "name", None)
        if not name:
            # In-memory entities: use ID with entity type prefix since no directory name available
            entity_id_raw = getattr(entity_object, "id", None)
            if entity_id_raw:
                # Truncate UUID to first 8 characters for readability
                short_id = str(entity_id_raw)[:8] if len(str(entity_id_raw)) > 8 else str(entity_id_raw)
                name = f"{entity_type.title()} {short_id}"
            else:
                # Fallback to class name with entity type
                class_name = entity_object.__class__.__name__
                name = f"{entity_type.title()} {class_name}"
        description = getattr(entity_object, "description", "")

        # Generate entity ID using Agent Framework specific naming
        entity_id = self._generate_entity_id(entity_object, entity_type, source)

        # Extract tools/executors using Agent Framework specific logic
        tools_list = await self._extract_tools_from_object(entity_object, entity_type)

        # Extract agent-specific fields (for agents only)
        instructions = None
        model = None
        chat_client_type = None
        context_providers_list = None
        middleware_list = None

        if entity_type == "agent":
            # Try to get instructions
            if hasattr(entity_object, "chat_options") and hasattr(entity_object.chat_options, "instructions"):
                instructions = entity_object.chat_options.instructions

            # Try to get model - check both chat_options and chat_client
            if (
                hasattr(entity_object, "chat_options")
                and hasattr(entity_object.chat_options, "model_id")
                and entity_object.chat_options.model_id
            ):
                model = entity_object.chat_options.model_id
            elif hasattr(entity_object, "chat_client") and hasattr(entity_object.chat_client, "model_id"):
                model = entity_object.chat_client.model_id

            # Try to get chat client type
            if hasattr(entity_object, "chat_client"):
                chat_client_type = entity_object.chat_client.__class__.__name__

            # Try to get context providers
            if (
                hasattr(entity_object, "context_provider")
                and entity_object.context_provider
                and hasattr(entity_object.context_provider, "__class__")
            ):
                context_providers_list = [entity_object.context_provider.__class__.__name__]

            # Try to get middleware
            if hasattr(entity_object, "middleware") and entity_object.middleware:
                middleware_list = []
                for m in entity_object.middleware:
                    # Try multiple ways to get a good name for middleware
                    if hasattr(m, "__name__"):  # Function or callable
                        middleware_list.append(m.__name__)
                    elif hasattr(m, "__class__"):  # Class instance
                        middleware_list.append(m.__class__.__name__)
                    else:
                        middleware_list.append(str(m))

        # Create EntityInfo with Agent Framework specifics
        return EntityInfo(
            id=entity_id,
            name=name,
            description=description,
            type=entity_type,
            framework="agent_framework",
            tools=[str(tool) for tool in (tools_list or [])],
            instructions=instructions,
            model=model,
            chat_client_type=chat_client_type,
            context_providers=context_providers_list,
            middleware=middleware_list,
            executors=tools_list if entity_type == "workflow" else [],
            input_schema={"type": "string"},  # Default schema
            start_executor_id=tools_list[0] if tools_list and entity_type == "workflow" else None,
            metadata={
                "source": "agent_framework_object",
                "class_name": entity_object.__class__.__name__
                if hasattr(entity_object, "__class__")
                else str(type(entity_object)),
                "has_run_stream": hasattr(entity_object, "run_stream"),
            },
        )

    async def _scan_entities_directory(self, entities_dir: Path) -> None:
        """Scan the entities directory for Agent Framework entities.

        Args:
            entities_dir: Directory to scan for entities
        """
        if not entities_dir.exists():  # noqa: ASYNC240
            logger.warning(f"Entities directory not found: {entities_dir}")
            return

        logger.info(f"Scanning {entities_dir} for Agent Framework entities...")

        # Add entities directory to Python path if not already there
        entities_dir_str = str(entities_dir)
        if entities_dir_str not in sys.path:
            sys.path.insert(0, entities_dir_str)

        # Scan for directories and Python files
        for item in entities_dir.iterdir():  # noqa: ASYNC240
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            if item.is_dir():
                # Directory-based entity
                await self._discover_entities_in_directory(item)
            elif item.is_file() and item.suffix == ".py" and not item.name.startswith("_"):
                # Single file entity
                await self._discover_entities_in_file(item)

    async def _discover_entities_in_directory(self, dir_path: Path) -> None:
        """Discover entities in a directory using module import.

        Args:
            dir_path: Directory containing entity
        """
        entity_id = dir_path.name
        logger.debug(f"Scanning directory: {entity_id}")

        try:
            # Load environment variables for this entity first
            self._load_env_for_entity(dir_path)

            # Try different import patterns
            import_patterns = [
                entity_id,  # Direct module import
                f"{entity_id}.agent",  # agent.py submodule
                f"{entity_id}.workflow",  # workflow.py submodule
            ]

            for pattern in import_patterns:
                module = self._load_module_from_pattern(pattern)
                if module:
                    entities_found = await self._find_entities_in_module(module, entity_id, str(dir_path))
                    if entities_found:
                        logger.debug(f"Found {len(entities_found)} entities in {pattern}")
                        break

        except Exception as e:
            logger.warning(f"Error scanning directory {entity_id}: {e}")

    async def _discover_entities_in_file(self, file_path: Path) -> None:
        """Discover entities in a single Python file.

        Args:
            file_path: Python file to scan
        """
        try:
            # Load environment variables for this entity's directory first
            self._load_env_for_entity(file_path.parent)

            # Create module name from file path
            base_name = file_path.stem

            # Load the module directly from file
            module = self._load_module_from_file(file_path, base_name)
            if module:
                entities_found = await self._find_entities_in_module(module, base_name, str(file_path))
                if entities_found:
                    logger.debug(f"Found {len(entities_found)} entities in {file_path.name}")

        except Exception as e:
            logger.warning(f"Error scanning file {file_path}: {e}")

    def _load_env_for_entity(self, entity_path: Path) -> bool:
        """Load .env file for an entity.

        Args:
            entity_path: Path to entity directory

        Returns:
            True if .env was loaded successfully
        """
        # Check for .env in the entity folder first
        env_file = entity_path / ".env"
        if self._load_env_file(env_file):
            return True

        # Check one level up (the entities directory) for safety
        if self.entities_dir:
            entities_dir = Path(self.entities_dir).resolve()
            entities_env = entities_dir / ".env"
            if self._load_env_file(entities_env):
                return True

        return False

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

    def _load_module_from_pattern(self, pattern: str) -> Any | None:
        """Load module using import pattern.

        Args:
            pattern: Import pattern to try

        Returns:
            Loaded module or None if failed
        """
        try:
            # Check if module exists first
            spec = importlib.util.find_spec(pattern)
            if spec is None:
                return None

            module = importlib.import_module(pattern)
            logger.debug(f"Successfully imported {pattern}")
            return module

        except ModuleNotFoundError:
            logger.debug(f"Import pattern {pattern} not found")
            return None
        except Exception as e:
            logger.warning(f"Error importing {pattern}: {e}")
            return None

    def _load_module_from_file(self, file_path: Path, module_name: str) -> Any | None:
        """Load module directly from file path.

        Args:
            file_path: Path to Python file
            module_name: Name to assign to module

        Returns:
            Loaded module or None if failed
        """
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module  # Add to sys.modules for proper imports
            spec.loader.exec_module(module)

            logger.debug(f"Successfully loaded module from {file_path}")
            return module

        except Exception as e:
            logger.warning(f"Error loading module from {file_path}: {e}")
            return None

    async def _find_entities_in_module(self, module: Any, base_id: str, module_path: str) -> list[str]:
        """Find agent and workflow entities in a loaded module.

        Args:
            module: Loaded Python module
            base_id: Base identifier for entities
            module_path: Path to module for metadata

        Returns:
            List of entity IDs that were found and registered
        """
        entities_found = []

        # Look for explicit variable names first
        candidates = [
            ("agent", getattr(module, "agent", None)),
            ("workflow", getattr(module, "workflow", None)),
        ]

        for obj_type, obj in candidates:
            if obj is None:
                continue

            if self._is_valid_entity(obj, obj_type):
                # Pass source as "directory" for directory-discovered entities
                await self._register_entity_from_object(obj, obj_type, module_path, source="directory")
                entities_found.append(obj_type)

        return entities_found

    def _is_valid_entity(self, obj: Any, expected_type: str) -> bool:
        """Check if object is a valid agent or workflow using duck typing.

        Args:
            obj: Object to validate
            expected_type: Expected type ("agent" or "workflow")

        Returns:
            True if object is valid for the expected type
        """
        if expected_type == "agent":
            return self._is_valid_agent(obj)
        if expected_type == "workflow":
            return self._is_valid_workflow(obj)
        return False

    def _is_valid_agent(self, obj: Any) -> bool:
        """Check if object is a valid Agent Framework agent.

        Args:
            obj: Object to validate

        Returns:
            True if object appears to be a valid agent
        """
        try:
            # Try to import AgentProtocol for proper type checking
            try:
                from agent_framework import AgentProtocol

                if isinstance(obj, AgentProtocol):
                    return True
            except ImportError:
                pass

            # Fallback to duck typing for agent protocol
            if hasattr(obj, "run_stream") and hasattr(obj, "id") and hasattr(obj, "name"):
                return True

        except (TypeError, AttributeError):
            pass

        return False

    def _is_valid_workflow(self, obj: Any) -> bool:
        """Check if object is a valid Agent Framework workflow.

        Args:
            obj: Object to validate

        Returns:
            True if object appears to be a valid workflow
        """
        # Check for workflow - must have run_stream method and executors
        return hasattr(obj, "run_stream") and (hasattr(obj, "executors") or hasattr(obj, "get_executors_list"))

    async def _register_entity_from_object(
        self, obj: Any, obj_type: str, module_path: str, source: str = "directory"
    ) -> None:
        """Register an entity from a live object.

        Args:
            obj: Entity object
            obj_type: Type of entity ("agent" or "workflow")
            module_path: Path to module for metadata
            source: Source of entity (directory, in_memory, remote)
        """
        try:
            # Generate entity ID with source information
            entity_id = self._generate_entity_id(obj, obj_type, source)

            # Extract metadata from the live object with improved fallback naming
            name = getattr(obj, "name", None)
            if not name:
                entity_id_raw = getattr(obj, "id", None)
                if entity_id_raw:
                    # Truncate UUID to first 8 characters for readability
                    short_id = str(entity_id_raw)[:8] if len(str(entity_id_raw)) > 8 else str(entity_id_raw)
                    name = f"{obj_type.title()} {short_id}"
                else:
                    name = f"{obj_type.title()} {obj.__class__.__name__}"
            description = getattr(obj, "description", None)
            tools = await self._extract_tools_from_object(obj, obj_type)

            # Create EntityInfo
            tools_union: list[str | dict[str, Any]] | None = None
            if tools:
                tools_union = [tool for tool in tools]

            # Extract agent-specific fields (for agents only)
            instructions = None
            model = None
            chat_client_type = None
            context_providers_list = None
            middleware_list = None

            if obj_type == "agent":
                # Try to get instructions
                if hasattr(obj, "chat_options") and hasattr(obj.chat_options, "instructions"):
                    instructions = obj.chat_options.instructions

                # Try to get model - check both chat_options and chat_client
                if hasattr(obj, "chat_options") and hasattr(obj.chat_options, "model_id") and obj.chat_options.model_id:
                    model = obj.chat_options.model_id
                elif hasattr(obj, "chat_client") and hasattr(obj.chat_client, "model_id"):
                    model = obj.chat_client.model_id

                # Try to get chat client type
                if hasattr(obj, "chat_client"):
                    chat_client_type = obj.chat_client.__class__.__name__

                # Try to get context providers
                if (
                    hasattr(obj, "context_provider")
                    and obj.context_provider
                    and hasattr(obj.context_provider, "__class__")
                ):
                    context_providers_list = [obj.context_provider.__class__.__name__]

                # Try to get middleware
                if hasattr(obj, "middleware") and obj.middleware:
                    middleware_list = []
                    for m in obj.middleware:
                        # Try multiple ways to get a good name for middleware
                        if hasattr(m, "__name__"):  # Function or callable
                            middleware_list.append(m.__name__)
                        elif hasattr(m, "__class__"):  # Class instance
                            middleware_list.append(m.__class__.__name__)
                        else:
                            middleware_list.append(str(m))

            entity_info = EntityInfo(
                id=entity_id,
                type=obj_type,
                name=name,
                framework="agent_framework",
                description=description,
                tools=tools_union,
                instructions=instructions,
                model=model,
                chat_client_type=chat_client_type,
                context_providers=context_providers_list,
                middleware=middleware_list,
                metadata={
                    "module_path": module_path,
                    "entity_type": obj_type,
                    "source": source,
                    "has_run_stream": hasattr(obj, "run_stream"),
                    "class_name": obj.__class__.__name__ if hasattr(obj, "__class__") else str(type(obj)),
                },
            )

            # Register the entity
            self.register_entity(entity_id, entity_info, obj)

        except Exception as e:
            logger.error(f"Error registering entity from {source}: {e}")

    async def _extract_tools_from_object(self, obj: Any, obj_type: str) -> list[str]:
        """Extract tool/executor names from a live object.

        Args:
            obj: Entity object
            obj_type: Type of entity

        Returns:
            List of tool/executor names
        """
        tools = []

        try:
            if obj_type == "agent":
                # For agents, check chat_options.tools first
                chat_options = getattr(obj, "chat_options", None)
                if chat_options and hasattr(chat_options, "tools"):
                    for tool in chat_options.tools:
                        if hasattr(tool, "__name__"):
                            tools.append(tool.__name__)
                        elif hasattr(tool, "name"):
                            tools.append(tool.name)
                        else:
                            tools.append(str(tool))
                else:
                    # Fallback to direct tools attribute
                    agent_tools = getattr(obj, "tools", None)
                    if agent_tools:
                        for tool in agent_tools:
                            if hasattr(tool, "__name__"):
                                tools.append(tool.__name__)
                            elif hasattr(tool, "name"):
                                tools.append(tool.name)
                            else:
                                tools.append(str(tool))

            elif obj_type == "workflow":
                # For workflows, extract executor names
                if hasattr(obj, "get_executors_list"):
                    executor_objects = obj.get_executors_list()
                    tools = [getattr(ex, "id", str(ex)) for ex in executor_objects]
                elif hasattr(obj, "executors"):
                    executors = obj.executors
                    if isinstance(executors, list):
                        tools = [getattr(ex, "id", str(ex)) for ex in executors]
                    elif isinstance(executors, dict):
                        tools = list(executors.keys())

        except Exception as e:
            logger.debug(f"Error extracting tools from {obj_type} {type(obj)}: {e}")

        return tools

    def _generate_entity_id(self, entity: Any, entity_type: str, source: str = "directory") -> str:
        """Generate unique entity ID with UUID suffix for collision resistance.

        Args:
            entity: Entity object
            entity_type: Type of entity (agent, workflow, etc.)
            source: Source of entity (directory, in_memory, remote)

        Returns:
            Unique entity ID with format: {type}_{source}_{name}_{uuid8}
        """
        import re

        # Extract base name with priority: name -> id -> class_name
        if hasattr(entity, "name") and entity.name:
            base_name = str(entity.name).lower().replace(" ", "-").replace("_", "-")
        elif hasattr(entity, "id") and entity.id:
            base_name = str(entity.id).lower().replace(" ", "-").replace("_", "-")
        elif hasattr(entity, "__class__"):
            class_name = entity.__class__.__name__
            # Convert CamelCase to kebab-case
            base_name = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", class_name).lower()
        else:
            base_name = "entity"

        # Generate short UUID (8 chars = 4 billion combinations)
        short_uuid = uuid.uuid4().hex[:8]

        return f"{entity_type}_{source}_{base_name}_{short_uuid}"

    async def fetch_remote_entity(
        self, url: str, metadata: dict[str, Any] | None = None
    ) -> tuple[EntityInfo | None, str | None]:
        """Fetch and register entity from URL.

        Args:
            url: URL to Python file containing entity
            metadata: Additional metadata (source, sampleId, etc.)

        Returns:
            Tuple of (EntityInfo if successful, error_message if failed)
        """
        try:
            normalized_url = self._normalize_url(url)
            logger.info(f"Normalized URL: {normalized_url}")

            content = await self._fetch_url_content(normalized_url)
            if not content:
                error_msg = "Failed to fetch content from URL. The file may not exist or is not accessible."
                logger.warning(error_msg)
                return None, error_msg

            if not self._validate_python_syntax(content):
                error_msg = "Invalid Python syntax in the file. Please check the file contains valid Python code."
                logger.warning(error_msg)
                return None, error_msg

            entity_object = await self._load_entity_from_content(content, url)
            if not entity_object:
                error_msg = (
                    "No valid agent or workflow found in the file. "
                    "Make sure the file contains an 'agent' or 'workflow' variable."
                )
                logger.warning(error_msg)
                return None, error_msg

            entity_info = await self.create_entity_info_from_object(
                entity_object,
                entity_type=None,  # Auto-detect
                source="remote",
            )

            entity_info.source = metadata.get("source", "remote_gallery") if metadata else "remote_gallery"
            entity_info.original_url = url
            if metadata:
                entity_info.metadata.update(metadata)

            self.register_entity(entity_info.id, entity_info, entity_object)

            logger.info(f"Successfully added remote entity: {entity_info.id}")
            return entity_info, None

        except Exception as e:
            error_msg = f"Unexpected error: {e!s}"
            logger.error(f"Error fetching remote entity from {url}: {e}", exc_info=True)
            return None, error_msg

    def _normalize_url(self, url: str) -> str:
        """Convert various Git hosting URLs to raw content URLs."""
        # GitHub: blob -> raw
        if "github.com" in url and "/blob/" in url:
            return url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        # GitLab: blob -> raw
        if "gitlab.com" in url and "/-/blob/" in url:
            return url.replace("/-/blob/", "/-/raw/")

        # Bitbucket: src -> raw
        if "bitbucket.org" in url and "/src/" in url:
            return url.replace("/src/", "/raw/")

        return url

    async def _fetch_url_content(self, url: str, max_size_mb: int = 10) -> str | None:
        """Fetch content from URL with size and timeout limits."""
        try:
            timeout = 30.0  # 30 second timeout

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    return None

                # Check content length
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_size_mb * 1024 * 1024:
                    logger.warning(f"File too large: {content_length} bytes")
                    return None

                # Read with size limit
                content = response.text
                if len(content.encode("utf-8")) > max_size_mb * 1024 * 1024:
                    logger.warning("Content too large after reading")
                    return None

                return content

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def _validate_python_syntax(self, content: str) -> bool:
        """Validate that content is valid Python code."""
        try:
            compile(content, "<remote>", "exec")
            return True
        except SyntaxError as e:
            logger.warning(f"Python syntax error: {e}")
            return False

    async def _load_entity_from_content(self, content: str, source_url: str) -> Any | None:
        """Load entity object from Python content string using disk-based import.

        This method caches remote entities to disk and uses importlib for loading,
        making it consistent with local entity discovery and avoiding exec() security warnings.
        """
        try:
            # Create cache directory if it doesn't exist
            self._remote_cache_dir.mkdir(parents=True, exist_ok=True)

            # Generate a unique filename based on URL hash
            url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:16]
            module_name = f"remote_entity_{url_hash}"
            cached_file = self._remote_cache_dir / f"{module_name}.py"

            # Write content to cache file
            cached_file.write_text(content, encoding="utf-8")
            logger.debug(f"Cached remote entity to {cached_file}")

            # Load module from cached file using importlib (same as local scanning)
            module = self._load_module_from_file(cached_file, module_name)
            if not module:
                logger.warning(f"Failed to load module from cached file: {cached_file}")
                return None

            # Look for agent or workflow objects in the loaded module
            for name in dir(module):
                if name.startswith("_"):
                    continue

                obj = getattr(module, name)

                # Check for explicitly named entities first
                if name in ["agent", "workflow"] and self._is_valid_entity(obj, name):
                    return obj

                # Also check if any object looks like an agent/workflow
                if self._is_valid_agent(obj) or self._is_valid_workflow(obj):
                    return obj

            return None

        except Exception as e:
            logger.error(f"Error loading entity from content: {e}")
            return None

    def remove_remote_entity(self, entity_id: str) -> bool:
        """Remove a remote entity by ID."""
        if entity_id in self._entities:
            entity_info = self._entities[entity_id]
            if entity_info.source in ["remote_gallery", "remote"]:
                del self._entities[entity_id]
                if entity_id in self._loaded_objects:
                    del self._loaded_objects[entity_id]
                logger.info(f"Removed remote entity: {entity_id}")
                return True
            logger.warning(f"Cannot remove local entity: {entity_id}")
            return False
        return False
