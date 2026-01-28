# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import FunctionCallContent, FunctionResultContent, tool
from agent_framework.openai import OpenAIResponsesClient

"""
Some tools are very expensive to run, so you may want to limit the number of times
it tries to call them and fails. This sample shows a tool that can only raise exceptions a
limited number of times.
"""


# we trick the AI into calling this function with 0 as denominator to trigger the exception
@tool(max_invocation_exceptions=1)
def safe_divide(
    a: Annotated[int, "Numerator"],
    b: Annotated[int, "Denominator"],
) -> str:
    """Divide two numbers can be used with 0 as denominator."""
    try:
        result = a / b  # Will raise ZeroDivisionError
    except ZeroDivisionError as exc:
        print(f"    Tool failed with error: {exc}")
        raise

    return f"{a} / {b} = {result}"


async def main():
    # tools = Tools()
    agent = OpenAIResponsesClient().as_agent(
        name="ToolAgent",
        instructions="Use the provided tools.",
        tools=[safe_divide],
    )
    thread = agent.get_new_thread()
    print("=" * 60)
    print("Step 1: Call divide(10, 0) - tool raises exception")
    response = await agent.run("Divide 10 by 0", thread=thread)
    print(f"Response: {response.text}")
    print("=" * 60)
    print("Step 2: Call divide(100, 0) - will refuse to execute due to max_invocation_exceptions")
    response = await agent.run("Divide 100 by 0", thread=thread)
    print(f"Response: {response.text}")
    print("=" * 60)
    print(f"Number of tool calls attempted: {safe_divide.invocation_count}")
    print(f"Number of tool calls failed: {safe_divide.invocation_exception_count}")
    print("Replay the conversation:")
    assert thread.message_store
    assert thread.message_store.list_messages
    for idx, msg in enumerate(await thread.message_store.list_messages()):
        if msg.text:
            print(f"{idx + 1}  {msg.author_name or msg.role}: {msg.text} ")
        for content in msg.contents:
            if isinstance(content, FunctionCallContent):
                print(
                    f"{idx + 1}  {msg.author_name}: calling function: {content.name} with arguments: {content.arguments}"
                )
            if isinstance(content, FunctionResultContent):
                print(f"{idx + 1}  {msg.role}: {content.result if content.result else content.exception}")


"""
Expected Output:
============================================================
Step 1: Call divide(10, 0) - tool raises exception
    Tool failed with error: division by zero
[2025-10-31 15:39:53 - /Users/edvan/Work/agent-framework/python/packages/core/agent_framework/_tools.py:718 - ERROR]
Function failed. Error: division by zero
Response: Division by zero is undefined in standard arithmetic. There is no finite value for 10 ÷ 0.

If you want alternatives:
- A valid example: 10 ÷ 2 = 5.
- To handle safely in code, you can check the denominator first (e.g., in Python: if b == 0:
    handle error else: compute a/b).
- If you’re curious about limits: as x → 0+, 10/x → +∞; as x → 0−, 10/x → −∞; there is no finite limit.

Would you like me to show a safe division snippet in a specific language, or compute something else?
============================================================
Step 2: Call divide(100, 0) - will refuse to execute due to max_invocations
[2025-10-31 15:40:09 - /Users/edvan/Work/agent-framework/python/packages/core/agent_framework/_tools.py:718 - ERROR]
Function failed. Error: Function 'safe_divide' has reached its maximum exception limit, you tried to use this
tool too many times and it kept failing.
Response: Division by zero is undefined in standard arithmetic, so 100 ÷ 0 has no finite value.

If you’re coding and want safe handling, here are quick patterns in a few languages:

- Python
  def safe_divide(a, b):
      if b == 0:
          return None  # or raise an exception
      return a / b

  safe_divide(100, 0)  # -> None

- JavaScript
  function safeDivide(a, b) {
      if (b === 0) return undefined; // or throw
      return a / b;
  }

  safeDivide(100, 0)  // -> undefined

- Java
  public static Double safeDivide(double a, double b) {
      if (b == 0.0) throw new ArithmeticException("Divide by zero");
      return a / b;
  }

  safeDivide(100, 0)  // -> exception

- C/C++
  double safeDivide(double a, double b) {
      if (b == 0.0) return std::numeric_limits<double>::infinity(); // or handle error
      return a / b;
  }

Note: In many languages, dividing by zero with floating-point numbers yields Infinity (or -Infinity) or NaN,
but integer division typically raises an error.

Would you like a snippet in a specific language or to see a math explanation (limits) for what happens as the
divisor approaches zero?
============================================================
Number of tool calls attempted: 1
Number of tool calls failed: 1
Replay the conversation:
1  user: Divide 10 by 0
2  ToolAgent: calling function: safe_divide with arguments: {"a":10,"b":0}
3  tool: division by zero
4  ToolAgent: Division by zero is undefined in standard arithmetic. There is no finite value for 10 ÷ 0.

If you want alternatives:
- A valid example: 10 ÷ 2 = 5.
- To handle safely in code, you can check the denominator first (e.g., in Python: if b == 0:
    handle error else: compute a/b).
- If you’re curious about limits: as x → 0+, 10/x → +∞; as x → 0−, 10/x → −∞; there is no finite limit.

Would you like me to show a safe division snippet in a specific language, or compute something else?
5  user: Divide 100 by 0
6  ToolAgent: calling function: safe_divide with arguments: {"a":100,"b":0}
7  tool: Function 'safe_divide' has reached its maximum exception limit, you tried to use this tool too many times
    and it kept failing.
8  ToolAgent: Division by zero is undefined in standard arithmetic, so 100 ÷ 0 has no finite value.

If you’re coding and want safe handling, here are quick patterns in a few languages:

- Python
  def safe_divide(a, b):
      if b == 0:
          return None  # or raise an exception
      return a / b

  safe_divide(100, 0)  # -> None

- JavaScript
  function safeDivide(a, b) {
      if (b === 0) return undefined; // or throw
      return a / b;
  }

  safeDivide(100, 0)  // -> undefined

- Java
  public static Double safeDivide(double a, double b) {
      if (b == 0.0) throw new ArithmeticException("Divide by zero");
      return a / b;
  }

  safeDivide(100, 0)  // -> exception

- C/C++
  double safeDivide(double a, double b) {
      if (b == 0.0) return std::numeric_limits<double>::infinity(); // or handle error
      return a / b;
  }

Note: In many languages, dividing by zero with floating-point numbers yields Infinity (or -Infinity) or NaN,
but integer division typically raises an error.

Would you like a snippet in a specific language or to see a math explanation (limits) for what happens as the
divisor approaches zero?
"""

if __name__ == "__main__":
    asyncio.run(main())
