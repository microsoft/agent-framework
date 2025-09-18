# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import uuid
from typing import TypedDict

import tau2.evaluator.evaluator_nl_assertions as evaluator_nl_assertions
from agent_framework._agents import ChatAgent
from agent_framework._types import AgentRunResponse, ChatMessage, Role
from agent_framework._workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from agent_framework.openai import OpenAIChatClient
from loguru import logger
from pydantic import Field
from tau2.data_model.simulation import SimulationRun, TerminationReason
from tau2.data_model.tasks import Task
from tau2.domains.airline.environment import get_environment, get_tasks
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


class ConversationOrchestrator(Executor):
    """Orchestrates conversation between agent and user simulator, handling termination logic."""

    task: Task
    step_count: int = 0
    max_steps: int = 100
    trajectory: list[ChatMessage] = Field(default_factory=list)
    done: bool = False
    termination_reason: TerminationReason | None = None

    @handler
    async def handle_response(self, response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]):
        """Process any response and route appropriately."""
        self.step_count += 1

        # Determine who sent this based on executor_id
        is_from_agent = response.executor_id == "assistant_agent"
        is_from_user = response.executor_id == "user_simulator"

        logger.opt(colors=True).info(
            f"<bold>[Step {self.step_count}] Received the following response from "
            f"{'<blue>assistant</blue>' if is_from_agent else '<green>user</green>'}</bold>, "
            f"routing to {'<green>user</green>' if is_from_agent else '<blue>assistant</blue>'}:"
        )
        log_messages(response.agent_run_response.messages)

        # Check stop conditions based on sender
        response_text = response.agent_run_response.text

        if is_from_agent:
            self.trajectory.extend(response.agent_run_response.messages)

            # Check for agent stop conditions
            if self._is_agent_stop(response_text):
                logger.info("Agent requested stop - terminating conversation")
                self.done = True
                self.termination_reason = TerminationReason.AGENT_STOP
                await ctx.add_event(
                    WorkflowCompletedEvent(
                        {"messages": self.trajectory, "termination_reason": self.termination_reason, "errors": None}
                    )
                )
                return

            # Otherwise, route to user simulator
            user_messages = flip_messages(response.agent_run_response.messages)
            logger.info("Orchestrator has flipped the roles and will route the agent response to user simulator")
            await ctx.send_message(
                AgentExecutorRequest(messages=user_messages, should_respond=True),
                target_id="user_simulator",
            )

        elif is_from_user:
            # Convert user simulator's assistant messages to user messages for the agent
            agent_messages = flip_messages(response.agent_run_response.messages)
            self.trajectory.extend(agent_messages)

            # Check for user stop conditions
            if self._is_user_stop(response_text):
                logger.info(f"User requested stop with message: '{response_text}' - terminating conversation")
                self.done = True
                self.termination_reason = TerminationReason.USER_STOP
                await ctx.add_event(
                    WorkflowCompletedEvent(
                        {"messages": self.trajectory, "termination_reason": self.termination_reason, "errors": None}
                    )
                )
                return

            logger.info("Orchestrator has flipped the roles and will route the user response to the assistant.")

            # Route to agent
            await ctx.send_message(
                AgentExecutorRequest(messages=agent_messages, should_respond=True), target_id="assistant_agent"
            )

        # Check max steps
        if self.step_count >= self.max_steps:
            logger.info(f"Max steps ({self.max_steps}) reached - terminating conversation")
            self.done = True
            self.termination_reason = TerminationReason.MAX_STEPS
            await ctx.add_event(
                WorkflowCompletedEvent(
                    {"messages": self.trajectory, "termination_reason": self.termination_reason, "errors": None}
                )
            )
            return

    def _is_agent_stop(self, _: str) -> bool:
        """Check if agent wants to stop the conversation."""
        # Could check for specific stop tokens if agent uses them
        return False  # Agent doesn't have explicit stop in this setup

    def _is_user_stop(self, text: str) -> bool:
        """Check if user wants to stop the conversation."""
        return STOP in text or TRANSFER in text or OUT_OF_SCOPE in text


class AgentConfiguration(TypedDict):
    model: str
    temperature: float
    base_url: str
    api_key: str
    sliding_window: int


