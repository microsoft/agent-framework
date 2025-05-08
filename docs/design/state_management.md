# State Management

## Current State APIs

### AutoGen

The state management model is a pull-based model from the host-side, leaving agents to manage state internally on their own.

```python

class Agent(Protocol):
    # ...
    async def save_state(self) -> Mapping[str, Any]:
        """Save the state of the agent. The result must be JSON serializable."""
        ...

    async def load_state(self, state: Mapping[str, Any]) -> None:
        """Load in the state of the agent obtained from `save_state`.

        Args:
            state (Mapping[str, Any]): State of the agent. Must be JSON serializable.
        """

        ...

    ...

```

Similar APIs exist at the level of the runtime, both agent-scoped and runtime-scoped, allowing the host to save and load the state when they wish, when they have control over the execution.

```python

class AgentRuntime(Protocol):
    # ...

    async def save_state(self) -> Mapping[str, Any]:
        """Save the state of the entire runtime, including all hosted agents. The only way
        to restore the state is to pass it to :meth:`load_state`.

        The structure of the state is implementation defined and can be any JSON serializable
         object.

        Returns:
            Mapping[str, Any]: The saved state.
        """
        ...

    async def load_state(self, state: Mapping[str, Any]) -> None:
        """Load the state of the entire runtime, including all hosted agents. The state
        should be the same as the one returned by :meth:`save_state`.

        Args:
            state (Mapping[str, Any]): The saved state.
        """
        ...

    # ...

    async def agent_save_state(self, agent: AgentId) -> Mapping[str, Any]:
        """Save the state of a single agent.

        The structure of the state is implementation defined and can be any JSON
        serializable object.

        Args:
            agent (AgentId): The agent id.

        Returns:
            Mapping[str, Any]: The saved state.
        """
        ...

    async def agent_load_state(self, agent: AgentId, state: Mapping[str, Any]) -> None:
        """Load the state of a single agent.

        Args:
            agent (AgentId): The agent id.
            state (Mapping[str, Any]): The saved state.
        """
        ...

    ...

```

### SemanticKernel Agent Framework

The Semantic Kernel Agents Framework embeds state management in the AgentThread object. Stateful Agents have corresponding AgentThread objects (e.g. `AzureAIAgent` => `AzureAIAgentThread`), and rely the AgentThread to manage state, which for the most part seems to be only used to keep ChatMessageData objects.

```python

class AgentThread(ABC):

    # ...

    @abstractmethod
    async def _create(self) -> str:
        """Starts the thread and returns the thread ID."""
        raise NotImplementedError

    @abstractmethod
    async def _delete(self) -> None:
        """Ends the current thread."""
        raise NotImplementedError

    @abstractmethod
    async def _on_new_message(
        self,
        new_message: ChatMessageContent,
    ) -> None:
        """Invoked when a new message has been contributed to the chat by any
        participant."""
        raise NotImplementedError

```

When the agent is invoked, the thread (or None) is passed to the agent, and the response contains the modified thread, allowing it to be shared to another agent, or passed back to the agent after being modified directly.

```python

class Agent(KernelBaseModel, ABC):
    # ...

    @abstractmethod
    def get_response(
        self,
        *,
        messages: str | ChatMessageContent | list[str | ChatMessageContent] | None = None,
        thread: AgentThread | None = None,
        **kwargs,
    ) -> Awaitable[AgentResponseItem[ChatMessageContent]]:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single ChatMessageContent object. The caller is blocked until
        the final result is available.

        Note: For streaming responses, use the invoke_stream method, which returns
        intermediate steps and the final result as a stream of StreamingChatMessageContent
        objects. Streaming only the final result is not feasible because the timing of
        the final result's availability is unknown, and blocking the caller until then
        is undesirable in streaming scenarios.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        pass

    ...

# Usage:
# From: https://github.com/microsoft/semantic-kernel/blob/main/python/samples/getting_started_with_agents/chat_completion/step2_chat_completion_agent_thread_management.py

agent = ChatCompletionAgent(...)

thread: ChatHistoryAgentThread = None

for user_input in USER_INPUTS:
        print(f"# User: {user_input}")
        # 3. Invoke the agent for a response
        response = await agent.get_response(
            messages=user_input,
            thread=thread,
        )
        print(f"# {response.name}: {response}")
        # 4. Store the thread, which allows the agent to
        # maintain conversation history across multiple messages.
        thread = response.thread

```

When participating in group chat, the `AgentChannel` object takes care of managing the thread and invoking the underlying agent.

## Semantic Kernel Process Framework

