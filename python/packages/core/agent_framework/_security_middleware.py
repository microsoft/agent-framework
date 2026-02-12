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
from ._types import FunctionResultContent

if TYPE_CHECKING:
    from ._clients import ChatClientProtocol

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
                # Empty list - treat as public for safety
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
    
    Data-Flow Labeling Scheme:
    This middleware uses data-flow based labeling where the output label of a tool
    is determined by combining the labels of all its inputs plus the tool's source
    integrity declaration:
    
        output_label = combine_labels(input_labels + source_label)
    
    - input_labels: Labels extracted from arguments (VariableReferenceContent, etc.)
    - source_label: Tool's declared source_integrity (defaults to UNTRUSTED for safety)
    
    Tools can declare their source_integrity in additional_properties:
    - source_integrity="trusted": Tool produces trusted data (e.g., internal computation)
    - source_integrity="untrusted": Tool fetches external/untrusted data
    - (not set): Defaults to UNTRUSTED for safety - tools must opt-in to TRUSTED
    
    This middleware:
    1. Extracts labels from tool input arguments (recursive inspection)
    2. Checks tool's source_integrity declaration
    3. Combines input labels + source label for the output
    4. Maintains confidentiality labels based on tool declarations
    5. Automatically hides untrusted content using variable indirection
    
    Attributes:
        default_integrity: Default integrity for tools without source_integrity declaration.
        default_confidentiality: The default confidentiality label for tool results.
        auto_hide_untrusted: Whether to automatically hide untrusted results.
        hide_threshold: The integrity level at which to hide content.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ChatAgent, LabelTrackingFunctionMiddleware
            
            # Create agent with automatic hiding enabled
            middleware = LabelTrackingFunctionMiddleware(
                auto_hide_untrusted=True  # Enabled by default
            )
            agent = ChatAgent(
                chat_client=client,
                name="assistant",
                middleware=middleware
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
        
        Data-flow labeling: The output label of a tool is determined by combining
        the labels of all its inputs, plus the tool's source_integrity property.
        
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
    
    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Process function invocation with data-flow based label tracking.
        
        Data-flow labeling scheme:
        - output_label = combine_labels(input_labels + source_label)
        - input_labels: Labels extracted from arguments (VariableReferenceContent, etc.)
        - source_label: Tool's declared source_integrity (defaults to UNTRUSTED for safety)
        
        The context label tracks the cumulative security state:
        - Starts as TRUSTED + PUBLIC
        - Gets updated (tainted) based on tool results added to context
        - Policy enforcement uses the context label to validate tool calls
        
        Args:
            context: The function invocation context.
            next: Callback to continue to next middleware or function execution.
        """
        # Set thread-local middleware reference for tools to access
        _current_middleware.instance = self
        
        try:
            function_name = context.function.name
            
            # ========== Data-Flow Based Labeling ==========
            # Step 1: Extract labels from input arguments
            input_labels = self._get_input_labels(context)
            
            # Step 2: Get tool's source_integrity declaration
            # Default to UNTRUSTED for safety (tools fetching external data)
            source_integrity = self._get_source_integrity(context)
            if source_integrity is None:
                # Default: tools without explicit declaration are treated as UNTRUSTED
                # This is the safe default - tools must explicitly opt-in to TRUSTED
                source_integrity = self.default_integrity
            
            # Step 3: Create source label from tool's declaration
            source_label = ContentLabel(
                integrity=source_integrity,
                confidentiality=ConfidentialityLabel.PUBLIC,  # Source doesn't affect confidentiality
                metadata={"source": "tool_declaration", "function_name": function_name}
            )
            
            # Step 4: Combine all labels (input labels + source label)
            all_labels = input_labels + [source_label]
            combined_integrity_label = combine_labels(*all_labels) if all_labels else ContentLabel()
            
            # Get confidentiality from function additional_properties or use default
            confidentiality = self._get_function_confidentiality(context)
            
            # Create the final call label
            call_label = ContentLabel(
                integrity=combined_integrity_label.integrity,
                confidentiality=confidentiality,
                metadata={
                    "source": "data_flow",
                    "function_name": function_name,
                    "input_labels_count": len(input_labels),
                    "source_integrity": source_integrity.value,
                }
            )
            
            # Store both the call label AND the current context label in metadata
            # Policy enforcement will use the context label for validation
            context.metadata["security_label"] = call_label
            context.metadata["context_label"] = self._context_label
            
            logger.info(
                f"Tool call '{function_name}' labeled (data-flow): {call_label.integrity.value}, "
                f"{call_label.confidentiality.value} "
                f"(inputs: {len(input_labels)}, source: {source_integrity.value})"
            )
            logger.info(
                f"Current context label: {self._context_label.integrity.value}, "
                f"{self._context_label.confidentiality.value}"
            )
            
            # Execute the function
            await next(context)
            
            # If middleware set a FunctionApprovalRequestContent (e.g., policy violation approval),
            # skip all result processing and let it pass through unchanged
            from ._types import FunctionApprovalRequestContent
            if isinstance(context.result, FunctionApprovalRequestContent):
                logger.info(
                    f"Tool '{function_name}' returned FunctionApprovalRequestContent - "
                    f"skipping result processing"
                )
                return
            
            # Result inherits the call label (data-flow: output = f(inputs))
            result_label = call_label
            
            # Process result for per-item embedded labels
            if context.result is not None:
                original_result = context.result
                
                # First, process for per-item embedded labels
                # This allows tools to return mixed-trust data (e.g., some emails trusted, others not)
                # Items with additional_properties.security_label.integrity="untrusted" are auto-hidden
                context.result, result_label = self._process_result_with_embedded_labels(
                    context.result,
                    function_name,
                    fallback_label=call_label,  # Use call label for items without embedded labels
                )
                
                # Update the security_label metadata with the combined result label
                # This reflects the combined labels from all items (including embedded labels)
                context.metadata["security_label"] = result_label
                
                # Attach overall label to result if it's a FunctionResultContent
                self._attach_label_to_result(context, result_label)
                
                # Update context label only if untrusted content actually entered the context
                # If the entire result was hidden (replaced with VariableReferenceContent),
                # the untrusted content is NOT in the LLM context, so don't taint INTEGRITY.
                # However, CONFIDENTIALITY should ALWAYS be updated even for hidden content,
                # because the data still exists and could be revealed by approving the variable.
                entire_result_hidden = (
                    isinstance(context.result, VariableReferenceContent) and 
                    not isinstance(original_result, VariableReferenceContent)
                )
                
                if entire_result_hidden:
                    # Result was hidden - integrity stays clean, but confidentiality MUST be updated
                    # This prevents data exfiltration: even hidden PRIVATE data taints the context
                    if result_label.confidentiality != self._context_label.confidentiality:
                        old_conf = self._context_label.confidentiality
                        # Only update confidentiality, keep integrity clean
                        hidden_result_label = ContentLabel(
                            integrity=self._context_label.integrity,  # Keep existing integrity
                            confidentiality=result_label.confidentiality,  # Update confidentiality
                        )
                        self._update_context_label(hidden_result_label)
                        logger.info(
                            f"Result from '{function_name}' hidden (integrity clean) but "
                            f"confidentiality updated: {old_conf.value} -> {result_label.confidentiality.value}"
                        )
                    else:
                        logger.info(
                            f"Result from '{function_name}' fully hidden - context label unchanged: "
                            f"{self._context_label.integrity.value}, "
                            f"{self._context_label.confidentiality.value}"
                        )
                else:
                    # Some content entered context - update context label
                    self._update_context_label(result_label)
                    logger.info(
                        f"Context label after processing '{function_name}': "
                        f"{self._context_label.integrity.value}, "
                        f"{self._context_label.confidentiality.value}"
                    )
        finally:
            # Clear thread-local reference
            _current_middleware.instance = None
    
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
    
    def _attach_label_to_result(
        self,
        context: FunctionInvocationContext,
        label: ContentLabel,
    ) -> None:
        """Attach security label to function result.
        
        Args:
            context: The function invocation context.
            label: The security label to attach.
        """
        result = context.result
        
        # If result is a FunctionResultContent, attach label to additional_properties
        if isinstance(result, FunctionResultContent):
            if not hasattr(result, "additional_properties") or result.additional_properties is None:
                result.additional_properties = {}
            result.additional_properties["security_label"] = label.to_dict()
            logger.debug(f"Attached label to FunctionResultContent: {label}")
        
        # If result is a dict, attach label directly
        elif isinstance(result, dict):
            result["security_label"] = label.to_dict()
            logger.debug(f"Attached label to dict result: {label}")
        
        # Otherwise, store in context metadata
        else:
            context.metadata["result_label"] = label
            logger.debug(f"Stored label in context metadata: {label}")
    
    def _process_result_with_embedded_labels(
        self,
        result: Any,
        function_name: str,
        fallback_label: ContentLabel,
    ) -> tuple[Any, ContentLabel]:
        """Recursively process result, respecting per-item embedded labels.
        
        Items can embed their own security labels in additional_properties.security_label,
        consistent with how FunctionResultContent stores labels. This allows tools to
        return mixed-trust data where some items are trusted and others are untrusted.
        
        Untrusted items are automatically hidden and replaced with VariableReferenceContent.
        Trusted items pass through unchanged.
        
        If an item has no embedded label, the fallback_label is used. If that fallback
        is UNTRUSTED, the item is hidden.
        
        Args:
            result: The result to process (may be dict, list, or primitive).
            function_name: Name of the function that produced the result.
            fallback_label: Label to use if item has no embedded label.
            context_label: Label of the current context.
        Returns:
            Tuple of (processed_result, combined_label).
            - processed_result: Result with untrusted items replaced by variable references
            - combined_label: Most restrictive label from all items
        
        Examples:
            Tool returns list with per-item labels::
            
                [
                    {"id": 1, "body": "safe", "additional_properties": {"security_label": {"integrity": "trusted"}}},
                    {"id": 2, "body": "unsafe", "additional_properties": {"security_label": {"integrity": "untrusted"}}},
                ]
            
            After processing::
            
                [
                    {"id": 1, "body": "safe", "additional_properties": {"security_label": {"integrity": "trusted"}}},
                    VariableReferenceContent(variable_id="var_xxx", ...),  # Item 2 hidden
                ]
        """
        from pydantic import BaseModel
        
        # Handle pydantic models (e.g., TextContent from MCP) with additional_properties
        if isinstance(result, BaseModel) and hasattr(result, "additional_properties"):
            additional_props = result.additional_properties
            if additional_props and isinstance(additional_props, dict):
                # Check for standard security_label
                label_data = additional_props.get("security_label")
                if label_data:
                    try:
                        item_label = ContentLabel.from_dict(label_data)
                        # Only hide if context is trusted (untrusted content would taint it)
                        # If context is already untrusted, no need to hide
                        if (self.auto_hide_untrusted and 
                            item_label.integrity == self.hide_threshold and
                            self._context_label.integrity == IntegrityLabel.TRUSTED):
                            hidden = self._hide_untrusted_result(result, item_label, function_name)
                            return hidden, item_label
                        return result, item_label
                    except Exception as e:
                        logger.warning(f"Failed to parse security_label from pydantic model: {e}")
                
                # Check for GitHub MCP server labels format
                github_labels = additional_props.get("labels")
                if github_labels and isinstance(github_labels, (dict, list)):
                    try:
                        if isinstance(github_labels, list) and github_labels:
                            github_labels = github_labels[0] if isinstance(github_labels[0], dict) else {}
                        
                        item_label = _parse_github_mcp_labels(github_labels)
                        if item_label:
                            logger.info(
                                f"Parsed GitHub MCP labels from pydantic model for '{function_name}': "
                                f"integrity={item_label.integrity.value}, "
                                f"confidentiality={item_label.confidentiality.value}"
                            )
                            # Only hide if context is trusted
                            if (self.auto_hide_untrusted and 
                                item_label.integrity == self.hide_threshold and
                                self._context_label.integrity == IntegrityLabel.TRUSTED):
                                hidden = self._hide_untrusted_result(result, item_label, function_name)
                                return hidden, item_label
                            return result, item_label
                    except Exception as e:
                        logger.warning(f"Failed to parse GitHub MCP labels from pydantic model: {e}")
            
            # No embedded labels found - use fallback
            # Only hide if context is trusted
            if (self.auto_hide_untrusted and 
                fallback_label.integrity == self.hide_threshold and
                self._context_label.integrity == IntegrityLabel.TRUSTED):
                hidden = self._hide_untrusted_result(result, fallback_label, function_name)
                return hidden, fallback_label
            return result, fallback_label
        
        if isinstance(result, dict):
            # Check for additional_properties.security_label (consistent with FunctionResultContent)
            additional_props = result.get("additional_properties")
            if additional_props and isinstance(additional_props, dict):
                label_data = additional_props.get("security_label")
                if label_data:
                    try:
                        item_label = ContentLabel.from_dict(label_data)
                        # This item has an explicit label
                        # Only hide if context is trusted
                        if (self.auto_hide_untrusted and 
                            item_label.integrity == self.hide_threshold and
                            self._context_label.integrity == IntegrityLabel.TRUSTED):
                            # Hide this entire item
                            hidden = self._hide_untrusted_result(result, item_label, function_name)
                            return hidden, item_label
                        # Item is trusted or hiding disabled or context already untrusted - return as-is
                        return result, item_label
                    except Exception as e:
                        logger.warning(f"Failed to parse embedded security_label: {e}")
                
                # Check for GitHub MCP server labels format: additional_properties.labels
                # This is per-field labels like {"body": {"integrity": "low", ...}, ...}
                github_labels = additional_props.get("labels")
                if github_labels and isinstance(github_labels, (dict, list)):
                    try:
                        # Handle list of labels (for list_issues) or dict of labels (for get_issue)
                        if isinstance(github_labels, list) and github_labels:
                            # Take the first item's labels as representative for the whole result
                            github_labels = github_labels[0] if isinstance(github_labels[0], dict) else {}
                        
                        item_label = _parse_github_mcp_labels(github_labels)
                        if item_label:
                            logger.info(
                                f"Parsed GitHub MCP labels for '{function_name}': "
                                f"integrity={item_label.integrity.value}, "
                                f"confidentiality={item_label.confidentiality.value}"
                            )
                            # This item has a label from GitHub MCP
                            # Only hide if context is trusted
                            if (self.auto_hide_untrusted and 
                                item_label.integrity == self.hide_threshold and
                                self._context_label.integrity == IntegrityLabel.TRUSTED):
                                # Hide this entire item
                                hidden = self._hide_untrusted_result(result, item_label, function_name)
                                return hidden, item_label
                            # Item is trusted or hiding disabled or context already untrusted - return as-is
                            return result, item_label
                    except Exception as e:
                        logger.warning(f"Failed to parse GitHub MCP labels: {e}")
            
            # No embedded label on this dict - recurse into values
            # But only process list/dict values, not primitives
            processed = {}
            child_labels = []
            has_embedded_labels = False
            for key, value in result.items():
                if key == "additional_properties":
                    # Don't recurse into additional_properties itself
                    processed[key] = value
                elif isinstance(value, (dict, list)):
                    processed_value, child_label = self._process_result_with_embedded_labels(
                        value, function_name, fallback_label
                    )
                    processed[key] = processed_value
                    child_labels.append(child_label)
                    # Check if any child had embedded labels (not just fallback)
                    if isinstance(value, list) and any(
                        isinstance(v, dict) and v.get("additional_properties", {}).get("security_label")
                        for v in value
                    ):
                        has_embedded_labels = True
                else:
                    processed[key] = value
            
            # Combine child labels, or use fallback if no children had labels
            if child_labels:
                combined = combine_labels(*child_labels)
            else:
                combined = fallback_label
            
            # If no embedded labels were found anywhere and fallback is UNTRUSTED,
            # hide the entire dict (backward compatibility with old behavior)
            # Only hide if context is trusted
            if not has_embedded_labels and not additional_props:
                if (self.auto_hide_untrusted and 
                    combined.integrity == self.hide_threshold and
                    self._context_label.integrity == IntegrityLabel.TRUSTED):
                    hidden = self._hide_untrusted_result(result, combined, function_name)
                    return hidden, combined
            
            return processed, combined
        
        elif isinstance(result, list):
            # Check if any items have embedded labels (dict items or pydantic models with additional_properties)
            has_embedded_labels = False
            for item in result:
                if isinstance(item, dict):
                    additional_props = item.get("additional_properties", {})
                    if additional_props.get("security_label") or additional_props.get("labels"):
                        has_embedded_labels = True
                        break
                elif hasattr(item, "additional_properties") and item.additional_properties:
                    # Pydantic model with additional_properties (e.g., TextContent from MCP)
                    additional_props = item.additional_properties
                    if additional_props.get("security_label") or additional_props.get("labels"):
                        has_embedded_labels = True
                        break
            
            if has_embedded_labels:
                # Process each item independently - some may be hidden, others visible
                processed = []
                item_labels = []
                for i, item in enumerate(result):
                    processed_item, item_label = self._process_result_with_embedded_labels(
                        item, function_name, fallback_label
                    )
                    processed.append(processed_item)
                    item_labels.append(item_label)
                
                # Combined label is most restrictive across all items
                combined = combine_labels(*item_labels) if item_labels else fallback_label
                return processed, combined
            else:
                # No embedded labels - if fallback is UNTRUSTED, hide entire list
                # Only hide if context is trusted
                if (self.auto_hide_untrusted and 
                    fallback_label.integrity == self.hide_threshold and
                    self._context_label.integrity == IntegrityLabel.TRUSTED):
                    hidden = self._hide_untrusted_result(result, fallback_label, function_name)
                    return hidden, fallback_label
                return result, fallback_label
        
        else:
            # Primitive value - no embedded label possible, use fallback
            # If fallback is UNTRUSTED, hide it
            # Only hide if context is trusted
            if (self.auto_hide_untrusted and 
                fallback_label.integrity == self.hide_threshold and
                self._context_label.integrity == IntegrityLabel.TRUSTED):
                hidden = self._hide_untrusted_result(result, fallback_label, function_name)
                return hidden, fallback_label
            return result, fallback_label
    
    def _hide_untrusted_result(
        self,
        result: Any,
        label: ContentLabel,
        function_name: str
    ) -> VariableReferenceContent:
        """Replace untrusted result with a variable reference.
        
        This method stores the actual content in the variable store and returns
        a VariableReferenceContent that can be safely added to the LLM context.
        
        Args:
            result: The original result to hide.
            label: The security label for the result.
            function_name: Name of the function that produced the result.
        
        Returns:
            A VariableReferenceContent referencing the stored content.
        """
        # Store the actual content
        var_id = self._variable_store.store(result, label)
        
        # Store metadata about this variable
        self._variable_metadata[var_id] = {
            "function_name": function_name,
            "original_type": type(result).__name__,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Create variable reference
        description = f"Result from {function_name}"
        var_ref = VariableReferenceContent(
            variable_id=var_id,
            label=label,
            description=description
        )
        
        logger.info(
            f"Auto-hidden untrusted result from '{function_name}' "
            f"as variable {var_id}"
        )
        
        return var_ref
    
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
                
                agent = ChatAgent(
                    chat_client=client,
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
                
                agent = ChatAgent(
                    chat_client=client,
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
        
            from agent_framework import ChatAgent, PolicyEnforcementFunctionMiddleware
            
            # Create policy enforcement middleware
            policy = PolicyEnforcementFunctionMiddleware(
                allow_untrusted_tools={"search_web", "get_news"}
            )
            
            agent = ChatAgent(
                chat_client=client,
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
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Process function invocation with policy enforcement.
        
        Policy enforcement uses the context_label (cumulative security state of the
        conversation) to validate tool calls. This prevents indirect attacks where
        untrusted content from previous tool calls could influence dangerous operations.
        
        Args:
            context: The function invocation context.
            next: Callback to continue to next middleware or function execution.
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
            await next(context)
            return
        
        # Convert context label to ContentLabel if it's a dict
        if isinstance(context_label_data, dict):
            context_label = ContentLabel.from_dict(context_label_data)
        elif isinstance(context_label_data, ContentLabel):
            context_label = context_label_data
        else:
            logger.error(f"Invalid context label type: {type(context_label_data)}")
            await next(context)
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
                    
                    # Check multiple sources for approval:
                    # 1. policy_approval_granted from metadata (set by _tools.py)
                    # 2. call_id in _approved_violations (persisted approvals)
                    # 3. call_id in _pending_policy_approvals (we sent approval request for this call_id)
                    is_approved = (
                        policy_approved 
                        or call_id in self._approved_violations 
                        or call_id in self._pending_policy_approvals
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
                        # Create FunctionApprovalRequestContent directly in middleware
                        logger.info(
                            f"APPROVAL REQUESTED: Tool '{function_name}' requires user approval "
                            f"due to UNTRUSTED context."
                        )
                        from ._types import FunctionApprovalRequestContent, FunctionCallContent
                        
                        # Track that we're requesting approval for this call_id
                        self._pending_policy_approvals.add(call_id)
                        
                        # Reconstruct FunctionCallContent from context
                        func_call = FunctionCallContent(
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
                        
                        context.result = FunctionApprovalRequestContent(
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
            
            # Check multiple sources for approval:
            # 1. policy_approval_granted from metadata (set by _tools.py)
            # 2. call_id in _approved_violations (persisted approvals)
            # 3. call_id in _pending_policy_approvals (we sent approval request for this call_id)
            is_approved = (
                policy_approved 
                or call_id in self._approved_violations 
                or call_id in self._pending_policy_approvals
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
                # Create FunctionApprovalRequestContent directly in middleware
                logger.info(
                    f"APPROVAL REQUESTED: Tool '{function_name}' requires user approval "
                    f"due to confidentiality policy violation."
                )
                from ._types import FunctionApprovalRequestContent, FunctionCallContent
                
                # Track that we're requesting approval for this call_id
                self._pending_policy_approvals.add(call_id)
                
                # Reconstruct FunctionCallContent from context
                func_call = FunctionCallContent(
                    call_id=call_id,
                    name=function_name,
                    arguments=context.arguments.model_dump() if hasattr(context.arguments, 'model_dump') else dict(context.arguments),
                )
                
                reason = (
                    f"Tool '{function_name}' violates confidentiality policy: "
                    f"{conf_result['reason']}. Approve to proceed anyway."
                )
                
                context.result = FunctionApprovalRequestContent(
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
        await next(context)
    
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


class SecureAgentConfig:
    """Configuration for creating a secure agent with prompt injection defense.
    
    This class encapsulates the security middleware, tools, and instructions
    needed to create an agent that can safely handle untrusted content.
    
    Attributes:
        label_tracker: The LabelTrackingFunctionMiddleware instance.
        policy_enforcer: Optional PolicyEnforcementFunctionMiddleware instance.
        auto_hide_untrusted: Whether to automatically hide untrusted content.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ChatAgent, SecureAgentConfig
            
            # Create security configuration
            config = SecureAgentConfig(
                allow_untrusted_tools={"fetch_external_data"},
                block_on_violation=True,
            )
            
            # Create secure agent
            agent = ChatAgent(
                chat_client=client,
                instructions=base_instructions + config.get_instructions(),
                tools=[my_tool, *config.get_tools()],
                middleware=config.get_middleware(),
            )
    """
    
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
        quarantine_chat_client: "ChatClientProtocol | None" = None,
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
        """
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
    
    def get_quarantine_client(self) -> "ChatClientProtocol | None":
        """Get the quarantine chat client.
        
        Returns:
            The ChatClientProtocol instance for quarantine calls, or None if not configured.
        """
        return self._quarantine_chat_client
