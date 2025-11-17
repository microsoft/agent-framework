# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework entity discovery implementation."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

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
        self._cleanup_hooks: dict[str, list[Any]] = {}

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

    async def load_entity(self, entity_id: str, checkpoint_manager: Any = None) -> Any:
        """Load entity on-demand and inject checkpoint storage for workflows.

        This method implements lazy loading by importing the entity module only when needed.
        In-memory entities are returned from cache immediately.

        Args:
            entity_id: Entity identifier
            checkpoint_manager: Optional checkpoint manager for workflow storage injection

        Returns:
            Loaded entity object

        Raises:
            ValueError: If entity not found or cannot be loaded
        """
        # Check if already loaded (includes in-memory entities)
        if entity_id in self._loaded_objects:
            logger.debug(f"Entity {entity_id} already loaded (cache hit)")
            return self._loaded_objects[entity_id]

        # Get entity metadata
        entity_info = self._entities.get(entity_id)
        if not entity_info:
            raise ValueError(f"Entity {entity_id} not found in registry")

        # In-memory entities should never reach here (they're pre-loaded)
        if entity_info.source == "in_memory":
            raise ValueError(f"In-memory entity {entity_id} missing from loaded objects cache")

        logger.info(f"Lazy loading entity: {entity_id} (source: {entity_info.source})")

        # Load based on source - only directory and in-memory are supported
        if entity_info.source == "directory":
            entity_obj = await self._load_directory_entity(entity_id, entity_info)
        else:
            raise ValueError(
                f"Unsupported entity source: {entity_info.source}. "
                f"Only 'directory' and 'in-memory' sources are supported."
            )

        # Note: Checkpoint storage is now injected at runtime via run_stream() parameter,
        # not at load time. This provides cleaner architecture and explicit control flow.
        # See _executor.py _execute_workflow() for runtime checkpoint storage injection.

        # Enrich metadata with actual entity data
        # Don't pass entity_type if it's "unknown" - let inference determine the real type
        enriched_info = await self.create_entity_info_from_object(
            entity_obj,
            entity_type=entity_info.type if entity_info.type != "unknown" else None,
            source=entity_info.source,
        )
        # IMPORTANT: Preserve the original entity_id (enrichment generates a new one)
        enriched_info.id = entity_id
        # Preserve the original path from sparse metadata
        if "path" in entity_info.metadata:
            enriched_info.metadata["path"] = entity_info.metadata["path"]
            # Now that we have the path, properly check deployment support
            entity_path = Path(entity_info.metadata["path"])
            deployment_supported, deployment_reason = self._check_deployment_support(entity_path, entity_info.source)
            enriched_info.deployment_supported = deployment_supported
            enriched_info.deployment_reason = deployment_reason
        enriched_info.metadata["lazy_loaded"] = True
        self._entities[entity_id] = enriched_info

        # Cache the loaded object
        self._loaded_objects[entity_id] = entity_obj

        # Check module-level registry for cleanup hooks
        from . import _get_registered_cleanup_hooks

        registered_hooks = _get_registered_cleanup_hooks(entity_obj)
        if registered_hooks:
            if entity_id not in self._cleanup_hooks:
                self._cleanup_hooks[entity_id] = []
            self._cleanup_hooks[entity_id].extend(registered_hooks)
            logger.debug(f"Discovered {len(registered_hooks)} registered cleanup hook(s) for: {entity_id}")

        logger.info(f"Successfully loaded entity: {entity_id} (type: {enriched_info.type})")

        return entity_obj

    async def _load_directory_entity(self, entity_id: str, entity_info: EntityInfo) -> Any:
        """Load entity from directory (imports module).

        Args:
            entity_id: Entity identifier
            entity_info: Entity metadata

        Returns:
            Loaded entity object
        """
        # Get directory path from metadata
        dir_path = Path(entity_info.metadata.get("path", ""))
        if not dir_path.exists():  # noqa: ASYNC240
            raise ValueError(f"Entity directory not found: {dir_path}")

        # Load .env if it exists
        if dir_path.is_dir():  # noqa: ASYNC240
            self._load_env_for_entity(dir_path)
        else:
            self._load_env_for_entity(dir_path.parent)

        # Import the module
        if dir_path.is_dir():  # noqa: ASYNC240
            # Directory-based entity - try different import patterns
            import_patterns = [
                entity_id,
                f"{entity_id}.agent",
                f"{entity_id}.workflow",
            ]

            for pattern in import_patterns:
                module = self._load_module_from_pattern(pattern)
                if module:
                    # Find entity in module - pass entity_id so registration uses correct ID
                    entity_obj = await self._find_entity_in_module(module, entity_id, str(dir_path))
                    if entity_obj:
                        return entity_obj

            raise ValueError(f"No valid entity found in {dir_path}")
        # File-based entity
        module = self._load_module_from_file(dir_path, entity_id)
        if module:
            entity_obj = await self._find_entity_in_module(module, entity_id, str(dir_path))
            if entity_obj:
                return entity_obj

        raise ValueError(f"No valid entity found in {dir_path}")

    def list_entities(self) -> list[EntityInfo]:
        """List all discovered entities.

        Returns:
            List of all entity information
        """
        return list(self._entities.values())

    def get_cleanup_hooks(self, entity_id: str) -> list[Any]:
        """Get cleanup hooks registered for an entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List of cleanup hooks for the entity
        """
        return self._cleanup_hooks.get(entity_id, [])

    def invalidate_entity(self, entity_id: str) -> None:
        """Invalidate (clear cache for) an entity to enable hot reload.

        This removes the entity from the loaded objects cache and clears its module
        from Python's sys.modules cache. The entity metadata remains, so it will be
        reimported on next access.

        Args:
            entity_id: Entity identifier to invalidate
        """
        # Remove from loaded objects cache
        if entity_id in self._loaded_objects:
            del self._loaded_objects[entity_id]
            logger.info(f"Cleared loaded object cache for: {entity_id}")

        # Clear from Python's module cache (including submodules)
        keys_to_delete = [
            module_name
            for module_name in sys.modules
            if module_name == entity_id or module_name.startswith(f"{entity_id}.")
        ]
        for key in keys_to_delete:
            del sys.modules[key]
            logger.debug(f"Cleared module cache: {key}")

        # Reset lazy_loaded flag in metadata
        entity_info = self._entities.get(entity_id)
        if entity_info and "lazy_loaded" in entity_info.metadata:
            entity_info.metadata["lazy_loaded"] = False

        logger.info(f"Entity invalidated: {entity_id} (will reload on next access)")

    def invalidate_all(self) -> None:
        """Invalidate all cached entities.

        Useful for forcing a complete reload of all entities.
        """
        entity_ids = list(self._loaded_objects.keys())
        for entity_id in entity_ids:
            self.invalidate_entity(entity_id)
        logger.info(f"Invalidated {len(entity_ids)} entities")

    def register_entity(self, entity_id: str, entity_info: EntityInfo, entity_object: Any) -> None:
        """Register an entity with both metadata and object.

        Args:
            entity_id: Unique entity identifier
            entity_info: Entity metadata
            entity_object: Actual entity object for execution
        """
        self._entities[entity_id] = entity_info
        self._loaded_objects[entity_id] = entity_object

        # Check module-level registry for cleanup hooks
        from . import _get_registered_cleanup_hooks

        registered_hooks = _get_registered_cleanup_hooks(entity_object)
        if registered_hooks:
            if entity_id not in self._cleanup_hooks:
                self._cleanup_hooks[entity_id] = []
            self._cleanup_hooks[entity_id].extend(registered_hooks)
            logger.debug(f"Discovered {len(registered_hooks)} registered cleanup hook(s) for: {entity_id}")

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
            # In-memory entities: use class name as it's more readable than UUID
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
            from ._utils import extract_agent_metadata

            agent_meta = extract_agent_metadata(entity_object)
            instructions = agent_meta["instructions"]
            model = agent_meta["model"]
            chat_client_type = agent_meta["chat_client_type"]
            context_providers_list = agent_meta["context_providers"]
            middleware_list = agent_meta["middleware"]

        # Log helpful info about agent capabilities (before creating EntityInfo)
        if entity_type == "agent":
            has_run_stream = hasattr(entity_object, "run_stream")
            has_run = hasattr(entity_object, "run")

            if not has_run_stream and has_run:
                logger.info(
                    f"Agent '{entity_id}' only has run() (non-streaming). "
                    "DevUI will automatically convert to streaming."
                )
            elif not has_run_stream and not has_run:
                logger.warning(f"Agent '{entity_id}' lacks both run() and run_stream() methods. May not work.")

        # Check deployment support based on source
        # For directory-based entities, we need the path to verify deployment support
        deployment_supported = False
        deployment_reason = "In-memory entities cannot be deployed (no source directory)"

        if source == "directory":
            # Directory-based entity - will be checked properly after enrichment when path is available
            # For now, mark as potentially deployable - will be re-evaluated after enrichment
            deployment_supported = True
            deployment_reason = "Ready for deployment (pending path verification)"

        # Create EntityInfo with Agent Framework specifics
        return EntityInfo(
            id=entity_id,
            name=name,
            description=description,
            type=entity_type,
            framework="agent_framework",
            tools=[str(tool) for tool in (tools_list or [])],
            instructions=instructions,
            model_id=model,
            chat_client_type=chat_client_type,
            context_providers=context_providers_list,
            middleware=middleware_list,
            executors=tools_list if entity_type == "workflow" else [],
            input_schema={"type": "string"},  # Default schema
            start_executor_id=tools_list[0] if tools_list and entity_type == "workflow" else None,
            deployment_supported=deployment_supported,
            deployment_reason=deployment_reason,
            metadata={
                "source": "agent_framework_object",
                "class_name": entity_object.__class__.__name__
                if hasattr(entity_object, "__class__")
                else str(type(entity_object)),
                "has_run_stream": hasattr(entity_object, "run_stream"),
            },
        )

    async def _scan_entities_directory(self, entities_dir: Path) -> None:
        """Scan the entities directory for Agent Framework entities (lazy loading).

        This method scans the filesystem WITHOUT importing modules, creating sparse
        metadata that will be enriched on-demand when entities are accessed.

        Args:
            entities_dir: Directory to scan for entities
        """
        if not entities_dir.exists():  # noqa: ASYNC240
            logger.warning(f"Entities directory not found: {entities_dir}")
            return

        logger.info(f"Scanning {entities_dir} for Agent Framework entities (lazy mode)...")

        # Add entities directory to Python path if not already there
        entities_dir_str = str(entities_dir)
        if entities_dir_str not in sys.path:
            sys.path.insert(0, entities_dir_str)

        # Scan for directories and Python files WITHOUT importing
        for item in entities_dir.iterdir():  # noqa: ASYNC240
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            if item.is_dir() and self._looks_like_entity(item):
                # Directory-based entity - create sparse metadata
                self._register_sparse_entity(item)
            elif item.is_file() and item.suffix == ".py" and not item.name.startswith("_"):
                # Single file entity - create sparse metadata
                self._register_sparse_file_entity(item)

    def _looks_like_entity(self, dir_path: Path) -> bool:
        """Check if directory contains an entity (without importing).

        Args:
            dir_path: Directory to check

        Returns:
            True if directory appears to contain an entity
        """
        return (
            (dir_path / "agent.py").exists()
            or (dir_path / "workflow.py").exists()
            or (dir_path / "__init__.py").exists()
        )

    def _detect_entity_type(self, dir_path: Path) -> str:
        """Detect entity type from directory structure (without importing).

        Uses filename conventions to determine entity type:
        - workflow.py → "workflow"
        - agent.py → "agent"
        - both or neither → "unknown"

        Args:
            dir_path: Directory to analyze

        Returns:
            Entity type: "workflow", "agent", or "unknown"
        """
        has_agent = (dir_path / "agent.py").exists()
        has_workflow = (dir_path / "workflow.py").exists()

        if has_agent and has_workflow:
            # Both files exist - ambiguous, mark as unknown
            return "unknown"
        if has_workflow:
            return "workflow"
        if has_agent:
            return "agent"
        # Has __init__.py but no specific file
        return "unknown"

    def _check_deployment_support(self, entity_path: Path, source: str) -> tuple[bool, str | None]:
        """Check if entity can be deployed to Azure Container Apps.

        Args:
            entity_path: Path to entity directory or file
            source: Entity source ("directory" or "in_memory")

        Returns:
            Tuple of (supported, reason) explaining deployment eligibility
        """
        # In-memory entities cannot be deployed
        if source == "in_memory":
            return False, "In-memory entities cannot be deployed (no source directory)"

        # File-based entities need a directory structure for deployment
        if not entity_path.is_dir():
            return False, "Only directory-based entities can be deployed"

        # Must have __init__.py
        if not (entity_path / "__init__.py").exists():
            return False, "Missing __init__.py file"

        # Passed all checks
        return True, "Ready for deployment"

    def _register_sparse_entity(self, dir_path: Path) -> None:
        """Register entity with sparse metadata (no import).

        Args:
            dir_path: Entity directory
        """
        entity_id = dir_path.name
        entity_type = self._detect_entity_type(dir_path)

        # Check deployment support
        deployment_supported, deployment_reason = self._check_deployment_support(dir_path, "directory")

        entity_info = EntityInfo(
            id=entity_id,
            name=entity_id.replace("_", " ").title(),
            type=entity_type,
            framework="agent_framework",
            tools=[],  # Sparse - will be populated on load
            description="",  # Sparse - will be populated on load
            source="directory",
            deployment_supported=deployment_supported,
            deployment_reason=deployment_reason,
            metadata={
                "path": str(dir_path),
                "discovered": True,
                "lazy_loaded": False,
            },
        )

        self._entities[entity_id] = entity_info
        logger.debug(f"Registered sparse entity: {entity_id} (type: {entity_type})")

    def _has_entity_exports(self, file_path: Path) -> bool:
        """Check if a Python file has entity exports (agent or workflow) using AST parsing.

        This safely checks for module-level assignments like:
        - agent = ChatAgent(...)
        - workflow = WorkflowBuilder()...

        Args:
            file_path: Python file to check

        Returns:
            True if file has 'agent' or 'workflow' exports
        """
        try:
            # Read and parse the file's AST
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))

            # Look for module-level assignments of 'agent' or 'workflow'
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in ("agent", "workflow"):
                            return True
        except Exception as e:
            logger.debug(f"Could not parse {file_path} for entity exports: {e}")
            return False

        return False

    def _register_sparse_file_entity(self, file_path: Path) -> None:
        """Register file-based entity with sparse metadata (no import).

        Args:
            file_path: Entity Python file
        """
        # Check if file has valid entity exports using AST parsing
        if not self._has_entity_exports(file_path):
            logger.debug(f"Skipping {file_path.name} - no 'agent' or 'workflow' exports found")
            return

        entity_id = file_path.stem

        # Check deployment support (file-based entities cannot be deployed)
        deployment_supported, deployment_reason = self._check_deployment_support(file_path, "directory")

        # File-based entities are typically agents, but we can't know for sure without importing
        entity_info = EntityInfo(
            id=entity_id,
            name=entity_id.replace("_", " ").title(),
            type="unknown",  # Will be determined on load
            framework="agent_framework",
            tools=[],
            description="",
            source="directory",
            deployment_supported=deployment_supported,
            deployment_reason=deployment_reason,
            metadata={
                "path": str(file_path),
                "discovered": True,
                "lazy_loaded": False,
            },
        )

        self._entities[entity_id] = entity_info
        logger.debug(f"Registered sparse file entity: {entity_id}")

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

    async def _find_entity_in_module(self, module: Any, entity_id: str, module_path: str) -> Any:
        """Find agent or workflow entity in a loaded module.

        Args:
            module: Loaded Python module
            entity_id: Expected entity identifier to register with
            module_path: Path to module for metadata

        Returns:
            Loaded entity object, or None if not found
        """
        # Look for explicit variable names first
        candidates = [
            ("agent", getattr(module, "agent", None)),
            ("workflow", getattr(module, "workflow", None)),
        ]

        for obj_type, obj in candidates:
            if obj is None:
                continue

            if self._is_valid_entity(obj, obj_type):
                # Register with the correct entity_id (from directory name)
                # Store the object directly in _loaded_objects so we can return it
                self._loaded_objects[entity_id] = obj
                return obj

        return None

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
            # Agent must have either run_stream() or run() method, plus id and name
            has_execution_method = hasattr(obj, "run_stream") or hasattr(obj, "run")
            if has_execution_method and hasattr(obj, "id") and hasattr(obj, "name"):
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
                # Use class name as it's more readable than UUID
                class_name = obj.__class__.__name__
                name = f"{obj_type.title()} {class_name}"
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
                from ._utils import extract_agent_metadata

                agent_meta = extract_agent_metadata(obj)
                instructions = agent_meta["instructions"]
                model = agent_meta["model"]
                chat_client_type = agent_meta["chat_client_type"]
                context_providers_list = agent_meta["context_providers"]
                middleware_list = agent_meta["middleware"]

            entity_info = EntityInfo(
                id=entity_id,
                type=obj_type,
                name=name,
                framework="agent_framework",
                description=description,
                tools=tools_union,
                instructions=instructions,
                model_id=model,
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
            Unique entity ID with format: {type}_{source}_{name}_{uuid}
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

        # Generate full UUID for guaranteed uniqueness
        full_uuid = uuid.uuid4().hex

        return f"{entity_type}_{source}_{base_name}_{full_uuid}"
