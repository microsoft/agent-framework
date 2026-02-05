# Copyright (c) Microsoft. All rights reserved.

"""Security infrastructure for prompt injection defense.

This module provides label-based security mechanisms to defend against prompt injection attacks
by tracking integrity and confidentiality of content throughout agent execution.
"""

import logging
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from ._serialization import SerializationMixin

__all__ = [
    "IntegrityLabel",
    "ConfidentialityLabel",
    "ContentLabel",
    "ContentVariableStore",
    "VariableReferenceContent",
    "LabeledMessage",
    "ContentLineage",
    "combine_labels",
    "check_confidentiality_allowed",
]

logger = logging.getLogger(__name__)


class IntegrityLabel(str, Enum):
    """Represents the integrity level of content.
    
    Attributes:
        TRUSTED: Content originated from trusted sources (e.g., user input, system messages).
        UNTRUSTED: Content originated from untrusted sources (e.g., AI-generated, external APIs).
    """
    
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    
    def __str__(self) -> str:
        return self.value


class ConfidentialityLabel(str, Enum):
    """Represents the confidentiality level of content.
    
    Attributes:
        PUBLIC: Content can be shared publicly.
        PRIVATE: Content is private and should not be shared.
        USER_IDENTITY: Content is restricted to specific user identities only.
    """
    
    PUBLIC = "public"
    PRIVATE = "private"
    USER_IDENTITY = "user_identity"
    
    def __str__(self) -> str:
        return self.value


