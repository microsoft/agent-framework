# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Sequence
from typing import Any, Literal, TypedDict, overload

from agent_framework import (
    AgentMiddlewareTypes,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    BaseContextProvider,
    Content,
    Message,
    ResponseStream,
    normalize_messages,
)
from agent_framework._settings import load_settings
from agent_framework._types import AgentRunInputs
from agent_framework.exceptions import AgentException
from microsoft_agents.copilotstudio.client import AgentType, ConnectionSettings, CopilotClient, PowerPlatformCloud

from ._acquire_token import acquire_token


class CopilotStudioSettings(TypedDict, total=False):
    """Copilot Studio model settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'COPILOTSTUDIOAGENT__'.

    Keys:
        environmentid: Environment ID of environment with the Copilot Studio App.
            Can be set via environment variable COPILOTSTUDIOAGENT__ENVIRONMENTID.
        schemaname: The agent identifier or schema name of the Copilot to use.
            Can be set via environment variable COPILOTSTUDIOAGENT__SCHEMANAME.
        agentappid: The app ID of the App Registration used to login.
            Can be set via environment variable COPILOTSTUDIOAGENT__AGENTAPPID.
        tenantid: The tenant ID of the App Registration used to login.
            Can be set via environment variable COPILOTSTUDIOAGENT__TENANTID.
    """

    environmentid: str | None
    schemaname: str | None
    agentappid: str | None
    tenantid: str | None


