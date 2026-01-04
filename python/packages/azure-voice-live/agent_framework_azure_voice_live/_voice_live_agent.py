# Copyright (c) Microsoft. All rights reserved.

"""Azure Voice Live Agent implementation."""

import asyncio
from collections.abc import AsyncIterable
from typing import Any

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, AgentThread, AIFunction, BaseAgent

from ._voice_live_session import VoiceLiveSession


class VoiceLiveAgent(BaseAgent):
    """Real-time voice agent using Azure Voice Live SDK.

    This agent enables real-time voice conversations with streaming audio,
    server-side voice activity detection, and function calling support.

    Example:
        ```python
        from agent_framework_azure_voice_live import VoiceLiveAgent
        from azure.identity.aio import DefaultAzureCredential

        agent = VoiceLiveAgent(
            endpoint="https://YOUR_RESOURCE.openai.azure.com",
            model="gpt-4o-realtime-preview",
            credential=DefaultAzureCredential(),
            voice="en-US-AvaNeural",
            instructions="You are a helpful assistant.",
        )

        # Text input -> Voice output
        response = await agent.run("Hello!")

        # Voice input -> Voice output
        with open("audio.pcm", "rb") as f:
            response = await agent.run(f.read())
        ```
    """

    def __init__(
        self,
        *,
        endpoint: str,
        model: str = "gpt-4o-realtime-preview",
        credential: Any,
        voice: str = "en-US-AvaNeural",
        instructions: str | None = None,
        tools: list[AIFunction] | None = None,
        temperature: float = 0.8,
        max_response_tokens: int | None = None,
        # VAD settings
        enable_vad: bool = True,
        vad_threshold: float = 0.5,
        vad_prefix_padding_ms: int = 300,
        vad_silence_duration_ms: int = 500,
        # Audio settings
        input_audio_format: str = "pcm16",
        output_audio_format: str = "pcm16",
        input_audio_transcription: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize VoiceLiveAgent.

        Args:
            endpoint: Azure OpenAI endpoint (e.g., "https://YOUR_RESOURCE.openai.azure.com")
            model: Model deployment name (default: "gpt-4o-realtime-preview")
            credential: Azure credential (AzureKeyCredential or TokenCredential)
            voice: Azure voice name (default: "en-US-AvaNeural")
            instructions: System instructions for the agent
            tools: List of AIFunction tools the agent can use
            temperature: Sampling temperature (0.0-1.0)
            max_response_tokens: Maximum tokens in response
            enable_vad: Enable server-side voice activity detection
            vad_threshold: VAD sensitivity (0.0-1.0, higher = less sensitive)
            vad_prefix_padding_ms: Milliseconds of audio before speech to include
            vad_silence_duration_ms: Milliseconds of silence to detect end of speech
            input_audio_format: Input audio format (default: "pcm16")
            output_audio_format: Output audio format (default: "pcm16")
            input_audio_transcription: Enable automatic transcription of user audio
            **kwargs: Additional arguments passed to BaseAgent
        """
        super().__init__(name=kwargs.pop("name", f"VoiceLiveAgent_{model}"), **kwargs)

        self._endpoint = endpoint
        self._model = model
        self._credential = credential
        self._voice = voice
        self._instructions = instructions
        self._tools = tools or []
        self._temperature = temperature
        self._max_response_tokens = max_response_tokens

        # VAD configuration
        self._enable_vad = enable_vad
        self._vad_threshold = vad_threshold
        self._vad_prefix_padding_ms = vad_prefix_padding_ms
        self._vad_silence_duration_ms = vad_silence_duration_ms

        # Audio formats (for future extensibility)
        self._input_audio_format = input_audio_format
        self._output_audio_format = output_audio_format
        self._input_audio_transcription = input_audio_transcription

        # Session management for multi-turn conversations
        self._session: Any = None

    async def connect(self) -> None:
        """Connect to Azure Voice Live and establish a persistent session.

        This enables multi-turn conversations without recreating the session each time.
        Call this before using run() or run_stream().
        """
        if self._session is not None:
            return  # Already connected

        self._session = VoiceLiveSession(
            endpoint=self._endpoint,
            model=self._model,
            credential=self._credential,
            config=self._build_session_config(),
        )
        await self._session.__aenter__()

    async def disconnect(self) -> None:
        """Disconnect from Azure Voice Live and close the session.

        Call this when done with the conversation.
        """
        if self._session is not None:
            await self._session.__aexit__(None, None, None)
            self._session = None

    async def run(
        self,
        input: str | bytes,  # Text or PCM16 audio bytes
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Run agent with text or audio input.

        Args:
            input: User input (text string or PCM16 audio bytes)
            thread: Optional conversation thread (not yet implemented)
            **kwargs: Additional arguments

        Returns:
            AgentRunResponse with audio content and transcript

        Example:
            ```python
            # Single-turn usage (auto-manages session):
            response = await agent.run("What's the weather?")

            # Multi-turn usage (persistent session):
            await agent.connect()
            response1 = await agent.run("What's the weather?")
            response2 = await agent.run("How about tomorrow?")
            await agent.disconnect()
            ```
        """
        # Auto-connect if not already connected
        use_temp_session = self._session is None

        if use_temp_session:
            # Create temporary session for single-turn use
            session = VoiceLiveSession(
                endpoint=self._endpoint,
                model=self._model,
                credential=self._credential,
                config=self._build_session_config(),
            )
            async with session:
                return await self._run_with_session(session, input)
        else:
            # Use persistent session
            return await self._run_with_session(self._session, input)

    async def _run_with_session(self, session: VoiceLiveSession, input: str | bytes) -> AgentRunResponse:
        """Internal method to run with a given session."""
        # Send input
        if isinstance(input, str):
            await session.send_text(input)
            await session.create_response()
        else:
            await session.send_audio(input, commit=self._enable_vad)
            if not self._enable_vad:
                await session.create_response()

        # Collect response
        return await session.collect_response()

    async def run_stream(
        self,
        input: str | bytes,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream voice responses in real-time.

        Args:
            input: User input (text string or PCM16 audio bytes)
            thread: Optional conversation thread (not yet implemented)
            **kwargs: Additional arguments

        Yields:
            AgentRunResponseUpdate objects with audio deltas and transcript deltas

        Example:
            ```python
            # Single-turn streaming:
            async for update in agent.run_stream("Tell me a story"):
                if update.additional_properties.get("type") == "audio_delta":
                    audio_player.play(update.additional_properties["audio_data"])

            # Multi-turn streaming:
            await agent.connect()
            async for update in agent.run_stream("Hello"):
                process_update(update)
            async for update in agent.run_stream("Tell me more"):
                process_update(update)
            await agent.disconnect()
            ```
        """
        # Auto-connect if not already connected
        use_temp_session = self._session is None

        if use_temp_session:
            # Create temporary session for single-turn use
            session = VoiceLiveSession(
                endpoint=self._endpoint,
                model=self._model,
                credential=self._credential,
                config=self._build_session_config(),
            )
            async with session:
                async for update in self._run_stream_with_session(session, input):
                    yield update
        else:
            # Use persistent session
            async for update in self._run_stream_with_session(self._session, input):
                yield update

    async def _run_stream_with_session(
        self, session: VoiceLiveSession, input: str | bytes
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Internal method to stream with a given session."""
        # Send input
        if isinstance(input, str):
            await session.send_text(input)
            await session.create_response()
        else:
            await session.send_audio(input, commit=self._enable_vad)
            if not self._enable_vad:
                await session.create_response()

        # Stream response updates
        async for update in session.stream_response():
            yield update

    async def stream_audio_chunk(self, audio_chunk: bytes) -> None:
        """Stream a single audio chunk for continuous input.

        This is used for streaming conversations where audio is captured
        continuously from the microphone and sent in real-time, rather than
        recording a complete buffer first.

        Args:
            audio_chunk: Raw PCM16 audio chunk (24kHz, mono, 16-bit)

        Raises:
            RuntimeError: If session is not connected

        Example:
            ```python
            await agent.connect()

            # Continuously stream audio chunks
            while recording:
                chunk = mic.read_chunk()
                await agent.stream_audio_chunk(chunk)

            await agent.disconnect()
            ```
        """
        if not self._session:
            raise RuntimeError("Must call connect() before streaming audio chunks")

        await self._session.send_audio_chunk(audio_chunk)

    async def listen_to_responses(self) -> AsyncIterable[AgentRunResponseUpdate]:
        """Listen to all response events continuously.

        This streams all events from the session, not just a single response.
        Used for streaming conversations where the agent can respond multiple
        times as the user speaks.

        Automatically handles function calls in the background.

        Yields:
            AgentRunResponseUpdate objects for each event

        Raises:
            RuntimeError: If session is not connected

        Example:
            ```python
            await agent.connect()

            async for update in agent.listen_to_responses():
                if update.additional_properties.get("type") == "audio_delta":
                    audio_player.play(update.additional_properties["audio_data"])
                elif update.additional_properties.get("type") == "transcript_delta":
                    print(update.additional_properties["text"], end="")

            await agent.disconnect()
            ```
        """
        if not self._session:
            raise RuntimeError("Must call connect() before listening to responses")

        pending_function_call = None

        async for update in self._session.stream_all_events():
            props = update.additional_properties or {}
            event_type = props.get("type")

            # Handle function calls automatically
            if event_type == "function_call":
                print(f"\n[DEBUG] Function call detected: {props.get('name')}")
                # Store pending function call to execute after response_done
                pending_function_call = {
                    "call_id": props.get("call_id"),
                    "name": props.get("name"),
                    "arguments": props.get("arguments")
                }

            # When response is done, execute any pending function call
            elif event_type == "response_complete" and pending_function_call:
                print(f"[DEBUG] Response done, executing pending function call")
                # Execute function and create new response
                asyncio.create_task(self._handle_function_call_after_response(
                    pending_function_call["call_id"],
                    pending_function_call["name"],
                    pending_function_call["arguments"]
                ))
                pending_function_call = None

            yield update

    async def _handle_function_call_after_response(self, call_id: str, name: str, arguments: str) -> None:
        """Handle function call execution after response is done, then trigger new response.

        Args:
            call_id: Function call ID
            name: Function name
            arguments: JSON string of arguments
        """
        import json

        print(f"[DEBUG] Executing function: {name} with call_id={call_id}, args={arguments}")

        try:
            # Parse arguments
            args_dict = json.loads(arguments) if arguments else {}

            # Find the function
            function = None
            for tool in self._tools:
                if tool.name == name:
                    function = tool
                    break

            if not function:
                result = f"Error: Function '{name}' not found"
                print(f"[DEBUG] Function not found: {name}")
            else:
                # Execute the function
                print(f"[DEBUG] Calling function {name} with args: {args_dict}")
                result = await function(**args_dict)
                print(f"[DEBUG] Function {name} returned: {result}")

            # Send result back
            print(f"[DEBUG] Sending function result for call_id={call_id}")
            await self._session.send_function_result(call_id, str(result))
            print(f"[DEBUG] Function result sent successfully")

            # Now trigger a new response to process the function result
            # This is safe because we waited for RESPONSE_DONE
            print(f"[DEBUG] Creating new response to process function result")
            await self._session.create_response()
            print(f"[DEBUG] New response created")

        except Exception as e:
            error_msg = f"Error executing {name}: {e}"
            print(f"[DEBUG] Exception in function execution: {e}")
            import traceback
            traceback.print_exc()
            try:
                await self._session.send_function_result(call_id, error_msg)
                await self._session.create_response()
            except Exception as e2:
                print(f"[DEBUG] Failed to send error result: {e2}")

    async def cancel_response(self) -> None:
        """Cancel the ongoing agent response.

        This is used for interruption handling - when the user starts speaking
        while the agent is responding, call this to stop the agent's response.

        Raises:
            RuntimeError: If session is not connected

        Example:
            ```python
            await agent.connect()

            # If user interrupts, cancel the response
            if user_started_speaking and agent_is_speaking:
                await agent.cancel_response()

            await agent.disconnect()
            ```
        """
        if not self._session:
            raise RuntimeError("Must call connect() before canceling response")

        await self._session.cancel_response()

    def _build_session_config(self) -> Any:
        """Build Azure Voice Live session configuration.

        Returns:
            RequestSession configuration object
        """
        from azure.ai.voicelive.models import (
            AzureStandardVoice,
            InputAudioFormat,
            Modality,
            OutputAudioFormat,
            RequestSession,
            ServerVad,
        )

        # Configure VAD
        turn_detection = None
        if self._enable_vad:
            turn_detection = ServerVad(
                threshold=self._vad_threshold,
                prefix_padding_ms=self._vad_prefix_padding_ms,
                silence_duration_ms=self._vad_silence_duration_ms,
            )

        # Configure transcription
        input_audio_transcription = None
        if self._input_audio_transcription:
            input_audio_transcription = {"model": "whisper-1"}

        # Build session config
        return RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            instructions=self._instructions,
            voice=AzureStandardVoice(name=self._voice),
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            input_audio_transcription=input_audio_transcription,
            turn_detection=turn_detection,
            tools=self._convert_tools_to_azure_format(),
            temperature=self._temperature,
            max_response_output_tokens=self._max_response_tokens,
        )

    def _convert_tools_to_azure_format(self) -> list[Any]:
        """Convert AIFunction tools to Azure Voice Live format.

        Returns:
            List of FunctionTool objects in Azure format
        """
        from azure.ai.voicelive.models import FunctionTool

        azure_tools = []

        for tool in self._tools:
            # Get the JSON schema from the tool
            if hasattr(tool, 'to_json_schema_spec'):
                schema = tool.to_json_schema_spec()

                # Extract function details from schema
                func_spec = schema.get('function', {})

                # Create Azure FunctionTool using dict-style assignment
                azure_tool = FunctionTool()
                azure_tool['type'] = 'function'
                azure_tool['name'] = func_spec.get('name', tool.name)
                azure_tool['description'] = func_spec.get('description', '')
                azure_tool['parameters'] = func_spec.get('parameters', {})

                azure_tools.append(azure_tool)
                print(f"[DEBUG] Tool converted: {tool.name} -> {dict(azure_tool)}")
            else:
                # Fallback for non-AIFunction tools
                azure_tool = FunctionTool()
                azure_tool['type'] = 'function'
                azure_tool['name'] = getattr(tool, 'name', 'unknown')
                azure_tool['description'] = getattr(tool, 'description', '')
                azure_tool['parameters'] = tool.parameters() if callable(getattr(tool, 'parameters', None)) else {}

                azure_tools.append(azure_tool)
                print(f"[DEBUG] Tool converted (fallback): {dict(azure_tool)}")

        print(f"[DEBUG] Total tools converted: {len(azure_tools)}")
        return azure_tools
