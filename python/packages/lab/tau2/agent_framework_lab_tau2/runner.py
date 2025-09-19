# Copyright (c) Microsoft. All rights reserved.

import uuid
from typing import cast

from agent_framework._agents import ChatAgent
from agent_framework._types import AgentRunResponse, ChatMessage, Role
from agent_framework._workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    FunctionExecutor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
)
from agent_framework.openai import OpenAIChatClient
from loguru import logger
from tau2.data_model.simulation import SimulationRun, TerminationReason  # type: ignore[import-untyped]
from tau2.data_model.tasks import Task  # type: ignore[import-untyped]
from tau2.domains.airline.environment import get_environment  # type: ignore[import-untyped]
from tau2.evaluator.evaluator import EvaluationType, RewardInfo, evaluate_simulation  # type: ignore[import-untyped]
from tau2.user.user_simulator import (  # type: ignore[import-untyped]
    OUT_OF_SCOPE,
    STOP,
    TRANSFER,
    get_global_user_sim_guidelines,
)
from tau2.utils.utils import get_now  # type: ignore[import-untyped]

from ._message_utils import flip_messages, log_messages
from ._sliding_window import SlidingWindowChatMessageList
from ._tau2_utils import convert_agent_framework_messages_to_tau2_messages, convert_tau2_tool_to_ai_function