class CopilotStudioAgent(BaseAgent):
    """A Copilot Studio Agent."""

    def __init__(
        self,
        client: CopilotClient | None = None,
        settings: ConnectionSettings | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
        middleware: list[AgentMiddlewareTypes] | None = None,
        environment_id: str | None = None,
        agent_identifier: str | None = None,
        client_id: str | None = None,
        tenant_id: str | None = None,
        token: str | None = None,
        cloud: PowerPlatformCloud | None = None,
        agent_type: AgentType | None = None,
        custom_power_platform_cloud: str | None = None,
        username: str | None = None,
        token_cache: Any | None = None,
        scopes: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the Copilot Studio Agent.

        Args:
            client: Optional pre-configured CopilotClient instance. If not provided,
                a new client will be created using the other parameters.
            settings: Optional pre-configured ConnectionSettings. If not provided,
                settings will be created from the other parameters.

        Keyword Args:
            id: id of the CopilotAgent
            name: Name of the CopilotAgent
            description: Description of the CopilotAgent
            context_providers: Context Providers, to be used by the copilot agent.
            middleware: Agent middleware used by the agent, should be a list of AgentMiddlewareTypes.
            environment_id: Environment ID of the Power Platform environment containing
                the Copilot Studio app. Can also be set via COPILOTSTUDIOAGENT__ENVIRONMENTID
                environment variable.
            agent_identifier: The agent identifier or schema name of the Copilot to use.
                Can also be set via COPILOTSTUDIOAGENT__SCHEMANAME environment variable.
            client_id: The app ID of the App Registration used for authentication.
                Can also be set via COPILOTSTUDIOAGENT__AGENTAPPID environment variable.
            tenant_id: The tenant ID of the App Registration used for authentication.
                Can also be set via COPILOTSTUDIOAGENT__TENANTID environment variable.
            token: Optional pre-acquired authentication token. If not provided,
                token acquisition will be attempted using MSAL.
            cloud: The Power Platform cloud to use (Public, GCC, etc.).
            agent_type: The type of Copilot Studio agent (Copilot, Agent, etc.).
            custom_power_platform_cloud: Custom Power Platform cloud URL if using
                a custom environment.
            username: Optional username for token acquisition.
            token_cache: Optional token cache for storing authentication tokens.
            scopes: Optional list of authentication scopes. Defaults to Power Platform
                API scopes if not provided.
            env_file_path: Optional path to .env file for loading configuration.
            env_file_encoding: Encoding of the .env file, defaults to 'utf-8'.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        super().__init__(
            id=id,
            name=name,
            description=description,
            context_providers=context_providers,
            middleware=middleware,
        )
        if not client:
            copilot_studio_settings = load_settings(
                CopilotStudioSettings,
                env_prefix="COPILOTSTUDIOAGENT__",
                environmentid=environment_id,
                schemaname=agent_identifier,
                agentappid=client_id,
                tenantid=tenant_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )

            if not settings:
                if not copilot_studio_settings["environmentid"]:
                    raise ValueError(
                        "Copilot Studio environment ID is required. Set via 'environment_id' parameter "
                        "or 'COPILOTSTUDIOAGENT__ENVIRONMENTID' environment variable."
                    )
                if not copilot_studio_settings["schemaname"]:
                    raise ValueError(
                        "Copilot Studio agent identifier/schema name is required. Set via 'agent_identifier' parameter "
                        "or 'COPILOTSTUDIOAGENT__SCHEMANAME' environment variable."
                    )

                settings = ConnectionSettings(
                    environment_id=copilot_studio_settings["environmentid"],
                    agent_identifier=copilot_studio_settings["schemaname"],
                    cloud=cloud,
                    copilot_agent_type=agent_type,
                    custom_power_platform_cloud=custom_power_platform_cloud,
                )

            if not token:
                if not copilot_studio_settings["agentappid"]:
                    raise ValueError(
                        "Copilot Studio client ID is required. Set via 'client_id' parameter "
                        "or 'COPILOTSTUDIOAGENT__AGENTAPPID' environment variable."
                    )

                if not copilot_studio_settings["tenantid"]:
                    raise ValueError(
                        "Copilot Studio tenant ID is required. Set via 'tenant_id' parameter "
                        "or 'COPILOTSTUDIOAGENT__TENANTID' environment variable."
                    )

                token = acquire_token(
                    client_id=copilot_studio_settings["agentappid"],
                    tenant_id=copilot_studio_settings["tenantid"],
                    username=username,
                    token_cache=token_cache,
                    scopes=scopes,
                )

            client = CopilotClient(settings=settings, token=token)

        self.client = client
        self.cloud = cloud
        self.agent_type = agent_type
        self.custom_power_platform_cloud = custom_power_platform_cloud
        self.username = username
        self.token_cache = token_cache
        self.scopes = scopes

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentResponse object. When stream=True, it returns
        a ResponseStream that yields AgentResponseUpdate objects.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            stream: Whether to stream the response. Defaults to False.
            session: The conversation session associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            When stream=False: An Awaitable[AgentResponse].
            When stream=True: A ResponseStream of AgentResponseUpdate items.
        """
        if stream:
            return self._run_stream_impl(messages=messages, session=session, **kwargs)
        return self._run_impl(messages=messages, session=session, **kwargs)

    async def _run_impl(
        self,
        messages: AgentRunInputs | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Non-streaming implementation of run."""
        if not session:
            session = self.create_session()
        session.service_session_id = await self._start_new_conversation()

        input_messages = normalize_messages(messages)

        question = "\n".join([message.text for message in input_messages])

        activities = self.client.ask_question(question, session.service_session_id)
        response_messages: list[Message] = []
        response_id: str | None = None

        response_messages = [message async for message in self._process_activities(activities, streaming=False)]
        response_id = response_messages[0].message_id if response_messages else None

        return AgentResponse(messages=response_messages, response_id=response_id)

    def _run_stream_impl(
        self,
        messages: AgentRunInputs | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        """Streaming implementation of run."""

        async def _stream() -> AsyncIterable[AgentResponseUpdate]:
            nonlocal session
            if not session:
                session = self.create_session()
            session.service_session_id = await self._start_new_conversation()

            input_messages = normalize_messages(messages)

            question = "\n".join([message.text for message in input_messages])

            activities = self.client.ask_question(question, session.service_session_id)

            async for message in self._process_activities(activities, streaming=True):
                yield AgentResponseUpdate(
                    role=message.role,
                    contents=message.contents,
                    author_name=message.author_name,
                    raw_representation=message.raw_representation,
                    response_id=message.message_id,
                    message_id=message.message_id,
                )

        def _finalize(updates: Sequence[AgentResponseUpdate]) -> AgentResponse[None]:
            return AgentResponse.from_updates(updates)

        return ResponseStream(_stream(), finalizer=_finalize)

    async def _start_new_conversation(self) -> str:
        """Start a new conversation with the Copilot Studio agent.

        Returns:
            The conversation ID for the new conversation.

        Raises:
            AgentException: If the conversation could not be started.
        """
        conversation_id: str | None = None

        async for activity in self.client.start_conversation(emit_start_conversation_event=True):
            if activity and activity.conversation and activity.conversation.id:
                conversation_id = activity.conversation.id

        if not conversation_id:
            raise AgentException("Failed to start a new conversation.")

        return conversation_id

    async def _process_activities(self, activities: AsyncIterable[Any], streaming: bool) -> AsyncIterable[Message]:
        """Process activities from the Copilot Studio agent.

        Args:
            activities: Stream of activities from the agent.
            streaming: Whether to process activities for streaming (typing activities)
                or non-streaming (message activities) responses.

        Yields:
            Message objects created from the activities.
        """
        async for activity in activities:
            if activity.text and (
                (activity.type == "message" and not streaming) or (activity.type == "typing" and streaming)
            ):
                yield Message(
                    role="assistant",
                    contents=[Content.from_text(activity.text)],
                    author_name=activity.from_property.name if activity.from_property else None,
                    message_id=activity.id,
                    raw_representation=activity,
                )