async def loop(
    task: Task,
    assistant_config: AgentConfiguration,
    user_config: AgentConfiguration,
    judge_config: AgentConfiguration,
    max_steps: int = 100,
) -> dict:
    """Complex workflow-based agent implementation."""

    logger.info(f"Starting workflow agent for task {task.id}: {task.description.purpose}")  # type: ignore
    logger.info(f"Assistant config: {assistant_config}")
    logger.info(f"User config: {user_config}")
    logger.info(f"Judge config: {judge_config}")

    # Get environment and tools
    env = get_environment()
    tools = env.get_tools()
    policy = env.get_policy()

    # Set the model needed by judge
    evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS = judge_config["model"]
    evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {
        "temperature": judge_config["temperature"],
        # base url and api key not supported here
    }

    # Convert tau2 tools to AIFunction format
    ai_functions = [convert_tau2_tool_to_ai_function(tool) for tool in tools]

    # 1. Create assistant agent with proper system prompt
    assistant_system_prompt = f"""<instructions>
{ASSISTANT_AGENT_INSTRUCTION}
</instructions>
<policy>
{policy}
</policy>"""

    assistant_chat_client = OpenAIChatClient(
        ai_model_id=assistant_config["model"],
        base_url=assistant_config["base_url"],
        api_key=assistant_config["api_key"],
    )
    assistant = ChatAgent(
        chat_client=assistant_chat_client,
        instructions=assistant_system_prompt,
        tools=ai_functions,  # type: ignore
        temperature=assistant_config["temperature"],
        chat_message_store_factory=lambda: SlidingWindowChatMessageList(
            system_message=assistant_system_prompt,
            tool_definitions=[tool.openai_schema for tool in tools],
            max_tokens=assistant_config["sliding_window"],
        ),
    )

    # 2. Create user simulator as another ChatAgent
    # Get user simulator guidelines (without tools for now as requested)
    user_sim_guidelines = get_global_user_sim_guidelines(use_tools=False)

    user_sim_system_prompt = f"""{user_sim_guidelines}
<scenario>
{task.user_scenario.instructions}
</scenario>"""

    user_chat_client = OpenAIChatClient(
        ai_model_id=user_config["model"],
        base_url=user_config["base_url"],
        api_key=user_config["api_key"],
    )
    user_simulator = ChatAgent(
        chat_client=user_chat_client,
        instructions=user_sim_system_prompt,
        temperature=user_config["temperature"],
        # No tools for user simulator as requested
        chat_message_store_factory=(
            (
                lambda: SlidingWindowChatMessageList(
                    system_message=user_sim_system_prompt,
                    tool_definitions=[],  # No tools for user simulator
                    max_tokens=user_config["sliding_window"],
                )
            )
            if user_config["sliding_window"] > 0
            else None
        ),
    )

    # 3. Create standard AgentExecutors
    assistant_executor = AgentExecutor(assistant, id="assistant_agent")
    user_executor = AgentExecutor(user_simulator, id="user_simulator")
    orchestrator = ConversationOrchestrator(id="orchestrator", task=task, max_steps=max_steps)

    # 4. Build workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)  # Start with orchestrator
        .add_edge(orchestrator, assistant_executor)  # Orchestrator -> Assistant
        .add_edge(assistant_executor, orchestrator)  # Assistant -> Orchestrator
        .add_edge(orchestrator, user_executor)  # Orchestrator -> User
        .add_edge(user_executor, orchestrator)  # User -> Orchestrator
        .build()
    )

    # 5. Start workflow with hardcoded greeting
    logger.info(f"Starting workflow with hardcoded greeting: '{DEFAULT_FIRST_AGENT_MESSAGE}'")

    # Create initial greeting response to kick off the conversation
    initial_greeting = AgentExecutorResponse(
        executor_id="assistant_agent",
        agent_run_response=AgentRunResponse(messages=[ChatMessage(Role.ASSISTANT, text=DEFAULT_FIRST_AGENT_MESSAGE)]),
        full_conversation=[ChatMessage(Role.ASSISTANT, text=DEFAULT_FIRST_AGENT_MESSAGE)],
    )

    try:
        events = await workflow.run(initial_greeting)
    except RuntimeError as e:
        if "did not converge" in str(e):
            logger.error(f"Workflow failed to converge: {e}")
            # Return a result indicating convergence failure
            return {
                "messages": orchestrator.trajectory,
                "errors": str(e),
                "termination_reason": TerminationReason.MAX_STEPS,
            }
        else:
            # Re-raise if it's a different RuntimeError
            raise

    # 6. Extract completed event
    completed_event = events.get_completed_event()

    logger.opt(colors=True).info(f"<green>WORKFLOW COMPLETED WITH {len(orchestrator.trajectory)} MESSAGES:</green>")
    log_messages(orchestrator.trajectory)

    if completed_event and completed_event.data:
        result = {
            "messages": completed_event.data.get("messages", []),
            "errors": completed_event.data.get("errors"),
            "termination_reason": completed_event.data.get("termination_reason"),
        }
    else:
        result = {
            "messages": orchestrator.trajectory,
            "errors": None,
            "termination_reason": orchestrator.termination_reason,
        }

    logger.info(f"FINAL RESULT: {len(result['messages'])} messages, termination: {result['termination_reason']}")
    return result