# Agent instructions matching tau2's LLMAgent
ASSISTANT_AGENT_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.
Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
""".strip()

# Default first message from agent (matching tau2)
DEFAULT_FIRST_AGENT_MESSAGE = "Hi! How can I help you today?"

# Constants of Agent executor IDs
ASSISTANT_AGENT_ID = "assistant_agent"
USER_SIMULATOR_ID = "user_simulator"
ORCHESTRATOR_ID = "orchestrator"


class TaskRunner:
    """Orchestrates task execution using agent framework workflows for tau2 benchmarks.

    Manages conversation flow between assistant agents and user simulators,
    handles termination conditions, and evaluates performance using tau2 metrics.

    Only "airline" domain is supported for now.
    """

    # State tracking
    step_count: int
    full_conversation: list[ChatMessage]
    termination_reason: TerminationReason | None
    full_reward_info: RewardInfo | None
    _final_user_message: list[ChatMessage] | None
    _assistant_executor: AgentExecutor | None
    _user_executor: AgentExecutor | None

    # Configuration
    max_steps: int
    assistant_sampling_temperature: float
    assistant_window_size: int

    def __init__(self, max_steps: int, assistant_sampling_temperature: float = 0.0, assistant_window_size: int = 32768):
        """Initialize the TaskRunner.

        Args:
            max_steps: The maximum number of steps to run.
            assistant_sampling_temperature: The sampling temperature for the assistant agent.
            assistant_window_size: The window size for the assistant agent.
        """
        self.assistant_sampling_temperature = assistant_sampling_temperature
        self.assistant_window_size = assistant_window_size
        self.max_steps = max_steps
        self.reinit()

    def reinit(self) -> "TaskRunner":
        """Reset all state for a new task run."""
        self.step_count = 0
        self.full_conversation = []
        self.termination_reason = None
        self.full_reward_info = None
        self._final_user_message = None
        self._assistant_executor = None
        self._user_executor = None
        logger.info("TaskRunner has been re-initialized.")
        return self

    def __repr__(self) -> str:
        return (
            f"TaskRunner(max_steps={self.max_steps}, step_count={self.step_count}, "
            f"full_conversation_length={len(self.full_conversation)}, "
            f"termination_reason={self.termination_reason}, full_reward_info={self.full_reward_info})"
        )

    def should_not_stop(self, response: AgentExecutorResponse) -> bool:
        """Based on the response, check whether we should or not stop the conversation."""

        # Determine who sent this based on executor_id
        is_from_agent = response.executor_id == ASSISTANT_AGENT_ID
        is_from_user = response.executor_id == USER_SIMULATOR_ID

        self.step_count += 1

        logger.opt(colors=True).info(
            f"<bold>[Step {self.step_count}] Received the following response from "
            f"{'<blue>assistant</blue>' if is_from_agent else '<green>user</green>'}</bold>, "
            f"routing to {'<green>user</green>' if is_from_agent else '<blue>assistant</blue>'}:"
        )
        log_messages(response.agent_run_response.messages)

        if self.step_count >= self.max_steps:
            logger.info(f"Max steps ({self.max_steps}) reached - terminating conversation")
            self.termination_reason = TerminationReason.MAX_STEPS
            # Terminate the workflow
            return False

        response_text = response.agent_run_response.text
        if is_from_agent and self._is_agent_stop(response_text):
            logger.info("Agent requested stop - terminating conversation")
            self.termination_reason = TerminationReason.AGENT_STOP
            return False

        if is_from_user and self._is_user_stop(response_text):
            logger.info(f"User requested stop with message: '{response_text}' - terminating conversation")
            self.termination_reason = TerminationReason.USER_STOP
            # The final user message won't appear in the assistant's message store,
            # because it will never arrive there.
            # We need to store it because it's needed for evaluation.
            self._final_user_message = flip_messages(response.agent_run_response.messages)
            return False

        return True

    def _is_agent_stop(self, _: str) -> bool:
        """Check if agent wants to stop the conversation."""
        # Could check for specific stop tokens if agent uses them
        return False  # Agent doesn't have explicit stop in this setup

    def _is_user_stop(self, text: str) -> bool:
        """Check if user wants to stop the conversation."""
        return STOP in text or TRANSFER in text or OUT_OF_SCOPE in text

    def assistant_agent(self, assistant_chat_client: OpenAIChatClient) -> ChatAgent:
        """Create an assistant agent.

        Users can override this method to provide a custom assistant agent.

        Args:
            assistant_chat_client: The chat client for the assistant agent.

        Returns:
            The assistant agent.
        """

        # Initialize tau2 environment and extract tools/policy
        # This provides the domain-specific context (airline customer service in this case)
        env = get_environment()
        tools = env.get_tools()  # Available actions the assistant can take
        policy = env.get_policy()  # Guidelines the assistant must follow

        logger.info(
            f"Environment has {len(env.get_tools())} tools: {', '.join([tool.name for tool in env.get_tools()])}"
        )

        # Convert tau2 tools to agent framework AIFunction format
        # This bridges the gap between tau2's tool system and agent framework's expectations
        ai_functions = [convert_tau2_tool_to_ai_function(tool) for tool in tools]

        # Combines general customer service behavior with specific policy guidelines
        assistant_system_prompt = f"""<instructions>
{ASSISTANT_AGENT_INSTRUCTION}
</instructions>
<policy>
{policy}
</policy>"""

        # Assistant agent has:
        # - Access to all domain tools (booking, cancellation, etc.)
        # - Sliding window memory to handle long conversations within token limits
        # - Temperature-controlled response generation
        return ChatAgent(
            chat_client=assistant_chat_client,
            instructions=assistant_system_prompt,
            tools=ai_functions,  # type: ignore
            temperature=self.assistant_sampling_temperature,
            chat_message_store_factory=lambda: SlidingWindowChatMessageList(
                system_message=assistant_system_prompt,
                tool_definitions=[tool.openai_schema for tool in tools],
                max_tokens=self.assistant_window_size,
            ),
        )

    def user_simulator(self, user_simuator_chat_client: OpenAIChatClient, task: Task) -> ChatAgent:
        """Create a user simulator agent.

        Users can override this method to provide a custom user simulator agent.

        Args:
            user_simuator_chat_client: The chat client for the user simulator agent.
            task: The task to be executed.

        Returns:
            The user simulator agent.
        """

        # User simulator follows tau2's guidelines for realistic customer behavior
        # No tools available - users typically don't have direct system access
        user_sim_guidelines = get_global_user_sim_guidelines(use_tools=False)

        # User simulator prompt combines general guidelines with task-specific scenario
        user_sim_system_prompt = f"""{user_sim_guidelines}
