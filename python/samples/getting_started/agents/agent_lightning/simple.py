# type: ignore

import asyncio
import uuid
from openai import OpenAI

from tau2.domains.airline.environment import get_environment, get_tasks
from tau2.data_model.tasks import Task
from tau2.data_model.simulation import SimulationRun, TerminationReason
from tau2.evaluator.evaluator import evaluate_simulation, EvaluationType
from tau2.utils.utils import get_now

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

from _tau2_helper import convert_agent_framework_messages_to_tau2_messages, convert_tau2_tool_to_ai_function

# Use pure OpenAI message format with error handling
TaskOutput = dict  # {"messages": list[dict], "errors": any}


class LengthenedOpenAIChatClient(OpenAIChatClient):
    def __init__(self, maximum_iterations_per_request: int = 10, **kwargs):
        super().__init__(**kwargs)
        setattr(self, "__maximum_iterations_per_request", maximum_iterations_per_request)


AGENT_INSTRUCTION = """
You are a customer service agent that helps the user according to the <policy> provided below.
In each turn you can either:
- Send a message to the user.
- Make a tool call.
You cannot do both at the same time.

Try to be helpful and always follow the policy. Always make sure you generate valid JSON only.
""".strip()


def criteria(task_input: Task, task_output: TaskOutput) -> float:
    """Evaluate the agent's performance using the existing evaluation system."""
    # Convert Agent framework messages to tau2 Message objects

    messages = task_output["messages"]
    errors = task_output.get("errors", None)

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)
    print(tau2_messages)

    # Determine termination reason based on errors or message content
    termination_reason = TerminationReason.AGENT_STOP
    if errors:
        termination_reason = TerminationReason.TOO_MANY_ERRORS

    # Create a mock SimulationRun for evaluation
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
    reward_info = evaluate_simulation(
        simulation=simulation, task=task_input, evaluation_type=EvaluationType.ALL, solo_mode=False, domain="airline"
    )

    print("Evaluation info:", reward_info)

    return reward_info.reward


async def agent(task_input: Task, openai: OpenAI, model: str, max_turns: int = 20) -> TaskOutput:
    """Minimal OpenAI SDK-based agent implementation."""
    # Get environment and tools
    env = get_environment()
    tools = env.get_tools()
    policy = env.get_policy()

    # Create system prompt
    system_prompt = f"""<instructions>
{AGENT_INSTRUCTION}
</instructions>
<policy>
{policy}
</policy>"""

    print("System prompt:", system_prompt)

    # Convert tau2 tools to AIFunction format
    ai_functions = [convert_tau2_tool_to_ai_function(tool) for tool in tools]

    # Initialize conversation with pure OpenAI format
    messages = [{"role": "system", "content": system_prompt}]

    chat_client = LengthenedOpenAIChatClient(ai_model_id=model, maximum_iterations_per_request=max_turns)

    chat_agent = ChatAgent(
        chat_client=chat_client,
        instructions=system_prompt,
        tools=ai_functions,
    )

    user_msg = f"Hello, {task_input.user_scenario.instructions.reason_for_call}"

    try:
        result = await chat_agent.run(user_msg)
        print(result)
        return {"messages": result.messages, "errors": None}
    except Exception as e:
        return {"messages": messages, "errors": str(e)}


async def main():
    import agentops
    agentops.init()
    # Test the implementation without OpenAI API calls
    env = get_environment()
    tasks = get_tasks()

    print(f"Found {len(tasks)} tasks")
    print(f"Environment has {len(env.get_tools())} tools")
    print("\nFirst task:")
    print(f"ID: {tasks[0].id}")
    print(f"Purpose: {tasks[0].description.purpose}")

    if tasks[0].user_scenario and tasks[0].user_scenario.instructions:
        print(f"User scenario: {tasks[0].user_scenario.instructions.reason_for_call}")

    print(f"Evaluation criteria actions: {len(tasks[0].evaluation_criteria.actions or [])}")

    # Uncomment to test with actual OpenAI API
    openai = OpenAI()
    for task in tasks[:3]:  # Test with first task only
        print(f"\nTesting task {task.id}")
        result = await agent(task, openai, "gpt-4.1-mini")
        print(f"Agent result:", result)
        reward = criteria(task, result)
        print(f"Reward: {reward}")


if __name__ == "__main__":
    asyncio.run(main())