class ContentLabel(SerializationMixin):
    """Represents security labels for content.
    
    Attributes:
        integrity: The integrity level of the content.
        confidentiality: The confidentiality level of the content.
        metadata: Additional metadata for the label (e.g., user IDs, source information).
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ContentLabel, IntegrityLabel, ConfidentialityLabel
            
            # Create a label for trusted public content
            label = ContentLabel(
                integrity=IntegrityLabel.TRUSTED,
                confidentiality=ConfidentialityLabel.PUBLIC
            )
            
            # Create a label with user identity
            user_label = ContentLabel(
                integrity=IntegrityLabel.TRUSTED,
                confidentiality=ConfidentialityLabel.USER_IDENTITY,
                metadata={"user_id": "user-123"}
            )
    """
    
    def __init__(
        self,
        integrity: IntegrityLabel = IntegrityLabel.TRUSTED,
        confidentiality: ConfidentialityLabel = ConfidentialityLabel.PUBLIC,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a ContentLabel.
        
        Args:
            integrity: The integrity level. Defaults to TRUSTED.
            confidentiality: The confidentiality level. Defaults to PUBLIC.
            metadata: Additional metadata for the label.
        """
        self.integrity = integrity if isinstance(integrity, IntegrityLabel) else IntegrityLabel(integrity)
        self.confidentiality = (
            confidentiality 
            if isinstance(confidentiality, ConfidentialityLabel) 
            else ConfidentialityLabel(confidentiality)
        )
        self.metadata = metadata or {}
    
    def is_trusted(self) -> bool:
        """Check if the content is trusted."""
        return self.integrity == IntegrityLabel.TRUSTED
    
    def is_public(self) -> bool:
        """Check if the content is public."""
        return self.confidentiality == ConfidentialityLabel.PUBLIC
    
    def __repr__(self) -> str:
        return f"ContentLabel(integrity={self.integrity}, confidentiality={self.confidentiality})"
    
    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "integrity": str(self.integrity),
            "confidentiality": str(self.confidentiality),
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentLabel":
        """Create ContentLabel from dictionary."""
        return cls(
            integrity=IntegrityLabel(data.get("integrity", "trusted")),
            confidentiality=ConfidentialityLabel(data.get("confidentiality", "public")),
            metadata=data.get("metadata"),
        )


def combine_labels(*labels: ContentLabel) -> ContentLabel:
    """Combine multiple labels using the most restrictive policy.
    
    The combined label will be:
    - UNTRUSTED if any input is UNTRUSTED
    - Most restrictive confidentiality level (USER_IDENTITY > PRIVATE > PUBLIC)
    - Merged metadata from all labels
    
    Args:
        *labels: Variable number of ContentLabel instances to combine.
    
    Returns:
        A new ContentLabel with the most restrictive settings.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ContentLabel, IntegrityLabel, ConfidentialityLabel, combine_labels
            
            label1 = ContentLabel(IntegrityLabel.TRUSTED, ConfidentialityLabel.PUBLIC)
            label2 = ContentLabel(IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PRIVATE)
            
            combined = combine_labels(label1, label2)
            # Result: UNTRUSTED integrity, PRIVATE confidentiality
    """
    if not labels:
        return ContentLabel()
    
    # Most restrictive integrity: UNTRUSTED if any is UNTRUSTED
    integrity = IntegrityLabel.UNTRUSTED if any(
        label.integrity == IntegrityLabel.UNTRUSTED for label in labels
    ) else IntegrityLabel.TRUSTED
    
    # Most restrictive confidentiality
    confidentiality_priority = {
        ConfidentialityLabel.PUBLIC: 0,
        ConfidentialityLabel.PRIVATE: 1,
        ConfidentialityLabel.USER_IDENTITY: 2,
    }
    
    confidentiality = max(
        (label.confidentiality for label in labels),
        key=lambda c: confidentiality_priority[c]
    )
    
    # Merge metadata
    merged_metadata: Dict[str, Any] = {}
    for label in labels:
        if label.metadata:
            merged_metadata.update(label.metadata)
    
    return ContentLabel(
        integrity=integrity,
        confidentiality=confidentiality,
        metadata=merged_metadata if merged_metadata else None
    )


def check_confidentiality_allowed(
    context_label: ContentLabel,
    max_allowed: ConfidentialityLabel,
) -> bool:
    """Check if writing data with context_label to a destination with max_allowed confidentiality is permitted.
    
    This function prevents data exfiltration attacks by enforcing that sensitive data
    cannot be written to less secure destinations. For example, it blocks PRIVATE data
    from being sent to PUBLIC endpoints.
    
    The check passes if context_label.confidentiality <= max_allowed in the hierarchy:
        PUBLIC (0) < PRIVATE (1) < USER_IDENTITY (2)
    
    Args:
        context_label: The label tracking the confidentiality of data in the current context.
        max_allowed: The maximum confidentiality level accepted by the destination.
    
    Returns:
        True if the write is allowed, False if it would be a data exfiltration.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ContentLabel, ConfidentialityLabel, check_confidentiality_allowed
            
            # PUBLIC data can be written anywhere
            public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
            assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PUBLIC) == True
            assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PRIVATE) == True
            
            # PRIVATE data cannot be written to PUBLIC destinations
            private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
            assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PUBLIC) == False
            assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PRIVATE) == True
            
            # Use in a tool to dynamically check destination
            def send_message(destination: str, message: str, context_label: ContentLabel):
                dest_confidentiality = get_destination_confidentiality(destination)
                if not check_confidentiality_allowed(context_label, dest_confidentiality):
                    raise ValueError(
                        f"Cannot send {context_label.confidentiality.value} data "
                        f"to {dest_confidentiality.value} destination"
                    )
                # Proceed with sending...
    """
    conf_hierarchy = {
        ConfidentialityLabel.PUBLIC: 0,
        ConfidentialityLabel.PRIVATE: 1,
        ConfidentialityLabel.USER_IDENTITY: 2,
    }
    
    return conf_hierarchy[context_label.confidentiality] <= conf_hierarchy[max_allowed]


class ContentVariableStore:
    """Client-side storage for untrusted content using variable indirection.
    
    This store maintains a mapping between variable IDs and actual content,
    preventing untrusted content from being exposed directly to the LLM context.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ContentVariableStore, ContentLabel, IntegrityLabel
            
            store = ContentVariableStore()
            
            # Store untrusted content
            untrusted_label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
            var_id = store.store("potentially malicious content", untrusted_label)
            
            # Retrieve content later
            content, label = store.retrieve(var_id)
            print(content)  # "potentially malicious content"
    """
    
    def __init__(self) -> None:
        """Initialize an empty ContentVariableStore."""
        self._storage: Dict[str, tuple[Any, ContentLabel]] = {}
    
    def store(self, content: Any, label: ContentLabel) -> str:
        """Store content and return a variable ID.
        
        Args:
            content: The content to store.
            label: The security label for the content.
        
        Returns:
            A unique variable ID string.
        """
        var_id = f"var_{uuid.uuid4().hex[:16]}"
        self._storage[var_id] = (content, label)
        logger.info(f"Stored content in variable {var_id} with label {label}")
        return var_id
    
    def retrieve(self, var_id: str) -> tuple[Any, ContentLabel]:
        """Retrieve content and its label by variable ID.
        
        Args:
            var_id: The variable ID.
        
        Returns:
            A tuple of (content, label).
        
        Raises:
            KeyError: If the variable ID doesn't exist.
        """
        if var_id not in self._storage:
            raise KeyError(f"Variable {var_id} not found in store")
        
        content, label = self._storage[var_id]
        logger.info(f"Retrieved content from variable {var_id} with label {label}")
        return content, label
    
    def exists(self, var_id: str) -> bool:
        """Check if a variable ID exists in the store.
        
        Args:
            var_id: The variable ID to check.
        
        Returns:
            True if the variable exists, False otherwise.
        """
        return var_id in self._storage
    
    def clear(self) -> None:
        """Clear all stored content."""
        count = len(self._storage)
        self._storage.clear()
        logger.info(f"Cleared {count} variables from store")
    
    def list_variables(self) -> list[str]:
        """Get a list of all variable IDs in the store.
        
        Returns:
            List of variable ID strings.
        """
        return list(self._storage.keys())


class VariableReferenceContent:
    """Represents a reference to content stored in ContentVariableStore.
    
    This class is used to represent untrusted content in the LLM context
    without exposing the actual content, preventing prompt injection.
    
    Attributes:
        variable_id: The ID of the variable in the store.
        label: The security label of the referenced content.
        description: Optional human-readable description of the content.
        type: The type discriminator, always "variable_reference".
    
    Examples:
        .. code-block:: python
        
            from agent_framework import VariableReferenceContent, ContentLabel, IntegrityLabel
            
            label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
            ref = VariableReferenceContent(
                variable_id="var_abc123",
                label=label,
                description="External API response"
            )
    """
    
    def __init__(
        self,
        variable_id: str,
        label: ContentLabel,
        description: Optional[str] = None,
    ) -> None:
        """Initialize a VariableReferenceContent.
        
        Args:
            variable_id: The ID of the variable in the store.
            label: The security label of the referenced content.
            description: Optional description of the content.
        """
        self.variable_id = variable_id
        self.label = label
        self.description = description
        self.type: str = "variable_reference"
    
    def __repr__(self) -> str:
        desc = f", description='{self.description}'" if self.description else ""
        return f"VariableReferenceContent(variable_id='{self.variable_id}'{desc})"
    
    def to_dict(self, *, exclude: Optional[set[str]] = None, exclude_none: bool = True) -> Dict[str, Any]:
        """Convert to dictionary representation.
        
        Args:
            exclude: Optional set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values. Defaults to True.
        
        Returns:
            Dictionary representation of this variable reference.
        """
        result = {
            "type": self.type,
            "variable_id": self.variable_id,
            "security_label": self.label.to_dict(),
        }
        if exclude:
            result = {k: v for k, v in result.items() if k not in exclude}
        if self.description:
            result["description"] = self.description
        elif not exclude_none:
            result["description"] = None
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariableReferenceContent":
        """Create VariableReferenceContent from dictionary."""
        # Accept both "security_label" (preferred) and "label" (legacy) keys
        label_data = data.get("security_label") or data.get("label")
        return cls(
            variable_id=data["variable_id"],
            label=ContentLabel.from_dict(label_data),
            description=data.get("description"),
        )


class LabeledMessage:
    """Represents a message with its security label and provenance.
    
    Every message in a conversation can carry a security label that tracks
    its integrity and confidentiality. This enables automatic label propagation
    through the conversation history.
    
    Attributes:
        role: The message role (user, assistant, system, tool).
        content: The message content.
        security_label: The security label for this message.
        message_index: Optional index in the conversation.
        source_labels: Labels of content that contributed to this message.
        metadata: Additional metadata.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import LabeledMessage, ContentLabel, IntegrityLabel
            
            # User message is always TRUSTED
            user_msg = LabeledMessage(
                role="user",
                content="Hello!",
                security_label=ContentLabel(integrity=IntegrityLabel.TRUSTED)
            )
            
            # Assistant message derived from untrusted content
            assistant_msg = LabeledMessage(
                role="assistant",
                content="Here's the summary...",
                security_label=ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
                source_labels=[untrusted_tool_label]
            )
    """
    
    def __init__(
        self,
        role: str,
        content: Any,
        security_label: Optional[ContentLabel] = None,
        message_index: Optional[int] = None,
        source_labels: Optional[list[ContentLabel]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a LabeledMessage.
        
        Args:
            role: The message role (user, assistant, system, tool).
            content: The message content.
            security_label: The security label. If None, inferred from role.
            message_index: Optional index in the conversation.
            source_labels: Labels of content that contributed to this message.
            metadata: Additional metadata.
        """
        self.role = role
        self.content = content
        self.message_index = message_index
        self.source_labels = source_labels or []
        self.metadata = metadata or {}
        
        # Infer label from role if not provided
        if security_label is None:
            security_label = self._infer_label_from_role(role)
        self.security_label = security_label
    
    def _infer_label_from_role(self, role: str) -> ContentLabel:
        """Infer a security label based on the message role.
        
        Args:
            role: The message role.
        
        Returns:
            A ContentLabel appropriate for the role.
        """
        if role in ("user", "system"):
            # User and system messages are trusted by default
            return ContentLabel(
                integrity=IntegrityLabel.TRUSTED,
                confidentiality=ConfidentialityLabel.PUBLIC,
                metadata={"auto_labeled": True, "reason": f"{role}_message"}
            )
        elif role == "assistant":
            # Assistant messages inherit from source labels if any
            if self.source_labels:
                return combine_labels(*self.source_labels)
            # Default to TRUSTED if no source labels (pure generation)
            return ContentLabel(
                integrity=IntegrityLabel.TRUSTED,
                confidentiality=ConfidentialityLabel.PUBLIC,
                metadata={"auto_labeled": True, "reason": "assistant_no_sources"}
            )
        elif role == "tool":
            # Tool messages are UNTRUSTED by default (external data)
            return ContentLabel(
                integrity=IntegrityLabel.UNTRUSTED,
                confidentiality=ConfidentialityLabel.PUBLIC,
                metadata={"auto_labeled": True, "reason": "tool_result"}
            )
        else:
            # Unknown role defaults to UNTRUSTED
            return ContentLabel(
                integrity=IntegrityLabel.UNTRUSTED,
                confidentiality=ConfidentialityLabel.PUBLIC,
                metadata={"auto_labeled": True, "reason": f"unknown_role_{role}"}
            )
    
    def is_trusted(self) -> bool:
        """Check if this message is trusted."""
        return self.security_label.is_trusted()
    
    def __repr__(self) -> str:
        return (
            f"LabeledMessage(role='{self.role}', "
            f"label={self.security_label.integrity.value}/{self.security_label.confidentiality.value})"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "role": self.role,
            "content": self.content,
            "security_label": self.security_label.to_dict(),
        }
        if self.message_index is not None:
            result["message_index"] = self.message_index
        if self.source_labels:
            result["source_labels"] = [l.to_dict() for l in self.source_labels]
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LabeledMessage":
        """Create LabeledMessage from dictionary."""
        source_labels = None
        if "source_labels" in data:
            source_labels = [ContentLabel.from_dict(l) for l in data["source_labels"]]
        
        return cls(
            role=data["role"],
            content=data["content"],
            security_label=ContentLabel.from_dict(data["security_label"]) if "security_label" in data else None,
            message_index=data.get("message_index"),
            source_labels=source_labels,
            metadata=data.get("metadata"),
        )
    
    @classmethod
    def from_message(cls, message: Dict[str, Any], index: Optional[int] = None) -> "LabeledMessage":
        """Create a LabeledMessage from a standard message dict.
        
        This is a convenience method to wrap existing messages with labels.
        
        Args:
            message: A message dict with at least 'role' and 'content'.
            index: Optional message index in the conversation.
        
        Returns:
            A LabeledMessage with an inferred security label.
        """
        return cls(
            role=message.get("role", "unknown"),
            content=message.get("content", ""),
            message_index=index,
            metadata={"original_message": True},
        )