The Semantic Kernel Process Framework deals with state explicitly, letting Steps declare their state object requirements freely. This state is serialized on every message in the Dapr runtime, using the APIs that are also available to the user to dump the state, similar to the AutoGen APIs. The state is also created during the activation of the step.

```python

    async def handle_message(self, message: ProcessMessage):
        # ...

            if self.step_state is not None:
                state_dict = self.step_state.model_dump()
                await self._state_manager.set_state(ActorStateKeys.StepStateJson.value, json.dumps(state_dict))
                await self._state_manager.save_state()

        ...

```

## Desiderata

* State Checkpoint Semantics

We want to be able to checkpoint between every agent turn - which corresponds to a single AgentResponse from the non-streaming case. This will support the capability to create durable processes, that could be resumed from an interruption, paused, migrated, etc.

* Low-Cost Abstractions

We want to support the ability to avoid copying and saving/loading the state objects if this is not necessary. Especially in the case of on-device, in-process, attempting to run as low-latency as possible, in e.g. interactive scenarios.

* Friendly Agent-Side APIs

We want to make it easy for agents to manage their state, and we want to make it invisible for agents that do not need to manage state. Ideally the agent should be able to be able to request its state when needed, and queue and update when desired. The update would be real for the agent during the processing of the turn, and would become real for the "runtime" (visible from the host when save/load is called).

* Questions:

Is it desireable to create an event for agent state updates for the host to hook into?

## Design Discussion

### Agent State Management

Remove the `save_state` and `load_state` APIs from the runtime's `Agent` protocol.

Instead, state management will be provided by a capability on/alongide the `MessageContext` object in the `handle_message` etc. methods, transferring ownership of state management to the runtime implementation.

```python

# TState is a Pydantic BaseModel
TState = TypeVar("TState", bound=BaseModel)

class StateContext[TState](Protocol):
    def get(self) -> TState:
        """Get the state of the agent."""
        ...

    def update(self, state: TState) -> None:
        """Set the state of the agent. The state will be update in the runtime at the end of
         the current turn."""
        ...

    def reset(self) -> None:
        """Reset the state of the agent to its initial value at the beginning of the turn."""
        ...

```

Calling `update` will let the runtime know that the state has been updated, but will not propagate it to be visible to the host until the agent returns the response. However, the agent will now be able to see the new state on subsequent calls to `get`. This behaves similar to a transaction operating at the turn level. Once the agent completes the turn, the runtime will consider the transaction committed, and will make the state visible to the host and later instantiations of the agent.

### Runtime State Management

From the runtime point of view, state management can be provided by a `StateManager` object (with a default fully-in-memory implementation), that can be optionally passed to the runtime on initialization, or using the component system:

```python

@dataclass
class AgentStateEntry[TState]:
    scope: AgentId
    type_: Type[TState]
    version: int # str?
    state: TState

@runtime_checkable
class StateManager(Protocol):
    def get_agent_state(self, scope: AgentId) -> AgentStateEntry:
        """Get the state of the agent."""
        ...

    def set_agent_state(self, scope: AgentId, state: AgentStateEntry) -> None:
        """Set the state of the agent."""
        ...

    # TODO: Test that this works, otherwise provide a helper function
    @property
    def is_exportable(self) -> bool:
        """Check if the state manager is exportable."""
        if isinstance(self, "ExportableStateManager"):
            return True

        return False

@runttime_checkable
class ExportableStateManager(StateManager):
    def dump_state(self) -> Mapping[str, Any]:
        """Dump the state of the runtime."""
        ...

    def load_state(self, state: Mapping[str, Any]) -> None:
        """Load the state of the runtime."""
        ...


class TurnStateContext[TState](StateContext[TState]):
    def __init__(self, state_entry: AgentStateEntry[TState]):
        self.state_entry = state_entry
        self._state : TState | None = None

    def get(self) -> TState:
        """Get the state of the agent."""
        if self._state is not None:
            return self._state

        return self.state_entry.state

    def update(self, state: TState) -> None:
        """Set the state of the agent. The state will be update in the runtime at the end of
        the current turn."""
        self._state = state

    def reset(self) -> None:
        """Reset the state of the agent to its initial value at the beginning of the turn."""
        self._state = None

    def complete(self, state_manager: StateManager) -> None:
        """Complete the state update."""
        if self._state is not None:
            state_manager.set_agent_state(self.state_entry.scope, self.state_entry)
            self._state = None

```

This ensures that we still have largely the same capabilities as the current runtime, while formalizing the checkpointable semantics that we desire, and allowing for more flexible state management that simply always exporting to JSON. We rely on Pydantic to handle the actual data modeling, as well as being our bridge to serialization.