<scenario>
{task.user_scenario.instructions}
</scenario>"""

        return ChatAgent(
            chat_client=user_simuator_chat_client,
            instructions=user_sim_system_prompt,
            temperature=0.0,
            # No sliding window for user simulator to maintain full conversation context
            # TODO(yuge): Consider adding user tools in future for more realistic scenarios
        )

    async def conversation_orchestrator(
        self, response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
    ) -> None:
        """Orchestrate conversation flow between assistant and user simulator.

        This is the central routing hub that:

        1. Receives responses from either the assistant agent or user simulator
        2. Flips message roles to create proper conversation flow (assistant->user, user->assistant)
        3. Routes the flipped messages to the appropriate target agent
        4. Maintains the conversation loop until termination conditions are met

        Args:
            response: The response from either assistant or user simulator agent
            ctx: Workflow context for sending messages to other executors
        """
        # Flip message roles for proper conversation flow
        # Assistant messages become user messages and vice versa
        flipped = flip_messages(response.agent_run_response.messages)

        # Determine source to route to correct target
        is_from_agent = response.executor_id == ASSISTANT_AGENT_ID

        # Send flipped messages to the opposite agent
        # Critical: Target ID must be specified to prevent broadcasting to both agents
        await ctx.send_message(
            AgentExecutorRequest(messages=flipped, should_respond=True),
            target_id=USER_SIMULATOR_ID if is_from_agent else ASSISTANT_AGENT_ID,
        )

    def build_conversation_workflow(self, assistant_agent: ChatAgent, user_simulator_agent: ChatAgent) -> Workflow:
        """Build the conversation workflow.

        Users can override this method to provide a custom conversation workflow.

        Args:
            assistant_agent: The assistant agent.
            user_simulator_agent: The user simulator agent.

        Returns:
            The conversation workflow.
        """

        # STEP 1: Create workflow executors
        # Each executor wraps an agent or function for workflow orchestration
        self._assistant_executor = AgentExecutor(assistant_agent, id=ASSISTANT_AGENT_ID)
        self._user_executor = AgentExecutor(user_simulator_agent, id=USER_SIMULATOR_ID)
        orchestrator = FunctionExecutor(func=self.conversation_orchestrator, id=ORCHESTRATOR_ID)

        # STEP 2: Build the conversation workflow
        # Creates a cyclic workflow: Orchestrator -> Assistant -> Orchestrator -> User -> Orchestrator...
        # The orchestrator acts as a message router that flips roles and routes to appropriate agent
        workflow = (
            WorkflowBuilder(max_iterations=10000)  # Unlimited - we control termination via should_not_stop
            .set_start_executor(orchestrator)  # Orchestrator manages the conversation flow
            .add_edge(orchestrator, self._assistant_executor)  # Route messages to assistant
            .add_edge(
                self._assistant_executor, orchestrator, condition=self.should_not_stop
            )  # Check termination after assistant
            .add_edge(orchestrator, self._user_executor)  # Route messages to user simulator
            .add_edge(self._user_executor, orchestrator, condition=self.should_not_stop)  # Check termination after user
            .build()
        )

        return workflow

    async def run(
        self,
        task: Task,
        assistant_chat_client: OpenAIChatClient,
        user_simuator_chat_client: OpenAIChatClient,
    ) -> list[ChatMessage]:
        """Run a tau2 task using workflow-based agent orchestration.

        This method orchestrates a complex multi-agent simulation:

        1. Sets up tau2 environment and converts tools for agent framework compatibility
        2. Creates two agents: assistant (with tools) and user simulator (without tools)
        3. Builds a workflow with orchestrated message routing between agents
        4. Manages conversation flow until termination conditions are met
        5. Returns complete conversation history for evaluation

        Args:
            task: Tau2 task containing scenario, policy, and evaluation criteria
            assistant_chat_client: LLM client for the assistant agent
            user_simuator_chat_client: LLM client for the user simulator

        Returns:
            Complete conversation history as ChatMessage list for evaluation
        """

        logger.info(f"Starting workflow agent for task {task.id}: {task.description.purpose}")  # type: ignore[unused-ignore]
        logger.info(f"Assistant chat client: {assistant_chat_client}")
        logger.info(f"User simulator chat client: {user_simuator_chat_client}")

        # STEP 1: Create agents
        assistant_agent = self.assistant_agent(assistant_chat_client)
        user_simulator_agent = self.user_simulator(user_simuator_chat_client, task)

        # STEP 2: Create the conversation workflow
        workflow = self.build_conversation_workflow(assistant_agent, user_simulator_agent)

        # STEP 3: Initialize conversation with standard greeting
        # Matches tau2's expected conversation start pattern
        logger.info(f"Starting workflow with hardcoded greeting: '{DEFAULT_FIRST_AGENT_MESSAGE}'")

        first_message = ChatMessage(Role.ASSISTANT, text=DEFAULT_FIRST_AGENT_MESSAGE)
        initial_greeting = AgentExecutorResponse(
            executor_id=ASSISTANT_AGENT_ID,
            agent_run_response=AgentRunResponse(messages=[first_message]),
            full_conversation=[ChatMessage(Role.ASSISTANT, text=DEFAULT_FIRST_AGENT_MESSAGE)],
        )

        # STEP 4: Execute the workflow and collect results
        # The workflow runs until termination conditions are met (max steps, stop signals, etc.)
        await workflow.run(initial_greeting)

        # STEP 5: Ensemble the conversation history needed for evaluation.
        # It's coming from three parts:
        # 1. The initial greeting
        # 2. The assistant's message store (not just the truncated window)
        # 3. The final user message (if any)
        assistant_executor = cast(AgentExecutor, self._assistant_executor)
        message_store = cast(SlidingWindowChatMessageList, assistant_executor._agent_thread.message_store)
        full_conversation = [first_message] + await message_store.list_all_messages()
        if self._final_user_message is not None:
            full_conversation.extend(self._final_user_message)

        logger.opt(colors=True).info(
            f"<green>WORKFLOW COMPLETED WITH {len(full_conversation)} MESSAGES. "
            f"Termination reason: {self.termination_reason}.</green>"
        )
        log_messages(full_conversation)

        return full_conversation

    def evaluate(
        self, task_input: Task, conversation: list[ChatMessage], termination_reason: TerminationReason | None
    ) -> float:
        """Evaluate agent performance using tau2's comprehensive evaluation system.

        Bridges agent framework conversation results with tau2's evaluation pipeline.
        Considers task completion, policy adherence, conversation quality, and tool usage.

        Args:
            task_input: Original tau2 task containing evaluation criteria
            conversation: Complete conversation history from workflow execution
            termination_reason: How/why the conversation ended (affects scoring)

        Returns:
            Numeric reward score (0.0-1.0) representing overall performance

        Side Effects:
            Stores detailed evaluation results in self.full_reward_info
        """

        # Handle missing termination reason (can happen with unexpected workflow endings)
        if termination_reason is None:
            termination_reason = TerminationReason.TOO_MANY_ERRORS

        # Convert agent framework ChatMessages to tau2 Message format for evaluation
        tau2_messages = convert_agent_framework_messages_to_tau2_messages(conversation)

        # Package conversation and metadata for tau2's evaluation system
        simulation = SimulationRun(
            id=str(uuid.uuid4()),  # Unique identifier for this evaluation run
            task_id=task_input.id,  # Links evaluation back to original task
            start_time=get_now(),  # Timestamp for evaluation records
            end_time=get_now(),  # Duration is 0 since this is post-hoc evaluation
            duration=0.0,
            termination_reason=termination_reason,  # Context for how conversation ended
            messages=tau2_messages,  # The actual conversation to evaluate
        )

        # Run comprehensive multi-dimensional evaluation
        # EvaluationType.ALL: evaluates task completion, policy adherence, conversation quality, ...
        # solo_mode=False: indicates multi-agent conversation (assistant + user simulator)
        self.full_reward_info = evaluate_simulation(
            simulation=simulation,
            task=task_input,
            evaluation_type=EvaluationType.ALL,
            solo_mode=False,
            domain="airline",
        )

        logger.info(f"Evaluation completed - Reward: {self.full_reward_info.reward}, Info: {self.full_reward_info}")
        return self.full_reward_info.reward  # type: ignore[no-any-return]
