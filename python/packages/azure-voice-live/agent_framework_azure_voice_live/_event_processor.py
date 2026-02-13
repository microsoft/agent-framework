# Copyright (c) Microsoft. All rights reserved.

"""Event processor for converting Azure Voice Live events to Agent Framework updates."""

from typing import Any

from agent_framework import AgentRunResponseUpdate


class EventProcessor:
    """Converts Azure Voice Live events to Agent Framework updates.

    This class processes server events from the Azure Voice Live SDK and converts them
    into AgentRunResponseUpdate objects that are compatible with the Agent Framework's
    streaming interface.
    """

    def __init__(self) -> None:
        """Initialize event processor."""
        self._current_response_id: str | None = None
        self._function_calls: dict[str, dict[str, Any]] = {}  # Track in-progress function calls

    def process_event(self, event: Any) -> AgentRunResponseUpdate | None:
        """Convert server event to agent update.

        Args:
            event: Server event from Azure Voice Live SDK

        Returns:
            AgentRunResponseUpdate if the event should be emitted, None otherwise
        """
        # Import here to avoid circular dependency and to handle SDK availability
        try:
            from azure.ai.voicelive.models import ServerEventType
        except ImportError:
            # SDK not available, return None
            return None

        event_type = event.type

        if event_type == ServerEventType.SESSION_UPDATED:
            # Session configuration complete
            return AgentRunResponseUpdate(additional_properties={"type": "session_ready"})

        elif event_type == ServerEventType.RESPONSE_CREATED:
            # New response started
            self._current_response_id = event.response.id
            return AgentRunResponseUpdate(
                additional_properties={"type": "response_started", "response_id": event.response.id}
            )

        elif event_type == ServerEventType.RESPONSE_AUDIO_DELTA:
            # Audio chunk received
            return AgentRunResponseUpdate(
                additional_properties={
                    "type": "audio_delta",
                    "response_id": self._current_response_id,
                    "audio_data": event.delta,
                }
            )

        elif event_type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
            # Transcript chunk received
            return AgentRunResponseUpdate(
                additional_properties={
                    "type": "transcript_delta",
                    "response_id": self._current_response_id,
                    "text": event.delta,
                }
            )

        elif event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            # User started speaking (VAD detected)
            return AgentRunResponseUpdate(additional_properties={"type": "speech_started"})

        elif event_type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            # User stopped speaking (VAD detected)
            return AgentRunResponseUpdate(additional_properties={"type": "speech_stopped"})

        elif event_type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            # User audio transcription complete
            return AgentRunResponseUpdate(
                additional_properties={
                    "type": "input_transcription_complete",
                    "transcript": event.transcript if hasattr(event, "transcript") else None,
                }
            )

        elif event_type == ServerEventType.RESPONSE_OUTPUT_ITEM_ADDED:
            # New output item (message or function call) added to response
            item_type = event.item.type if hasattr(event.item, "type") else None
            if item_type == "function_call":
                # Initialize function call tracking
                item_id = event.item.id if hasattr(event.item, "id") else None
                call_id = event.item.call_id if hasattr(event.item, "call_id") else None
                name = event.item.name if hasattr(event.item, "name") else None

                print(f"[DEBUG EventProcessor] RESPONSE_OUTPUT_ITEM_ADDED: item_id={item_id}, call_id={call_id}, name={name}")
                print(f"[DEBUG EventProcessor] item attributes: {dir(event.item)}")

                # Use call_id if available, otherwise fall back to item_id
                key = call_id if call_id else item_id
                if key:
                    self._function_calls[key] = {"name": name, "arguments": ""}
                    print(f"[DEBUG EventProcessor] Stored function call with key={key}, name={name}")

        elif event_type == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DELTA:
            # Accumulate function call arguments
            call_id = event.call_id if hasattr(event, "call_id") else None
            if call_id:
                if call_id not in self._function_calls:
                    self._function_calls[call_id] = {"name": event.name if hasattr(event, "name") else None, "arguments": ""}

                # Update name if provided
                if hasattr(event, "name") and event.name:
                    self._function_calls[call_id]["name"] = event.name

                # Accumulate arguments
                if hasattr(event, "delta") and event.delta:
                    self._function_calls[call_id]["arguments"] += event.delta

                return AgentRunResponseUpdate(
                    additional_properties={
                        "type": "function_call_delta",
                        "call_id": call_id,
                        "arguments_delta": event.delta if hasattr(event, "delta") else "",
                    }
                )

        elif event_type == ServerEventType.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            # Function call complete
            call_id = event.call_id if hasattr(event, "call_id") else None
            print(f"[DEBUG EventProcessor] RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE: call_id={call_id}")
            print(f"[DEBUG EventProcessor] Known function calls: {list(self._function_calls.keys())}")

            if call_id and call_id in self._function_calls:
                call_data = self._function_calls.pop(call_id)
                print(f"[DEBUG EventProcessor] Found function call data: name={call_data['name']}, args={call_data['arguments']}")

                return AgentRunResponseUpdate(
                    additional_properties={
                        "type": "function_call",
                        "call_id": call_id,
                        "name": call_data["name"],
                        "arguments": call_data["arguments"],
                    }
                )
            else:
                print(f"[DEBUG EventProcessor] call_id {call_id} not found in tracked function calls!")

        elif event_type == ServerEventType.RESPONSE_DONE:
            # Response complete
            usage = None
            if hasattr(event, "response") and hasattr(event.response, "usage"):
                usage = event.response.usage

            result = AgentRunResponseUpdate(
                additional_properties={
                    "type": "response_complete",
                    "response_id": self._current_response_id,
                    "usage": usage,
                }
            )

            # Reset state
            self._current_response_id = None
            return result

        elif event_type == ServerEventType.ERROR:
            # Error event
            error_message = event.error if hasattr(event, "error") else "Unknown error"
            return AgentRunResponseUpdate(additional_properties={"type": "error", "error": str(error_message)})

        # Return None for unhandled event types
        return None

    def reset(self) -> None:
        """Reset processor state.

        Useful when starting a new conversation or handling connection issues.
        """
        self._current_response_id = None
        self._function_calls.clear()
