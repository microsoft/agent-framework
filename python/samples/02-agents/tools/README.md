# Tools

Samples that show how to define, configure, and control function tools for an
agent — from basic declarations to approvals, invocation limits, session
injection, and dynamic (progressive) tool exposure.

## Function tools

| File | Demonstrates |
|------|--------------|
| [`function_tool_with_explicit_schema.py`](function_tool_with_explicit_schema.py) | Defining a tool with an explicit JSON schema. |
| [`function_tool_declaration_only.py`](function_tool_declaration_only.py) | A declaration-only tool (schema without a local implementation). |
| [`function_tool_with_kwargs.py`](function_tool_with_kwargs.py) | Passing extra keyword arguments into a tool. |
| [`function_tool_from_dict_with_dependency_injection.py`](function_tool_from_dict_with_dependency_injection.py) | Dependency injection into a tool defined from a dict. |
| [`function_tool_with_session_injection.py`](function_tool_with_session_injection.py) | Injecting the session into a tool. |
| [`tool_in_class.py`](tool_in_class.py) | Using a method on a class as a tool. |
| [`agent_as_tool_with_session_propagation.py`](agent_as_tool_with_session_propagation.py) | Exposing an agent as a tool with session propagation. |

## Approvals & invocation control

| File | Demonstrates |
|------|--------------|
| [`function_tool_with_approval.py`](function_tool_with_approval.py) | Requiring human approval before a tool runs. |
| [`function_tool_with_approval_and_sessions.py`](function_tool_with_approval_and_sessions.py) | Tool approvals combined with sessions. |
| [`tool_approval_middleware.py`](tool_approval_middleware.py) | Session-backed approval coordination, mixed-batch approvals, and "always approve" rules. |
| [`function_invocation_configuration.py`](function_invocation_configuration.py) | Configuring function-invocation settings (e.g. max iterations). |
| [`control_total_tool_executions.py`](control_total_tool_executions.py) | All the ways to cap how many times tools run. |
| [`function_tool_with_max_invocations.py`](function_tool_with_max_invocations.py) | Limiting the number of invocations per tool. |
| [`function_tool_with_max_exceptions.py`](function_tool_with_max_exceptions.py) | Limiting the number of exceptions a tool may raise. |
| [`function_tool_recover_from_failures.py`](function_tool_recover_from_failures.py) | Returning errors so the agent can recover from tool failures. |

## Progressive tool exposure (dynamic loading)

| File | Demonstrates |
|------|--------------|
| [`dynamic_tool_exposure.py`](dynamic_tool_exposure.py) | A "loader" tool that adds more tools at runtime via `FunctionInvocationContext`. |

Frontloading a model with hundreds of tools hurts tool-selection accuracy,
bloats context, and raises cost. Instead, start with a small set of loader
tools and let the model pull in more on demand. Inside a tool, the injected
`ctx: FunctionInvocationContext` exposes a live `ctx.tools` list plus
`ctx.add_tools(...)` / `ctx.remove_tools(...)` helpers. Tools added or removed
take effect on the **next iteration** of the function-calling loop.

> [!NOTE]
> Progressive tool exposure applies to the standard function-calling loop. It
> does **not** apply to CodeAct providers (`agent-framework-monty`,
> `agent-framework-hyperlight`). In CodeAct the model only sees a single
> `execute_code` tool, and host tools are exposed *inside the sandbox* as typed
> Python functions rather than as model tool-schemas. Host tools there are
> invoked without a `FunctionInvocationContext`, so `ctx.add_tools()` is not
> available; the helpers fail fast with a clear `RuntimeError` instead of
> silently doing nothing. To change a CodeAct agent's tool set, use the
> provider's own `add_tools` / `remove_tool` / `clear_tools` methods (applied
> between runs). The recommended provider-driven path for Monty and Hyperlight
> is shown in [`../context_providers/code_act/`](../context_providers/code_act/)
> ([`code_act.py`](../context_providers/code_act/code_act.py) for Hyperlight,
> [`monty_code_act.py`](../context_providers/code_act/monty_code_act.py) for
> Monty).

## Local shell & code interpreters

| Path | Demonstrates |
|------|--------------|
| [`local_shell_with_allowlist.py`](local_shell_with_allowlist.py) | `LocalShellTool` restricted by a strict command allow-list. |
| [`local_shell_with_environment_provider.py`](local_shell_with_environment_provider.py) | `LocalShellTool` wired with a `ShellEnvironmentProvider`. |
| [`local_code_interpreter/`](local_code_interpreter/) | Hyperlight-backed sandboxed code interpreter (standalone tool — *extra* pattern). |
| [`monty_code_interpreter/`](monty_code_interpreter/) | Monty-backed sandboxed code interpreter (standalone tool — *extra* pattern). |

> [!TIP]
> The `local_code_interpreter/` and `monty_code_interpreter/` samples show the
> standalone-tool wiring and are provided as *extra* reference. For most
> Monty/Hyperlight use cases the **recommended** path is the provider-driven
> CodeAct setup in
> [`../context_providers/code_act/`](../context_providers/code_act/), which adds
> dynamic tool / capability management.
