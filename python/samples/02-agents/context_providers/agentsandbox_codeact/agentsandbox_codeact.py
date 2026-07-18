import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

from agent_framework import Agent, FunctionInvocationContext, function_middleware
from agent_framework.agentsandbox import AgentSandboxCodeActProvider
from agent_framework.ollama import OllamaChatClient
from dotenv import load_dotenv
from k8s_agent_sandbox.models import SandboxDirectConnectionConfig

"""
Prerequisites

1. A running Kubernetes cluster with the agent-sandbox controller installed
   (https://agent-sandbox.sigs.k8s.io/docs/getting_started/).
2. A ``SandboxWarmPool`` (and the ``SandboxTemplate`` it references) applied to
   the cluster. See this sample's ``../../../../packages/agentsandbox/TESTING.md``
   for ready-to-apply manifests; by default the sample claims from a warm pool
   named ``python-sandbox-pool`` in the ``default`` namespace.
3. The ``sandbox-router`` deployed in the cluster, reachable on localhost. The
   async client does not support ``kubectl port-forward`` tunnelling, so run a
   port-forward yourself in a separate terminal and point the sample at it:

       kubectl -n default port-forward svc/sandbox-router-svc 8080:8080

   then ``SandboxDirectConnectionConfig(api_url="http://localhost:8080")`` (the
   default below) routes through it.
4. Ollama installed and running locally (https://ollama.com/). Pull a model
   that supports function calling, for example:

       ollama pull qwen2.5

5. Optional environment variables:

       export OLLAMA_HOST=http://localhost:11434
       export OLLAMA_MODEL=qwen2.5
       export AGENT_SANDBOX_WARMPOOL=python-sandbox-pool
       export AGENT_SANDBOX_NAMESPACE=default
       export AGENT_SANDBOX_ROUTER_URL=http://localhost:8080
"""

load_dotenv()

_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"


class _ColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"{_DIM}{super().format(record)}{_RESET}"


logging.basicConfig(level=logging.WARNING)
logging.getLogger().handlers[0].setFormatter(
    _ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"),
)


@function_middleware
async def log_function_calls(
    context: FunctionInvocationContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    import time

    function_name = context.function.name
    arguments = context.arguments if isinstance(context.arguments, dict) else {}

    if function_name == "execute_code" and "code" in arguments:
        print(f"\n{_YELLOW}{'─' * 60}")
        print("▶ execute_code")
        print(f"{'─' * 60}{_RESET}")
        print(arguments["code"])
        print(f"{_YELLOW}{'─' * 60}{_RESET}")
    else:
        pairs = ", ".join(f"{name}={value!r}" for name, value in arguments.items())
        print(f"\n{_YELLOW}▶ {function_name}({pairs}){_RESET}")

    start = time.perf_counter()
    await call_next()
    elapsed = time.perf_counter() - start

    result = context.result
    if function_name == "execute_code" and isinstance(result, list):
        for output in result:
            if output.type == "text" and output.text:
                print(f"{_GREEN}stdout:\n{output.text}{_RESET}")
            elif output.type == "error" and output.error_details:
                print(f"{_YELLOW}stderr:\n{output.error_details}{_RESET}")
    else:
        print(f"{_YELLOW}◀ {function_name} → {result!r}{_RESET}")

    print(f"{_DIM}  ({elapsed:.4f}s){_RESET}")


async def main() -> None:
    warmpool = os.environ.get("AGENT_SANDBOX_WARMPOOL", "python-sandbox-pool")
    namespace = os.environ.get("AGENT_SANDBOX_NAMESPACE", "default")
    router_url = os.environ.get("AGENT_SANDBOX_ROUTER_URL", "http://localhost:8080")

    async with AgentSandboxCodeActProvider(
        warmpool=warmpool,
        namespace=namespace,
        # The async client reaches the Pod through the sandbox-router. Point it
        # at a local `kubectl port-forward svc/sandbox-router-svc 8080:8080`.
        connection_config=SandboxDirectConnectionConfig(api_url=router_url),
        shutdown_after_seconds=30 * 60,
    ) as codeact:
        agent = Agent(
            client=OllamaChatClient(),
            name="AgentSandboxCodeActAgent",
            instructions=(
                "You are a careful Python assistant. When a user asks for a "
                "computation or data manipulation, write a small Python "
                "snippet and run it with `execute_code` to get an exact "
                "answer, then explain the result briefly. Use only the Python "
                "standard library — third-party packages are not installed in "
                "the sandbox unless you `pip install` them yourself."
            ),
            context_providers=[codeact],
            middleware=[log_function_calls],
        )

        session = agent.create_session()

        prompts = [
            (
                "Compute the 30th Fibonacci number using only the standard "
                "library. Save just the number to /app/fib.txt and print it."
            ),
            (
                "Read the number back from /app/fib.txt, compute its prime "
                "factorization using only the standard library, save the "
                "factors to /app/factors.txt, then print the number and its "
                "factors. (The file is still there because the sandbox Pod "
                "persists across calls.)"
            ),
        ]
        print(f"{_CYAN}{'=' * 60}")
        print("agent-sandbox CodeAct provider sample")
        print(f"{'=' * 60}{_RESET}")
        for prompt in prompts:
            print(f"\n{_CYAN}User: {prompt}{_RESET}")
            result = await agent.run(prompt, session=session)
            print(f"{_CYAN}Agent: {result.text}{_RESET}")


if __name__ == "__main__":
    asyncio.run(main())
