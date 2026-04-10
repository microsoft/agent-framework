# Copyright (c) Microsoft. All rights reserved.

"""Security middleware for prompt injection defense.

This module provides middleware components for tracking and enforcing security labels
on tool calls and results, implementing a deterministic defense against prompt injection attacks.
"""

import logging
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ._middleware import FunctionInvocationContext, FunctionMiddleware
from ._security import (
    ConfidentialityLabel,
    ContentLabel,
    ContentLineage,
    ContentVariableStore,
    IntegrityLabel,
    LabeledMessage,
    VariableReferenceContent,
    combine_labels,
)
from ._sessions import BaseContextProvider
from ._types import Content

if TYPE_CHECKING:
    from ._clients import SupportsChatGetResponse

__all__ = [
    "LabelTrackingFunctionMiddleware",
    "PolicyEnforcementFunctionMiddleware",
    "SecureAgentConfig",
    "get_current_middleware",
]

logger = logging.getLogger(__name__)

# Thread-local storage for current middleware instance
_current_middleware = threading.local()


def _parse_github_mcp_labels(labels_data: dict[str, Any]) -> ContentLabel | None:
    """Parse security labels from GitHub MCP server format.
    
    The GitHub MCP server returns per-field labels in the format:
    {
        "labels": {
            "title": {"integrity": "low", "confidentiality": ["public"]},
            "body": {"integrity": "low", "confidentiality": ["public"]},
            "user": {"integrity": "high", "confidentiality": ["public"]},
            ...
        }
    }
    
    Confidentiality uses a "readers lattice":
    - ["public"] → PUBLIC (anyone can read)
    - ["user_id_1", "user_id_2", ...] → PRIVATE (only specific collaborators can read)
    
    This function extracts the most restrictive (lowest integrity, highest confidentiality)
    label across all fields, focusing on user-controlled content like "body" and "title".
    
    Args:
        labels_data: The "labels" dict from additional_properties containing per-field labels.
        
    Returns:
        A ContentLabel with the most restrictive integrity/confidentiality found,
        or None if parsing fails.
    """
    if not isinstance(labels_data, dict):
        return None
    
    # Priority fields to check (user-controlled content that may be untrusted)
    priority_fields = ["body", "title", "content", "message", "text", "description"]
    
    # GitHub MCP uses "low" for untrusted user content and "high" for system-controlled
    # Map GitHub MCP integrity values to our IntegrityLabel enum
    integrity_map = {
        "low": IntegrityLabel.UNTRUSTED,
        "medium": IntegrityLabel.UNTRUSTED,  # Treat medium as untrusted for safety
        "high": IntegrityLabel.TRUSTED,
    }
    
    # Initialize with most permissive labels; we'll tighten them based on field values
    most_restrictive_integrity = IntegrityLabel.TRUSTED
    most_restrictive_confidentiality = ConfidentialityLabel.PUBLIC
    
    def parse_confidentiality_from_readers(conf_value: Any) -> ConfidentialityLabel:
        """Parse confidentiality from GitHub's readers lattice format.
        
        GitHub MCP uses a readers lattice:
        - ["public"] means anyone can read → PUBLIC
        - ["user_id_1", "user_id_2", ...] means only those users → PRIVATE
        """
        if isinstance(conf_value, list):
            if len(conf_value) == 1 and conf_value[0].lower() == "public":
                return ConfidentialityLabel.PUBLIC
            elif len(conf_value) > 0:
                # Non-empty list of user IDs = private/restricted access
                return ConfidentialityLabel.PRIVATE
            else:
                # Empty list - treat as public
                return ConfidentialityLabel.PUBLIC
        elif isinstance(conf_value, str):
            if conf_value.lower() == "public":
                return ConfidentialityLabel.PUBLIC
            elif conf_value.lower() in ("private", "internal", "confidential"):
                return ConfidentialityLabel.PRIVATE
            elif conf_value.lower() == "user_identity":
                return ConfidentialityLabel.USER_IDENTITY
        # Default to public
        return ConfidentialityLabel.PUBLIC
    
    # First check priority fields (user-controlled content)
    for field in priority_fields:
        if field in labels_data:
            field_label = labels_data[field]
            if isinstance(field_label, dict):
                # Parse integrity
                integrity_str = field_label.get("integrity", "").lower()
                if integrity_str in integrity_map:
                    field_integrity = integrity_map[integrity_str]
                    # UNTRUSTED is more restrictive than TRUSTED
                    if field_integrity == IntegrityLabel.UNTRUSTED:
                        most_restrictive_integrity = IntegrityLabel.UNTRUSTED
                
                # Parse confidentiality using readers lattice
                conf_value = field_label.get("confidentiality")
                field_conf = parse_confidentiality_from_readers(conf_value)
                # Higher confidentiality is more restrictive
                if field_conf.value > most_restrictive_confidentiality.value:
                    most_restrictive_confidentiality = field_conf
    
    # Also check all other fields for completeness
    for field, field_label in labels_data.items():
        if field not in priority_fields and isinstance(field_label, dict):
            # Parse integrity
            integrity_str = field_label.get("integrity", "").lower()
            if integrity_str in integrity_map:
                field_integrity = integrity_map[integrity_str]
                if field_integrity == IntegrityLabel.UNTRUSTED:
                    most_restrictive_integrity = IntegrityLabel.UNTRUSTED
            
            # Parse confidentiality using readers lattice
            conf_value = field_label.get("confidentiality")
            if conf_value is not None:
                field_conf = parse_confidentiality_from_readers(conf_value)
                if field_conf.value > most_restrictive_confidentiality.value:
                    most_restrictive_confidentiality = field_conf
    
    return ContentLabel(
        integrity=most_restrictive_integrity,
        confidentiality=most_restrictive_confidentiality,
        metadata={"source": "github_mcp_labels"},
    )