def criteria(task_input: Task, task_output: dict, return_reward_info: bool = False) -> float | RewardInfo:
    """Evaluate the agent's performance using the existing evaluation system."""

    messages = task_output["messages"]
    termination_reason = task_output.get("termination_reason", TerminationReason.TOO_MANY_ERRORS)

    # Convert Agent framework messages to tau2 Message objects
    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    # Create a SimulationRun for evaluation
    simulation = SimulationRun(
        id=str(uuid.uuid4()),
        task_id=task_input.id,
        start_time=get_now(),
        end_time=get_now(),
        duration=0.0,
        termination_reason=termination_reason,
        messages=tau2_messages,  # type: ignore
    )

    # Use the existing evaluation system
    reward_info = evaluate_simulation(
        simulation=simulation, task=task_input, evaluation_type=EvaluationType.ALL, solo_mode=False, domain="airline"
    )

    logger.info(f"Evaluation completed - Reward: {reward_info.reward}, Info: {reward_info}")

    if return_reward_info:
        return reward_info
    else:
        return reward_info.reward


async def main():
    # Test the environment
    env = get_environment()
    tasks = get_tasks()

    logger.info(f"Found {len(tasks)} tasks in the dataset")
    logger.info(f"Environment has {len(env.get_tools())} tools: {', '.join([tool.name for tool in env.get_tools()])}")

    _logger = logger.opt(colors=True)

    proxy_base_url = os.getenv("PROXY_OPENAI_BASE_URL")
    proxy_api_key = os.getenv("PROXY_OPENAI_API_KEY")
    if proxy_base_url is None:
        raise ValueError("PROXY_OPENAI_BASE_URL must be set")
    if proxy_api_key is None:
        raise ValueError("PROXY_OPENAI_API_KEY must be set")

    assistant_config = AgentConfiguration(
        model="gpt-4.1",
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=4000,
    )
    user_config = AgentConfiguration(
        model="gpt-4o-mini",
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=30000,  # long sliding window for user simulator
    )
    judge_config = AgentConfiguration(
        model="gpt-4o-mini",
        temperature=0.0,
        base_url=proxy_base_url,
        api_key=proxy_api_key,
        sliding_window=0,  # Not used for judge
    )

    # Iterate over the tasks
    for task in tasks:
        _logger.info(f"<red>Testing task #{task.id}</red>")
        _logger.info(f"<cyan>Purpose:</cyan> {task.description.purpose}")  # type: ignore

        if task.user_scenario and task.user_scenario.instructions:
            _logger.info(f"<cyan>User scenario:</cyan> {task.user_scenario.instructions.reason_for_call}")  # type: ignore

        result = await loop(task, assistant_config, user_config, judge_config, max_steps=100)
        _logger.info(f"<cyan>Agent result - Termination:</cyan> {result.get('termination_reason')}")
        _logger.info(f"<cyan>Number of messages:</cyan> {len(result['messages'])}")

        reward = criteria(task, result)
        _logger.info(f"<cyan>Final reward:</cyan> {reward}")


if __name__ == "__main__":
    asyncio.run(main())
