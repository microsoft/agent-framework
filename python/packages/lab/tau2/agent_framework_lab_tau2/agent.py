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
    WorkflowBuilder,
    WorkflowContext,
)
from agent_framework.openai import OpenAIChatClient
from loguru import logger
from tau2.data_model.simulation import SimulationRun, TerminationReason
from tau2.data_model.tasks import Task
from tau2.domains.airline.environment import get_environment
from tau2.evaluator.evaluator import EvaluationType, RewardInfo, evaluate_simulation
from tau2.user.user_simulator import OUT_OF_SCOPE, STOP, TRANSFER, get_global_user_sim_guidelines
from tau2.utils.utils import get_now

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
    """Running tasks defined in tau-2."""

    # State
    step_count: int
    full_conversation: list[ChatMessage]
    termination_reason: TerminationReason | None
    full_reward_info: RewardInfo | None

    # Configurations
    max_steps: int

    def __init__(self, max_steps: int):
        self.max_steps = max_steps

        self.reinit()

    def reinit(self):
        self.step_count = 0
        self.full_conversation = []
        self.termination_reason = None
        self.full_reward_info = None
        logger.info("ConversationOrchestrator has been re-initialized.")
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
            return False

        return True

    def _is_agent_stop(self, _: str) -> bool:
        """Check if agent wants to stop the conversation."""
        # Could check for specific stop tokens if agent uses them
        return False  # Agent doesn't have explicit stop in this setup

    def _is_user_stop(self, text: str) -> bool:
        """Check if user wants to stop the conversation."""
        return STOP in text or TRANSFER in text or OUT_OF_SCOPE in text

    async def conversation_orchestrator(
        self, response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
    ):
        """Flip the roles of messages and routes properly."""
        flipped = flip_messages(response.agent_run_response.messages)
        is_from_agent = response.executor_id == ASSISTANT_AGENT_ID
        await ctx.send_message(
            AgentExecutorRequest(messages=flipped, should_respond=True),
            # Target ID must be specified here because orchestrator is connected to both sides;
            # otherwise, it will be broadcasted (wrong).
            target_id=USER_SIMULATOR_ID if is_from_agent else ASSISTANT_AGENT_ID,
        )

    async def run(
        self,
        task: Task,
        assistant_chat_client: OpenAIChatClient,
        user_simuator_chat_client: OpenAIChatClient,
        assistant_sampling_temperature: float = 0.0,
        assistant_window_size: int = 32768,
    ) -> list[ChatMessage]:
        """Complex workflow-based agent implementation."""

        logger.info(f"Starting workflow agent for task {task.id}: {task.description.purpose}")  # type: ignore
        logger.info(f"Assistant chat client: {assistant_chat_client}")
        logger.info(f"User simulator chat client: {user_simuator_chat_client}")

        # Get environment and tools
        env = get_environment()
        tools = env.get_tools()
        policy = env.get_policy()

        logger.info(
            f"Environment has {len(env.get_tools())} tools: {', '.join([tool.name for tool in env.get_tools()])}"
        )

        # Convert tau2 tools to AIFunction format
        ai_functions = [convert_tau2_tool_to_ai_function(tool) for tool in tools]

        # 1. Create assistant agent with proper system prompt
        assistant_system_prompt = f"""<instructions>
{ASSISTANT_AGENT_INSTRUCTION}
</instructions>
<policy>
{policy}
</policy>"""

        assistant = ChatAgent(
            chat_client=assistant_chat_client,
            instructions=assistant_system_prompt,
            tools=ai_functions,  # type: ignore
            temperature=assistant_sampling_temperature,
            chat_message_store_factory=lambda: SlidingWindowChatMessageList(
                system_message=assistant_system_prompt,
                tool_definitions=[tool.openai_schema for tool in tools],
                max_tokens=assistant_window_size,
            ),
        )

        # 2. Create user simulator as another ChatAgent
        # Get user simulator guidelines (without tools for now as requested)
        user_sim_guidelines = get_global_user_sim_guidelines(use_tools=False)

        user_sim_system_prompt = f"""{user_sim_guidelines}
<scenario>
{task.user_scenario.instructions}
</scenario>"""

        user_simulator = ChatAgent(
            chat_client=user_simuator_chat_client,
            instructions=user_sim_system_prompt,
            temperature=0.0,
            # No sliding window for user simulator to keep full context
            # TODO(yuge): support user tools in future
        )

        # 3. Create standard AgentExecutors
        assistant_executor = AgentExecutor(assistant, id=ASSISTANT_AGENT_ID)
        user_executor = AgentExecutor(user_simulator, id=USER_SIMULATOR_ID)
        orchestrator = FunctionExecutor(func=self.conversation_orchestrator, id=ORCHESTRATOR_ID)

        # 4. Build workflow
        workflow = (
            WorkflowBuilder(max_iterations=10000)  # Set to unlimited, because we are not relying on this
            .set_start_executor(orchestrator)  # Start with orchestrator
            .add_edge(orchestrator, assistant_executor)  # Orchestrator -> Assistant
            .add_edge(assistant_executor, orchestrator, condition=self.should_not_stop)  # Assistant -> Orchestrator
            .add_edge(orchestrator, user_executor)  # Orchestrator -> User
            .add_edge(user_executor, orchestrator, condition=self.should_not_stop)  # User -> Orchestrator
            .build()
        )

        # 5. Start workflow with hardcoded greeting
        logger.info(f"Starting workflow with hardcoded greeting: '{DEFAULT_FIRST_AGENT_MESSAGE}'")

        first_message = ChatMessage(Role.ASSISTANT, text=DEFAULT_FIRST_AGENT_MESSAGE)
        initial_greeting = AgentExecutorResponse(
            executor_id=ASSISTANT_AGENT_ID,
            agent_run_response=AgentRunResponse(messages=[first_message]),
            full_conversation=[ChatMessage(Role.ASSISTANT, text=DEFAULT_FIRST_AGENT_MESSAGE)],
        )

        # 6. Run the workflow and gather the results
        await workflow.run(initial_greeting)

        message_store = cast(SlidingWindowChatMessageList, assistant_executor._agent_thread.message_store)
        full_conversation = [first_message] + await message_store.list_all_messages()
        logger.opt(colors=True).info(
            f"<green>WORKFLOW COMPLETED WITH {len(full_conversation)} MESSAGES. "
            f"Termination reason: {self.termination_reason}.</green>"
        )
        log_messages(full_conversation)

        return full_conversation

    def evaluate(
        self, task_input: Task, conversation: list[ChatMessage], termination_reason: TerminationReason | None
    ) -> float:
        """Evaluate the agent's performance using the existing evaluation system."""

        if termination_reason is None:
            # Set to "too many errors" if there is no explicit termination cause
            termination_reason = TerminationReason.TOO_MANY_ERRORS

        # Convert Agent framework messages to tau2 Message objects
        tau2_messages = convert_agent_framework_messages_to_tau2_messages(conversation)

        # Create a SimulationRun for evaluation
        simulation = SimulationRun(
            id=str(uuid.uuid4()),
            task_id=task_input.id,
            start_time=get_now(),
            end_time=get_now(),
            duration=0.0,
            termination_reason=termination_reason,
            messages=tau2_messages,
        )

        # Use the existing evaluation system
        self.full_reward_info = evaluate_simulation(
            simulation=simulation,
            task=task_input,
            evaluation_type=EvaluationType.ALL,
            solo_mode=False,
            domain="airline",
        )

        logger.info(f"Evaluation completed - Reward: {self.full_reward_info.reward}, Info: {self.full_reward_info}")
        return self.full_reward_info.reward