If a state is not exportable, or does not exist, the corresponding `agent_save_state` and `save_state` calls will contain empty state objects.

## Alternatives to Consider

* Externalize the state, more closely aligned with how AgentThread is managed in SemanticKernel

This is similar to the proposed design, except the state object is passed to the agent on initialization (similar to id and runtime), and also on the `handle_message` method, and returned back to the runtime on the response. The benefit is that this is much more explicit, and simpler at the runtime level. We could avoid forcing superfluous state updated by allowing the agent to return None for the state object if it is unchanged, or check if the state is the same as the one passed in (though checking this rigorously may be a challenge, depending on the actual data structure)

* Allow the agent to save multiple, more granular chunks of state

This would be more simliar to Dapr, changing the StateContext API to be keyed:

```python

# TKey here may just be a string, though it would be nice for the user to be able to
# specify a restriction on the values using e.g. Literal
class StateContext[TKey](Protocol):
    def get[TState](self, key: TKey) -> TState: # there may be a difficulty with the typing here
        """Get the state of the agent."""
        ...

    def update[TState](self, key: TKey, state: TState) -> None:
        """Set the state of the agent. The state will be update in the runtime at
        the end of the current turn."""
        ...

    def reset(self, key: TKey) -> None:
        """Reset the state of the agent to its initial value at the beginning of the
        turn."""
        ...

```

This would propagate into the Runtime APIs and `AgentStateEntry` object to instead be a mapping of keys to state objects, but would allow us to remove it from the Agent / StateContext APIs.

* Move runtime state management to the StateManager object

This would be similar to the current design, but would move the state management to the `StateManager` object, and remove the `save_state` and `load_state` APIs from the runtime. This would allow for more flexible state management, but would require more work to implement, and make the type signatures more complex, since we would need to notify the state manager of the type of the runtime state. Some way to make this easy for StateManager implementors to manage would be needed, potentially a higher level of abstraction representing a repository, which can be given the appropriate types to instantiate the state manager.

```python

class StateRepository(Protocol):
    def create_manager(self, runtime_state_type: Type[TState]) -> StateManager[TState]:
        """Create a state manager for the runtime state."""
        ...

```

* Shared State

It is conceivable we may want to share state between agents, or between the runtime and the agent. We would enable this by adding a `share` method to the `StateContext` object, which would allow an agent to make a state object shareable. In return this would grant the agent a "token" that other agents could redeem to access the state:

```python

class StateContext[TState](Protocol):
    def share(self) -> ShareToken:
        """Share the state of the agent. The state will be update in the runtime at the
         end of the current turn."""
        ...

```

In the case of unkeyed `StateContext`, the means to redeem a token will live on the `MessageContext` or `AgentRuntime` object; putting it on `MessageContext` may seem weird, but it does have the ability to capture the appropriate turn context to be able to manage the state. The `AgentRuntime` will also have it, but may require some logic to map to it. In the case of keyed `StateContext`, we change the `get` and `update` methods to support taking a token in place of a key.

The challenge for state sharing arises from the case of the distributed runtime. Especially in the case of an underlying `StateManager` which lives on, e.g. a database. The best solution here is likely to create supporting components enabling message-based state sync between disparate instances of `StateManager` via runtime-internal messaging, but if the implementor does not require it, no sync messages will be sent. A similar protocol can be used to enable a "cache" abstraction over the top of a repository-specific StateManager implementation, but allowing cache invalidation / local updates to occur via messaging, but defer to underlying storage to actually retrieve uncached state.

* Non-persisted Shared State

This is similar to the shared state proposal; to enable this we can reuse the message-based

* State-type-specific Repository

This is very much out of the scope of the current design, but an additional layer of abstraction could be to let us create type-specific mappings to a different underlying Repository. Composing this could prove challenging, so we may want to consider creating a builder to complement the configuration approach to defining a storage strategy.

Composition here could be managed by providing type-specific strategies, which `StateManager` would drive under the hood.

A big challenge here would be managing something akin to a two-phase commit when needing to coordinate across the repositories, or some other external synchronization mechanism. It is not clear what an ergonomic API for this would look like, especially if there is desire to support esoteric approaches like CRDTs or consensus algorithms.

## Proposal

* Use the base design as a starting point, but use keyed state at the `StateContext` level
* Create the Repository abstraction, and use it to give `AgentRuntime` access to state management as well
* Enable shared state using lower-level runtime-specific sync helpers for implementing StateManager/Repository
* Create a default InMemory ExportableStateManager as a baseline (and sample) implementation