class LabelTrackingFunctionMiddleware(FunctionMiddleware):
    """Middleware that tracks and propagates security labels through tool invocations.
    
    Tiered Label Propagation:
    The result label of a tool call is determined by a strict 3-tier priority:
    
    +----------+------------------------------------------+----------------------------+
    | Priority | Source                                   | When used                  |
    +==========+==========================================+============================+
    | Tier 1   | Per-item embedded labels in the result   | Always wins if present     |
    |          | (additional_properties.security_label)    |                            |
    +----------+------------------------------------------+----------------------------+
    | Tier 2   | Tool's source_integrity declaration       | No embedded labels         |
    +----------+------------------------------------------+----------------------------+
    | Tier 3   | Join (combine_labels) of input arg labels| No embedded labels AND     |
    |          |                                          | no source_integrity        |
    +----------+------------------------------------------+----------------------------+
    
    Tools can declare their source_integrity in additional_properties:
    - source_integrity="trusted": Tool produces trusted data (e.g., internal computation)
    - source_integrity="untrusted": Tool fetches external/untrusted data
    - (not set): Falls back to tier 3 (input label join), or UNTRUSTED if no inputs
    
    This middleware:
    1. Extracts labels from tool input arguments (tier 3 input)
    2. Checks tool's source_integrity declaration (tier 2)
    3. Executes the tool
    4. Checks for per-item embedded labels in the result (tier 1 — highest priority)
    5. Falls back to tier 2 or tier 3 when no embedded labels exist
    6. Maintains confidentiality labels based on tool declarations
    7. Automatically hides untrusted content using variable indirection
    
    Attributes:
        default_integrity: Default integrity for tools without source_integrity declaration.
        default_confidentiality: The default confidentiality label for tool results.
        auto_hide_untrusted: Whether to automatically hide untrusted results.
        hide_threshold: The integrity level at which to hide content.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import Agent, LabelTrackingFunctionMiddleware
            
            # Create agent with automatic hiding enabled
            middleware = LabelTrackingFunctionMiddleware(
                auto_hide_untrusted=True  # Enabled by default
            )
            agent = Agent(
                client=client,
                name="assistant",
                middleware=[middleware]
            )
            
            # Run agent - untrusted tool results are automatically hidden
            response = await agent.run(messages=[{"role": "user", "content": "What's the weather?"}])
    """
    
    def __init__(
        self,
        default_integrity: IntegrityLabel = IntegrityLabel.UNTRUSTED,
        default_confidentiality: ConfidentialityLabel = ConfidentialityLabel.PUBLIC,
        auto_hide_untrusted: bool = True,
        hide_threshold: IntegrityLabel = IntegrityLabel.UNTRUSTED,
    ) -> None:
        """Initialize LabelTrackingFunctionMiddleware.
        
        Args:
            default_integrity: Default integrity label for tools without source_integrity. 
                Defaults to UNTRUSTED for safety (tools must opt-in to TRUSTED).
            default_confidentiality: Default confidentiality label. Defaults to PUBLIC.
            auto_hide_untrusted: Whether to automatically hide untrusted results. Defaults to True.
            hide_threshold: The integrity level at which to hide content. Defaults to UNTRUSTED.
        """
        self.default_integrity = default_integrity
        self.default_confidentiality = default_confidentiality
        self.auto_hide_untrusted = auto_hide_untrusted
        self.hide_threshold = hide_threshold
        
        # Context-level security label that tracks the cumulative security state
        # Starts as TRUSTED + PUBLIC and gets updated based on content added to context
        self._context_label = ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.PUBLIC,
            metadata={"initialized": True}
        )
        
        # Stateful variable store for this middleware instance
        self._variable_store = ContentVariableStore()
        
        # Metadata about stored variables
        self._variable_metadata: dict[str, dict[str, Any]] = {}
        
        # Phase 1: Message-level label tracking
        # Maps message index to its security label
        self._message_labels: dict[int, ContentLabel] = {}
        
        # Phase 2: Content lineage tracking
        # Maps content_id to its lineage
        self._content_lineage: dict[str, ContentLineage] = {}
    
    def get_context_label(self) -> ContentLabel:
        """Get the current context-level security label.
        
        The context label represents the cumulative security state of the conversation.
        It starts as TRUSTED + PUBLIC and gets "tainted" as untrusted or private
        content is added to the context.
        
        Returns:
            The current context security label.
        """
        return self._context_label
    
    def reset_context_label(self) -> None:
        """Reset the context label to initial state (TRUSTED + PUBLIC).
        
        Call this when starting a new conversation or session.
        """
        self._context_label = ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.PUBLIC,
            metadata={"reset": True}
        )
        # Also reset message labels and lineage for new conversation
        self._message_labels.clear()
        self._content_lineage.clear()
        logger.info("Context label reset to TRUSTED + PUBLIC")
    
    # ========== Phase 1: Message-Level Label Tracking ==========
    
    def label_message(
        self,
        message_index: int,
        label: ContentLabel,
        source_labels: list[ContentLabel] | None = None,
    ) -> None:
        """Assign a security label to a message in the conversation.
        
        Args:
            message_index: The index of the message in the conversation.
            label: The security label to assign.
            source_labels: Optional list of labels that contributed to this message.
        """
        self._message_labels[message_index] = label
        logger.debug(
            f"Labeled message {message_index}: "
            f"{label.integrity.value}/{label.confidentiality.value}"
        )
    
    def get_message_label(self, message_index: int) -> ContentLabel | None:
        """Get the security label of a specific message.
        
        Args:
            message_index: The index of the message.
        
        Returns:
            The message's ContentLabel, or None if not labeled.
        """
        return self._message_labels.get(message_index)
    
    def label_messages(self, messages: list[dict[str, Any]]) -> list[LabeledMessage]:
        """Label a list of messages based on their roles and content.
        
        This method automatically assigns labels to messages:
        - user/system messages: TRUSTED
        - assistant messages: Inherit from source labels or TRUSTED
        - tool messages: UNTRUSTED (external data)
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
        
        Returns:
            List of LabeledMessage objects.
        """
        labeled = []
        for i, msg in enumerate(messages):
            # Check if message already has a label
            existing_label = self._message_labels.get(i)
            
            labeled_msg = LabeledMessage(
                role=msg.get("role", "unknown"),
                content=msg.get("content", ""),
                security_label=existing_label,  # Will auto-infer if None
                message_index=i,
            )
            
            # Store the label
            self._message_labels[i] = labeled_msg.security_label
            labeled.append(labeled_msg)
        
        return labeled
    
    def get_all_message_labels(self) -> dict[int, ContentLabel]:
        """Get all message labels.
        
        Returns:
            Dictionary mapping message index to ContentLabel.
        """
        return dict(self._message_labels)
    
    # ========== Phase 2: Content Lineage Tracking ==========
    
    def track_lineage(
        self,
        content_id: str,
        derived_from: list[str],
        transformation: str,
        combined_label: ContentLabel,
        metadata: dict[str, Any] | None = None,
    ) -> ContentLineage:
        """Track the lineage of derived content.
        
        When content is transformed (e.g., summarized by quarantined_llm),
        this method records its derivation history for label propagation.
        
        Args:
            content_id: Unique identifier for the derived content.
            derived_from: List of source content/variable IDs.
            transformation: Type of transformation (e.g., "llm_summary").
            combined_label: The combined label from all sources.
            metadata: Optional additional metadata.
        
        Returns:
            The created ContentLineage object.
        """
        lineage = ContentLineage(
            content_id=content_id,
            derived_from=derived_from,
            transformation=transformation,
            combined_label=combined_label,
            metadata=metadata,
        )
        self._content_lineage[content_id] = lineage
        logger.info(
            f"Tracked lineage for {content_id}: derived from {derived_from} "
            f"via {transformation}, label={combined_label.integrity.value}"
        )
        return lineage
    
    def get_lineage(self, content_id: str) -> ContentLineage | None:
        """Get the lineage of content by its ID.
        
        Args:
            content_id: The content identifier.
        
        Returns:
            The ContentLineage, or None if not tracked.
        """
        return self._content_lineage.get(content_id)
    
    def get_all_lineage(self) -> dict[str, ContentLineage]:
        """Get all tracked content lineage.
        
        Returns:
            Dictionary mapping content_id to ContentLineage.
        """
        return dict(self._content_lineage)
    
    def _update_context_label(self, new_content_label: ContentLabel) -> None:
        """Update the context label based on new content added to the context.
        
        The context label is updated using the most restrictive policy:
        - If new content is UNTRUSTED, context becomes UNTRUSTED
        - If new content has higher confidentiality, context inherits it
        
        Args:
            new_content_label: The label of the new content being added to context.
        """
        old_label = self._context_label
        self._context_label = combine_labels(self._context_label, new_content_label)
        
        if old_label.integrity != self._context_label.integrity:
            logger.info(
                f"Context integrity changed: {old_label.integrity.value} -> "
                f"{self._context_label.integrity.value}"
            )
        if old_label.confidentiality != self._context_label.confidentiality:
            logger.info(
                f"Context confidentiality changed: {old_label.confidentiality.value} -> "
                f"{self._context_label.confidentiality.value}"
            )
    
    def _get_input_labels(self, context: FunctionInvocationContext) -> list[ContentLabel]:
        """Extract security labels from tool input arguments.
        
        Recursively inspects the arguments passed to a tool to find any
        VariableReferenceContent objects or labeled data, and collects their labels.
        
        These labels are used as the tier-3 fallback (lowest priority) when
        neither embedded labels nor a source_integrity declaration are present.
        
        Args:
            context: The function invocation context containing arguments.
        
        Returns:
            List of ContentLabel objects found in the arguments.
        """
        from pydantic import BaseModel
        
        labels: list[ContentLabel] = []
        
        def _extract_labels_recursive(value: Any) -> None:
            """Recursively extract labels from a value."""
            if isinstance(value, VariableReferenceContent):
                # VariableReferenceContent has an embedded label
                labels.append(value.label)
                logger.debug(f"Found label from VariableReferenceContent: {value.variable_id}")
            elif isinstance(value, BaseModel):
                # Handle Pydantic models by converting to dict
                _extract_labels_recursive(value.model_dump())
            elif isinstance(value, dict):
                # Check for security_label field (preferred) or label field (legacy)
                if "security_label" in value:
                    label_data = value["security_label"]
                    if isinstance(label_data, ContentLabel):
                        labels.append(label_data)
                    elif isinstance(label_data, dict):
                        try:
                            labels.append(ContentLabel.from_dict(label_data))
                        except Exception:
                            pass
                # Fall back to "label" for backward compatibility
                elif "label" in value and isinstance(value.get("label"), dict):
                    try:
                        labels.append(ContentLabel.from_dict(value["label"]))
                    except Exception:
                        pass
                # Recurse into dict values
                for v in value.values():
                    _extract_labels_recursive(v)
            elif isinstance(value, (list, tuple)):
                # Recurse into list/tuple items
                for item in value:
                    _extract_labels_recursive(item)
        
        # Extract labels from context.arguments (tool call arguments)
        if context.arguments:
            _extract_labels_recursive(context.arguments)
        
        # Also check kwargs for any labeled data
        if context.kwargs:
            _extract_labels_recursive(context.kwargs)
        
        return labels
    
    def _get_source_integrity(self, context: FunctionInvocationContext) -> IntegrityLabel | None:
        """Get the source_integrity declaration from a tool's additional_properties.
        
        Tools that fetch external/untrusted data should declare source_integrity: "untrusted".
        Pure transformation tools may omit this property.
        
        Args:
            context: The function invocation context.
        
        Returns:
            IntegrityLabel if declared, None if not declared.
        """
        function_props = getattr(context.function, "additional_properties", None) or {}
        source_integrity_str = function_props.get("source_integrity", None)
        
        if source_integrity_str is not None:
            try:
                return IntegrityLabel(source_integrity_str)
            except ValueError:
                logger.warning(
                    f"Invalid source_integrity '{source_integrity_str}' for function "
                    f"'{context.function.name}', ignoring"
                )
        return None
    
    # ========== Helper utilities ==========
    
    @staticmethod
    def _ensure_content_list(result: Any) -> list[Content]:
        """Normalize any result value to ``list[Content]``.

        After ``call_next()``, ``context.result`` is typically ``list[Content]``
        from ``FunctionTool.invoke()``.  This helper handles legacy cases where
        middleware or tests set raw strings, dicts, or single ``Content`` items.

        Args:
            result: The raw result value.

        Returns:
            A ``list[Content]`` suitable for uniform processing.
        """
        import json as _json

        if isinstance(result, list) and all(isinstance(c, Content) for c in result):
            return result
        if isinstance(result, Content):
            return [result]
        if isinstance(result, str):
            return [Content.from_text(result)]
        try:
            text = _json.dumps(result, default=str)
        except (TypeError, ValueError):
            text = str(result)
        return [Content.from_text(text)]

    def _should_hide(self, label: ContentLabel) -> bool:
        """Decide whether a Content item with *label* should be hidden.

        An item is hidden when **all three** conditions hold:
        1. ``auto_hide_untrusted`` is enabled.
        2. The item's integrity matches the ``hide_threshold`` (UNTRUSTED).
        3. The conversation context is still TRUSTED (no point hiding if context
           is already tainted).
        """
        return (
            self.auto_hide_untrusted
            and label.integrity == self.hide_threshold
            and self._context_label.integrity == IntegrityLabel.TRUSTED
        )

    @staticmethod
    def _is_variable_reference(item: Content) -> bool:
        """Return True if *item* is a hidden variable-reference placeholder."""
        if not (isinstance(item, Content) and item.type == "text"):
            return False
        props = item.additional_properties or {}
        return bool(props.get("_variable_reference"))

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Process function invocation with tiered label propagation.
        
        Label propagation follows a strict 3-tier priority for determining the
        result label of a tool call:
        
        1. **Tier 1 (Highest)**: Per-item embedded labels in the tool result
           (``additional_properties.security_label``). If present, these labels
           are used directly for each item.
        2. **Tier 2**: The tool's ``source_integrity`` declaration. If the tool
           explicitly declares ``source_integrity`` in its ``additional_properties``,
           that declaration alone determines the fallback label (input argument
           labels are NOT combined in).
        3. **Tier 3 (Lowest)**: The join (``combine_labels``) of all input argument
           labels. Used only when there are no embedded labels AND no
           ``source_integrity`` declaration.
        
        Two metadata keys are set on the context:
        
        - ``context.metadata["result_label"]``: The security label of THIS tool
          call's result (per-call). Set once after result processing.
        - ``context.metadata["context_label"]``: The cumulative conversation
          security state (cross-call). Used by ``PolicyEnforcementFunctionMiddleware``
          to validate subsequent tool calls.
        
        Args:
            context: The function invocation context.
            call_next: Callback to continue to next middleware or function execution.
        """
        # Set thread-local middleware reference for tools to access
        _current_middleware.instance = self
        
        try:
            function_name = context.function.name
            
            # ========== Tiered Label Propagation ==========
            # Step 1: Extract labels from input arguments
            input_labels = self._get_input_labels(context)
            
            # Step 2: Get tool's source_integrity declaration (may be None)
            declared_source_integrity = self._get_source_integrity(context)
            
            # Get confidentiality from function additional_properties or use default
            confidentiality = self._get_function_confidentiality(context)
            
            # Step 3: Build tiered fallback_label
            # This label is used for result items that have NO embedded labels.
            # Priority: source_integrity declaration (tier 2) > input labels join (tier 3)
            if declared_source_integrity is not None:
                # Tier 2: Tool explicitly declared source_integrity — use it alone.
                # Input argument labels are NOT combined in; the tool's declaration
                # is authoritative for the trust level of its output.
                fallback_label = ContentLabel(
                    integrity=declared_source_integrity,
                    confidentiality=confidentiality,
                    metadata={"source": "source_integrity", "function_name": function_name}
                )
            elif input_labels:
                # Tier 3: No source_integrity declared — join all input labels.
                combined = combine_labels(*input_labels)
                fallback_label = ContentLabel(
                    integrity=combined.integrity,
                    confidentiality=confidentiality,
                    metadata={"source": "input_labels_join", "function_name": function_name}
                )
            else:
                # Tier 3 fallback: No source_integrity AND no input labels.
                # Default to UNTRUSTED for safety.
                fallback_label = ContentLabel(
                    integrity=self.default_integrity,
                    confidentiality=confidentiality,
                    metadata={"source": "default", "function_name": function_name}
                )
            
            # context_label: cumulative conversation security state (cross-call).
            # Used by PolicyEnforcementFunctionMiddleware to validate tool calls.
            context.metadata["context_label"] = self._context_label
            
            logger.info(
                f"Tool call '{function_name}' fallback label (tiered): "
                f"{fallback_label.integrity.value}, {fallback_label.confidentiality.value} "
                f"(inputs: {len(input_labels)}, source_integrity: "
                f"{declared_source_integrity.value if declared_source_integrity else 'not declared'})"
            )
            logger.info(
                f"Current context label: {self._context_label.integrity.value}, "
                f"{self._context_label.confidentiality.value}"
            )
            
            # Execute the function
            await call_next()
            
            # If middleware set a function_approval_request (e.g., policy violation approval),
            # skip all result processing and let it pass through unchanged
            if isinstance(context.result, Content) and context.result.type == "function_approval_request":
                logger.info(
                    f"Tool '{function_name}' returned function_approval_request - "
                    f"skipping result processing"
                )
                return
            
            # Label, hide, and update context label for the tool result
            self._label_result(context, function_name, fallback_label)
        finally:
            # Clear thread-local reference
            _current_middleware.instance = None
    
    def _label_result(
        self,
        context: FunctionInvocationContext,
        function_name: str,
        fallback_label: ContentLabel,
    ) -> None:
        """Label, optionally hide, and update context label for a tool result.
        
        Performs all post-call result processing in a single method:
        
        1. Normalise ``context.result`` to ``list[Content]``.
        2. Process per-item embedded labels (tier 1 overrides fallback).
        3. Store the combined result label in ``context.metadata["result_label"]``.
        4. Update the conversation-level context label, taking care to skip
           integrity tainting when the entire result was hidden behind
           variable references.
        
        Args:
            context: The function invocation context (result is read/written).
            function_name: Name of the function that produced the result.
            fallback_label: Tiered fallback label (tier 2 or tier 3).
        """
        if context.result is None:
            context.metadata["result_label"] = fallback_label
            return
        
        original_items = self._ensure_content_list(context.result)
        
        # Process items — apply per-item labels + hide untrusted items
        processed, result_label = self._process_result_with_embedded_labels(
            original_items,
            function_name,
            fallback_label=fallback_label,
        )
        
        context.result = processed
        context.metadata["result_label"] = result_label
        
        # Determine whether the entire result was hidden (all items became
        # variable references that were NOT variable references before).
        entire_result_hidden = (
            all(self._is_variable_reference(item) for item in processed)
            and not all(self._is_variable_reference(item) for item in original_items)
        )
        
        if entire_result_hidden:
            # Untrusted content is NOT in the LLM context — don't taint integrity.
            # However, confidentiality MUST be updated: even hidden PRIVATE data
            # could be revealed by approving the variable reference.
            if result_label.confidentiality != self._context_label.confidentiality:
                old_conf = self._context_label.confidentiality
                hidden_label = ContentLabel(
                    integrity=self._context_label.integrity,
                    confidentiality=result_label.confidentiality,
                )
                self._update_context_label(hidden_label)
                logger.info(
                    f"Result from '{function_name}' hidden (integrity clean) but "
                    f"confidentiality updated: {old_conf.value} -> "
                    f"{result_label.confidentiality.value}"
                )
            else:
                logger.info(
                    f"Result from '{function_name}' fully hidden - context label "
                    f"unchanged: {self._context_label.integrity.value}, "
                    f"{self._context_label.confidentiality.value}"
                )
        else:
            # Some content entered context — update context label fully
            self._update_context_label(result_label)
            logger.info(
                f"Context label after processing '{function_name}': "
                f"{self._context_label.integrity.value}, "
                f"{self._context_label.confidentiality.value}"
            )
    
    def _get_function_confidentiality(self, context: FunctionInvocationContext) -> ConfidentialityLabel:
        """Get confidentiality label from function metadata.
        
        Args:
            context: The function invocation context.
        
        Returns:
            The confidentiality label for this function.
        """
        # Check function's additional_properties for confidentiality setting
        function_props = getattr(context.function, "additional_properties", None) or {}
        confidentiality_str = function_props.get("confidentiality", None)
        
        if confidentiality_str:
            try:
                return ConfidentialityLabel(confidentiality_str)
            except ValueError:
                logger.warning(
                    f"Invalid confidentiality label '{confidentiality_str}' "
                    f"for function '{context.function.name}', using default"
                )
        
        return self.default_confidentiality
    
    def _process_result_with_embedded_labels(
        self,
        items: list[Content],
        function_name: str,
        fallback_label: ContentLabel,
    ) -> tuple[list[Content], ContentLabel]:
        """Process Content items, respecting per-item embedded labels.
        
        This implements the first tier of the label propagation priority:
        items with embedded labels (``additional_properties.security_label``)
        use those labels directly. Items without embedded labels fall back to
        ``fallback_label``, which is either the tool's ``source_integrity``
        declaration (tier 2) or the join of input argument labels (tier 3).
        
        Each item's own label is attached to its ``additional_properties``
        during processing, preserving per-item granularity.
        
        Untrusted items are automatically hidden and replaced with Content
        items containing a variable reference.  Trusted items pass through unchanged.
        
        Args:
            items: A list of Content items (already normalised by caller via
                ``_ensure_content_list``).
            function_name: Name of the function that produced the result.
            fallback_label: Label to use when an item has no embedded label.
        
        Returns:
            Tuple of (processed_content_list, combined_label).
            - processed_content_list: list[Content] with untrusted items replaced
            - combined_label: Most restrictive label across all items
        """
        processed: list[Content] = []
        item_labels: list[ContentLabel] = []

        for item in items:
            item_label = self._extract_content_label(item, fallback_label)
            item_labels.append(item_label)

            if self._should_hide(item_label):
                hidden = self._hide_item(item, item_label, function_name)
                processed.append(hidden)
            else:
                # Attach this item's own label (preserves per-item granularity)
                item.additional_properties["security_label"] = item_label.to_dict()
                processed.append(item)

        combined = combine_labels(*item_labels) if item_labels else fallback_label
        return processed, combined

    def _extract_content_label(
        self,
        item: Content,
        fallback_label: ContentLabel,
    ) -> ContentLabel:
        """Extract the security label for a single Content item.
        
        Checks (in order):
        1. ``additional_properties.security_label`` (explicit label)
        2. ``additional_properties.labels`` (GitHub MCP format)
        3. Falls back to ``fallback_label``
        
        Args:
            item: The Content item to inspect.
            fallback_label: The label to use if no embedded label is found.
            
        Returns:
            The resolved ContentLabel for this item.
        """
        additional_props = item.additional_properties or {}

        # Check for standard security_label
        label_data = additional_props.get("security_label")
        if label_data and isinstance(label_data, dict):
            try:
                return ContentLabel.from_dict(label_data)
            except Exception as e:
                logger.warning(f"Failed to parse security_label from Content: {e}")

        # Check for GitHub MCP server labels format
        github_labels = additional_props.get("labels")
        if github_labels and isinstance(github_labels, (dict, list)):
            try:
                if isinstance(github_labels, list) and github_labels:
                    github_labels = github_labels[0] if isinstance(github_labels[0], dict) else {}
                item_label = _parse_github_mcp_labels(github_labels)
                if item_label:
                    logger.info(
                        f"Parsed GitHub MCP labels for Content item: "
                        f"integrity={item_label.integrity.value}, "
                        f"confidentiality={item_label.confidentiality.value}"
                    )
                    return item_label
            except Exception as e:
                logger.warning(f"Failed to parse GitHub MCP labels from Content: {e}")

        # No embedded label — use fallback
        return fallback_label

    def _hide_item(
        self,
        item: Content,
        label: ContentLabel,
        function_name: str,
    ) -> Content:
        """Replace an untrusted Content item with a variable-reference placeholder.
        
        The original content is stored in the variable store; the returned
        ``Content.from_text(...)`` contains the serialised variable reference
        and can be safely included in the LLM context.
        
        Args:
            item: The original Content item to hide.
            label: The security label for the item.
            function_name: Name of the function that produced the item.
            
        Returns:
            A Content item containing the variable reference.
        """
        import json as _json

        # Store the actual content (serialize Content to its text representation)
        if item.type == "text" and item.text is not None:
            stored_value = item.text
        else:
            stored_value = item.to_dict()

        var_id = self._variable_store.store(stored_value, label)

        # Store metadata about this variable
        self._variable_metadata[var_id] = {
            "function_name": function_name,
            "original_type": item.type,
            "timestamp": datetime.now().isoformat(),
        }

        # Create variable reference
        description = f"Result from {function_name}"
        var_ref = VariableReferenceContent(
            variable_id=var_id,
            label=label,
            description=description,
        )

        logger.info(
            f"Auto-hidden untrusted result from '{function_name}' "
            f"as variable {var_id}"
        )

        # Return as a Content item so it fits in list[Content]
        return Content.from_text(
            _json.dumps(var_ref.to_dict()),
            additional_properties={"_variable_reference": True, "security_label": label.to_dict()},
        )
    
    def get_variable_store(self) -> ContentVariableStore:
        """Get the variable store for this middleware instance.
        
        Returns:
            The ContentVariableStore instance.
        """
        return self._variable_store
    
    def get_variable_metadata(self, var_id: str) -> dict[str, Any] | None:
        """Get metadata for a stored variable.
        
        Args:
            var_id: The variable ID.
        
        Returns:
            Metadata dictionary or None if not found.
        """
        return self._variable_metadata.get(var_id)
    
    def list_variables(self) -> list[str]:
        """Get a list of all stored variable IDs.
        
        Returns:
            List of variable ID strings.
        """
        return self._variable_store.list_variables()
    
    def get_security_tools(self) -> list:
        """Get the list of security tools for agent integration.
        
        Returns security tools that can be passed to an agent's tools parameter.
        These tools enable the agent to safely work with hidden untrusted content.
        
        Returns:
            List containing quarantined_llm and inspect_variable tools.
        
        Examples:
            .. code-block:: python
            
                middleware = LabelTrackingFunctionMiddleware()
                
                agent = Agent(
                    client=client,
                    tools=[my_tool, *middleware.get_security_tools()],
                    middleware=[middleware],
                )
        """
        from ._security_tools import get_security_tools
        return get_security_tools()
    
    def get_security_instructions(self) -> str:
        """Get instructions explaining how to use security tools.
        
        Returns security instructions that should be appended to agent instructions
        to teach the agent how to work with hidden untrusted content.
        
        Returns:
            String containing security tool usage instructions.
        
        Examples:
            .. code-block:: python
            
                middleware = LabelTrackingFunctionMiddleware()
                
                agent = Agent(
                    client=client,
                    instructions=base_instructions + middleware.get_security_instructions(),
                    tools=[my_tool, *middleware.get_security_tools()],
                    middleware=[middleware],
                )
        """
        from ._security_tools import SECURITY_TOOL_INSTRUCTIONS
        return SECURITY_TOOL_INSTRUCTIONS
    
    def _set_as_current(self) -> None:
        """Set this middleware as the current thread-local instance.
        
        This is primarily for testing and debugging purposes.
        In normal operation, the middleware is automatically set during process().
        """
        _current_middleware.instance = self
    
    def _clear_current(self) -> None:
        """Clear the current thread-local middleware instance.
        
        This is primarily for testing and debugging purposes.
        In normal operation, the middleware is automatically cleared after process().
        """
        _current_middleware.instance = None


def get_current_middleware() -> LabelTrackingFunctionMiddleware | None:
    """Get the current middleware instance from thread-local storage.
    
    This function allows tools to access the middleware's variable store.
    
    Returns:
        The current LabelTrackingFunctionMiddleware instance, or None if not set.
    """
    return getattr(_current_middleware, 'instance', None)


class PolicyEnforcementFunctionMiddleware(FunctionMiddleware):
    """Middleware that enforces security policies on tool invocations.
    
    This middleware:
    1. Checks security labels before tool execution
    2. Blocks tools with untrusted inputs unless explicitly allowed
    3. Validates confidentiality requirements against tool permissions
    4. Logs and reports blocked attempts
    
    Attributes:
        allow_untrusted_tools: Set of tool names that can accept untrusted inputs.
        block_on_violation: Whether to block execution on policy violations.
        audit_log: List of policy violation events for audit purposes.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import Agent, PolicyEnforcementFunctionMiddleware
            
            # Create policy enforcement middleware
            policy = PolicyEnforcementFunctionMiddleware(
                allow_untrusted_tools={"search_web", "get_news"}
            )
            
            agent = Agent(
                client=client,
                name="assistant",
                middleware=[label_tracker, policy]  # Apply both middlewares
            )
    """
    
    def __init__(
        self,
        allow_untrusted_tools: set[str] | None = None,
        block_on_violation: bool = True,
        enable_audit_log: bool = True,
        approval_on_violation: bool = False,
    ) -> None:
        """Initialize PolicyEnforcementFunctionMiddleware.
        
        Args:
            allow_untrusted_tools: Set of tool names that can accept untrusted inputs.
            block_on_violation: Whether to block execution on policy violations.
                Ignored if approval_on_violation is True.
            enable_audit_log: Whether to maintain an audit log of violations.
            approval_on_violation: Whether to request user approval instead of blocking
                when a policy violation is detected. If True, the middleware will return
                a special result that triggers an approval request in the UI. After user
                approval, the tool will execute with a warning about untrusted context.
        """
        self.allow_untrusted_tools = allow_untrusted_tools or set()
        self.approval_on_violation = approval_on_violation
        # If approval_on_violation is True, we don't block - we request approval instead
        self.block_on_violation = block_on_violation if not approval_on_violation else False
        self.enable_audit_log = enable_audit_log
        self.audit_log: list[dict[str, Any]] = []
        # Track approved violations by call_id (after user approves)
        self._approved_violations: set[str] = set()
        # Track call_ids for which we sent approval requests (pending approval)
        self._pending_policy_approvals: set[str] = set()
    
    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Process function invocation with policy enforcement.
        
        Policy enforcement uses the context_label (cumulative security state of the
        conversation) to validate tool calls. This prevents indirect attacks where
        untrusted content from previous tool calls could influence dangerous operations.
        
        Args:
            context: The function invocation context.
            call_next: Callback to continue to next middleware or function execution.
        """
        function_name = context.function.name
        
        # Get the context label (cumulative security state of the conversation)
        # This is set by LabelTrackingFunctionMiddleware and represents the
        # combined security state of all content that has entered the context
        context_label_data = context.metadata.get("context_label")
        
        if context_label_data is None:
            logger.warning(
                f"No context label found for tool '{function_name}'. "
                "Ensure LabelTrackingFunctionMiddleware runs before PolicyEnforcementFunctionMiddleware."
            )
            # Continue execution without policy check
            await call_next()
            return
        
        # Convert context label to ContentLabel if it's a dict
        if isinstance(context_label_data, dict):
            context_label = ContentLabel.from_dict(context_label_data)
        elif isinstance(context_label_data, ContentLabel):
            context_label = context_label_data
        else:
            logger.error(f"Invalid context label type: {type(context_label_data)}")
            await call_next()
            return
        
        logger.debug(
            f"Policy enforcement for '{function_name}': "
            f"context_label={context_label.integrity.value}/{context_label.confidentiality.value}"
        )
        
        # Check integrity policy based on context label
        # If context is UNTRUSTED (tainted), check if tool allows untrusted context
        if context_label.integrity == IntegrityLabel.UNTRUSTED:
            if function_name not in self.allow_untrusted_tools:
                # Also check if tool explicitly accepts untrusted via additional_properties
                function_props = getattr(context.function, "additional_properties", None) or {}
                accepts_untrusted = function_props.get("accepts_untrusted", False)
                
                if not accepts_untrusted:
                    violation = {
                        "type": "untrusted_context",
                        "function": function_name,
                        "context_label": context_label.to_dict(),
                        "turn": context.metadata.get("turn_number", -1),
                        "reason": "Context is UNTRUSTED and tool does not accept untrusted inputs",
                    }
                    
                    self._log_violation(violation)
                    
                    # Check if this specific call was previously approved
                    call_id = context.metadata.get("call_id", "")
                    policy_approved = context.metadata.get("policy_approval_granted", False)
                    
                    # Check for explicit approval:
                    # 1. policy_approval_granted from metadata (set by _tools.py)
                    # 2. call_id in _approved_violations (persisted approvals)
                    # Note: _pending_policy_approvals only prevents duplicate requests,
                    # it does NOT grant approval.
                    is_approved = (
                        policy_approved
                        or call_id in self._approved_violations
                    )
                    
                    if is_approved:
                        # User approved this violation - proceed with warning
                        logger.warning(
                            f"APPROVED BY USER: Tool '{function_name}' executing in UNTRUSTED context. "
                            f"User acknowledged the security risk and approved execution."
                        )
                        self._approved_violations.add(call_id)
                        self._pending_policy_approvals.discard(call_id)  # Clear pending status
                        # Continue execution but mark context as user-approved
                        context.metadata["user_approved_violation"] = True
                    elif self.approval_on_violation:
                        # Request user approval instead of blocking
                        # Create function_approval_request Content directly in middleware
                        logger.info(
                            f"APPROVAL REQUESTED: Tool '{function_name}' requires user approval "
                            f"due to UNTRUSTED context."
                        )
                        from ._types import Content
                        
                        # Track that we're requesting approval for this call_id
                        self._pending_policy_approvals.add(call_id)
                        
                        # Reconstruct function_call Content from context
                        func_call = Content.from_function_call(
                            call_id=call_id,
                            name=function_name,
                            arguments=context.arguments.model_dump() if hasattr(context.arguments, 'model_dump') else dict(context.arguments),
                        )
                        
                        reason = (
                            f"Tool '{function_name}' is being called in an UNTRUSTED context. "
                            f"The conversation contains data from untrusted sources which could "
                            f"influence this operation. Approve to proceed anyway (the agent will "
                            f"continue with a warning about untrusted context)."
                        )
                        
                        context.result = Content.from_function_approval_request(
                            id=call_id,
                            function_call=func_call,
                            additional_properties={
                                "policy_violation": True,
                                "violation_type": "untrusted_context",
                                "reason": reason,
                                "context_label": context_label.to_dict(),
                            },
                        )
                        context.terminate = True
                        return
                    elif self.block_on_violation:
                        logger.warning(
                            f"BLOCKED: Tool '{function_name}' called in UNTRUSTED context. "
                            f"Context became untrusted due to previous tool results. "
                            f"Add to allow_untrusted_tools or set accepts_untrusted=True to permit."
                        )
                        context.result = {
                            "error": "Policy violation: Tool cannot be called in untrusted context",
                            "function": function_name,
                            "context_label": context_label.to_dict(),
                        }
                        context.terminate = True
                        return
                    else:
                        logger.warning(
                            f"WARNING: Tool '{function_name}' called in UNTRUSTED context (allowed)"
                        )
        
        # Check confidentiality policy based on context label
        conf_result = self._check_confidentiality_policy_detailed(context, context_label)
        if not conf_result["passed"]:
            violation = {
                "type": "confidentiality_violation",
                "subtype": conf_result["failure_type"],
                "function": function_name,
                "context_label": context_label.to_dict(),
                "reason": conf_result["reason"],
                "turn": context.metadata.get("turn_number", -1),
            }
            
            self._log_violation(violation)
            
            # Check if this specific call was previously approved
            call_id = context.metadata.get("call_id", "")
            policy_approved = context.metadata.get("policy_approval_granted", False)
            
            # Check for explicit approval:
            # 1. policy_approval_granted from metadata (set by _tools.py)
            # 2. call_id in _approved_violations (persisted approvals)
            # Note: _pending_policy_approvals only prevents duplicate requests,
            # it does NOT grant approval.
            is_approved = (
                policy_approved
                or call_id in self._approved_violations
            )
            
            if is_approved:
                # User approved this violation - proceed with warning
                logger.warning(
                    f"APPROVED BY USER: Tool '{function_name}' executing despite confidentiality "
                    f"violation. User acknowledged the security risk and approved execution."
                )
                self._approved_violations.add(call_id)
                self._pending_policy_approvals.discard(call_id)  # Clear pending status
                context.metadata["user_approved_violation"] = True
            elif self.approval_on_violation:
                # Request user approval instead of blocking
                logger.info(
                    f"APPROVAL REQUESTED: Tool '{function_name}' requires user approval "
                    f"due to confidentiality policy violation."
                )
                from ._types import Content
                
                # Track that we're requesting approval for this call_id
                self._pending_policy_approvals.add(call_id)
                
                # Reconstruct function call content from context
                func_call = Content.from_function_call(
                    call_id=call_id,
                    name=function_name,
                    arguments=context.arguments.model_dump() if hasattr(context.arguments, 'model_dump') else dict(context.arguments),
                )
                
                reason = (
                    f"Tool '{function_name}' violates confidentiality policy: "
                    f"{conf_result['reason']}. Approve to proceed anyway."
                )
                
                context.result = Content.from_function_approval_request(
                    id=call_id,
                    function_call=func_call,
                    additional_properties={
                        "policy_violation": True,
                        "violation_type": conf_result["failure_type"],
                        "reason": reason,
                        "context_label": context_label.to_dict(),
                    },
                )
                context.terminate = True
                return
            elif self.block_on_violation:
                logger.warning(
                    f"BLOCKED: Tool '{function_name}' violates confidentiality policy: "
                    f"{conf_result['reason']}"
                )
                context.result = {
                    "error": f"Policy violation: {conf_result['reason']}",
                    "function": function_name,
                    "context_label": context_label.to_dict(),
                    "violation_type": conf_result["failure_type"],
                }
                context.terminate = True
                return
        
        # Policy check passed, continue execution
        logger.debug(f"Policy check passed for tool '{function_name}'")
        await call_next()
    
    def _check_confidentiality_policy(
        self,
        context: FunctionInvocationContext,
        label: ContentLabel,
    ) -> bool:
        """Check if confidentiality requirements are met.
        
        This method enforces confidentiality policy via **max_allowed_confidentiality**
        (output restriction): The maximum confidentiality level allowed in context when
        calling this tool. Used to prevent data exfiltration (e.g., "cannot write PRIVATE
        data to PUBLIC destination").
        
        Args:
            context: The function invocation context.
            label: The security label to check (typically context label).
        
        Returns:
            True if policy is satisfied, False otherwise.
        """
        return self._check_confidentiality_policy_detailed(context, label)["passed"]
    
    def _check_confidentiality_policy_detailed(
        self,
        context: FunctionInvocationContext,
        label: ContentLabel,
    ) -> dict[str, Any]:
        """Check confidentiality policy and return detailed results.
        
        Args:
            context: The function invocation context.
            label: The security label to check (typically context label).
        
        Returns:
            Dict with keys: passed (bool), failure_type (str), reason (str).
        """
        function_props = getattr(context.function, "additional_properties", None) or {}
        
        conf_hierarchy = {
            ConfidentialityLabel.PUBLIC: 0,
            ConfidentialityLabel.PRIVATE: 1,
            ConfidentialityLabel.USER_IDENTITY: 2,
        }
        
        # Check max_allowed_confidentiality (output restriction / data exfiltration prevention)
        # Context confidentiality must be <= max allowed level
        # This prevents PRIVATE data from being written to PUBLIC destinations
        max_allowed_conf = function_props.get("max_allowed_confidentiality", None)
        if max_allowed_conf is not None:
            try:
                max_allowed_level = ConfidentialityLabel(max_allowed_conf)
                if conf_hierarchy[label.confidentiality] > conf_hierarchy[max_allowed_level]:
                    return {
                        "passed": False,
                        "failure_type": "max_allowed_confidentiality",
                        "reason": (
                            f"Cannot write {label.confidentiality.value.upper()} data to "
                            f"{max_allowed_level.value.upper()} destination (data exfiltration blocked)"
                        ),
                    }
            except ValueError:
                logger.warning(f"Invalid max_allowed_confidentiality: {max_allowed_conf}")
        
        return {"passed": True, "failure_type": None, "reason": None}
    
    def _log_violation(self, violation: dict[str, Any]) -> None:
        """Log a policy violation.
        
        Args:
            violation: Dictionary containing violation details.
        """
        if self.enable_audit_log:
            self.audit_log.append(violation)
        
        logger.warning(f"Policy violation detected: {violation}")
    
    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get the audit log of policy violations.
        
        Returns:
            List of violation records.
        """
        return self.audit_log.copy()
    
    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self.audit_log.clear()


class SecureAgentConfig(BaseContextProvider):
    """Context provider for creating a secure agent with prompt injection defense.
    
    This class extends BaseContextProvider to automatically inject security tools
    and instructions into any agent via the context provider pipeline. Middleware
    must still be passed separately to the agent constructor.
    
    Attributes:
        label_tracker: The LabelTrackingFunctionMiddleware instance.
        policy_enforcer: Optional PolicyEnforcementFunctionMiddleware instance.
        auto_hide_untrusted: Whether to automatically hide untrusted content.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import Agent, SecureAgentConfig
            
            # Create security configuration (also a context provider)
            security = SecureAgentConfig(
                allow_untrusted_tools={"fetch_external_data"},
                block_on_violation=True,
            )
            
            # Create secure agent - tools and instructions injected automatically
            agent = Agent(
                client=client,
                instructions=base_instructions,
                tools=[my_tool],
                context_providers=[security],
                middleware=security.get_middleware(),
            )
    """
    
    DEFAULT_SOURCE_ID = "secure_agent"
    
    def __init__(
        self,
        auto_hide_untrusted: bool = True,
        default_integrity: IntegrityLabel = IntegrityLabel.UNTRUSTED,
        default_confidentiality: ConfidentialityLabel = ConfidentialityLabel.PUBLIC,
        allow_untrusted_tools: set[str] | None = None,
        block_on_violation: bool = True,
        approval_on_violation: bool = False,
        enable_audit_log: bool = True,
        enable_policy_enforcement: bool = True,
        quarantine_chat_client: "SupportsChatGetResponse | None" = None,
        source_id: str | None = None,
    ) -> None:
        """Initialize secure agent configuration.
        
        Args:
            auto_hide_untrusted: Whether to automatically hide UNTRUSTED content.
            default_integrity: Default integrity label for tool calls.
            default_confidentiality: Default confidentiality label for tool calls.
            allow_untrusted_tools: Set of tool names that can accept untrusted inputs.
            block_on_violation: Whether to block execution on policy violations.
                Ignored if approval_on_violation is True.
            approval_on_violation: Whether to request user approval instead of blocking
                when a policy violation is detected. If True, the middleware will return
                a special result that triggers an approval request in the UI. After user
                approval, the tool will execute with a warning about untrusted context.
            enable_audit_log: Whether to enable audit logging.
            enable_policy_enforcement: Whether to enable policy enforcement middleware.
            quarantine_chat_client: Optional chat client for real LLM calls in quarantined_llm.
                If provided, the quarantined_llm tool will make actual isolated LLM calls
                instead of returning placeholder responses. This client should ideally be
                a separate instance using a cheaper model (e.g., gpt-4o-mini) since it
                processes untrusted content.
            source_id: Optional source identifier for context provider attribution.
                Defaults to "secure_agent".
        """
        super().__init__(source_id or self.DEFAULT_SOURCE_ID)
        
        self.label_tracker = LabelTrackingFunctionMiddleware(
            auto_hide_untrusted=auto_hide_untrusted,
            default_integrity=default_integrity,
            default_confidentiality=default_confidentiality,
        )
        
        self.enable_policy_enforcement = enable_policy_enforcement
        if enable_policy_enforcement:
            # Always allow security tools to accept untrusted inputs
            tools_allowing_untrusted = {"quarantined_llm", "inspect_variable"}
            if allow_untrusted_tools:
                tools_allowing_untrusted.update(allow_untrusted_tools)
            
            self.policy_enforcer = PolicyEnforcementFunctionMiddleware(
                allow_untrusted_tools=tools_allowing_untrusted,
                block_on_violation=block_on_violation,
                approval_on_violation=approval_on_violation,
                enable_audit_log=enable_audit_log,
            )
        else:
            self.policy_enforcer = None
        
        # Store and configure quarantine client for real LLM calls
        self._quarantine_chat_client = quarantine_chat_client
        if quarantine_chat_client is not None:
            from ._security_tools import set_quarantine_client
            set_quarantine_client(quarantine_chat_client)
            logger.info("Quarantine chat client configured for real LLM calls")
    
    async def before_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """Inject security tools and instructions before model invocation.
        
        This method is called automatically by the agent framework when
        SecureAgentConfig is used as a context provider.
        
        Args:
            agent: The agent running this invocation.
            session: The current session.
            context: The invocation context - tools and instructions are added here.
            state: The provider-scoped mutable state dict.
        """
        context.extend_tools(self.source_id, self.get_tools())
        context.extend_instructions(self.source_id, self.get_instructions())
    
    def get_tools(self) -> list:
        """Get the security tools for agent integration.
        
        Returns:
            List containing quarantined_llm and inspect_variable tools.
        """
        return self.label_tracker.get_security_tools()
    
    def get_instructions(self) -> str:
        """Get the security instructions for agent integration.
        
        Returns:
            String containing security tool usage instructions.
        """
        return self.label_tracker.get_security_instructions()
    
    def get_middleware(self) -> list:
        """Get the middleware stack for agent integration.
        
        Returns:
            List of middleware instances in the correct order.
        """
        middleware = [self.label_tracker]
        if self.policy_enforcer:
            middleware.append(self.policy_enforcer)
        return middleware
    
    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get the audit log from policy enforcement.
        
        Returns:
            List of violation records, or empty list if policy enforcement disabled.
        """
        if self.policy_enforcer:
            return self.policy_enforcer.get_audit_log()
        return []
    
    def get_variable_store(self) -> ContentVariableStore:
        """Get the variable store for this configuration.
        
        Returns:
            The ContentVariableStore instance.
        """
        return self.label_tracker.get_variable_store()
    
    def list_variables(self) -> list[str]:
        """Get a list of all stored variable IDs.
        
        Returns:
            List of variable ID strings.
        """
        return self.label_tracker.list_variables()
    
    def get_quarantine_client(self) -> "SupportsChatGetResponse | None":
        """Get the quarantine chat client.
        
        Returns:
            The SupportsChatGetResponse instance for quarantine calls, or None if not configured.
        """
        return self._quarantine_chat_client