class ContentLineage:
    """Tracks the derivation history of content for label propagation.
    
    When content is transformed (summarized, extracted, combined, etc.),
    the ContentLineage tracks where it came from and how it was derived.
    This ensures that labels are properly propagated through transformations.
    
    Attributes:
        content_id: Unique identifier for this content.
        derived_from: IDs of source content that this was derived from.
        transformation: Type of transformation applied (e.g., "summarize", "extract").
        combined_label: The combined label from all source content.
        metadata: Additional metadata about the derivation.
    
    Examples:
        .. code-block:: python
        
            from agent_framework import ContentLineage, ContentLabel, IntegrityLabel
            
            # Content derived from quarantined_llm processing
            lineage = ContentLineage(
                content_id="result_123",
                derived_from=["var_abc123", "var_def456"],
                transformation="llm_summary",
                combined_label=ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
                metadata={"prompt": "Summarize the data"}
            )
    """
    
    def __init__(
        self,
        content_id: str,
        derived_from: Optional[list[str]] = None,
        transformation: Optional[str] = None,
        combined_label: Optional[ContentLabel] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a ContentLineage.
        
        Args:
            content_id: Unique identifier for this content.
            derived_from: IDs of source content.
            transformation: Type of transformation applied.
            combined_label: The combined label from sources.
            metadata: Additional metadata.
        """
        self.content_id = content_id
        self.derived_from = derived_from or []
        self.transformation = transformation
        self.combined_label = combined_label or ContentLabel()
        self.metadata = metadata or {}
    
    def is_derived(self) -> bool:
        """Check if this content was derived from other content."""
        return len(self.derived_from) > 0
    
    def __repr__(self) -> str:
        sources = f" from {self.derived_from}" if self.derived_from else ""
        trans = f" via {self.transformation}" if self.transformation else ""
        return f"ContentLineage(id='{self.content_id}'{sources}{trans})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "content_id": self.content_id,
            "combined_label": self.combined_label.to_dict(),
        }
        if self.derived_from:
            result["derived_from"] = self.derived_from
        if self.transformation:
            result["transformation"] = self.transformation
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentLineage":
        """Create ContentLineage from dictionary."""
        return cls(
            content_id=data["content_id"],
            derived_from=data.get("derived_from"),
            transformation=data.get("transformation"),
            combined_label=ContentLabel.from_dict(data["combined_label"]) if "combined_label" in data else None,
            metadata=data.get("metadata"),
        )
