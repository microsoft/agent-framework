// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Globalization;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Tool bracket: emits <c>pre_tool_call</c> and <c>post_tool_call</c> around each
/// host-executed function invocation.
/// </summary>
/// <remarks>
/// <para>
/// Installed by the agent-hooks factory through the framework's function-invocation
/// middleware seam (<see cref="FunctionInvocationDelegatingAgentBuilderExtensions"/>),
/// which wraps every <see cref="AIFunction"/> so this callback brackets the invocation.
/// </para>
/// <para>
/// A policy deny blocks the tool call — the tool is not executed (or its result is
/// discarded) and a tool-error payload is surfaced to the model so the agent loop can
/// continue, per the spec's block-propagation rules. A <c>host_error:*</c> deny (the
/// enforcement layer itself failed) additionally halts the run: the loop is terminated
/// via <see cref="FunctionInvocationContext.Terminate"/> — the only loud escape from the
/// function-invocation loop, which converts thrown exceptions into tool errors and keeps
/// running (fail open) — and the agent seam rethrows the failure at the run boundary.
/// </para>
/// <para>
/// Approval flows pass through structurally: the framework requests tool approvals
/// before ever invoking the wrapped function, so an unapproved tool never reaches this
/// seam, and the approved replay enters through <c>pre_tool_call</c> when it actually
/// executes.
/// </para>
/// <para>
/// Known limitation (service-side tool execution): tools executed by the model provider
/// itself never pass through the function-invocation seam, so <c>pre_tool_call</c> /
/// <c>post_tool_call</c> cannot intercept them. Their calls and outputs are surfaced in
/// the <c>post_model_call</c> content projection, where interceptors can observe and
/// deny/transform the response that carries them.
/// </para>
/// </remarks>
internal static class AgentHooksFunctionMiddleware
{
    internal static Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> CreateCallback(
        AgentHooksConfiguration configuration) =>
        (agent, context, next, cancellationToken) => InvokeAsync(configuration, context, next, cancellationToken);

    private static async ValueTask<object?> InvokeAsync(
        AgentHooksConfiguration configuration,
        FunctionInvocationContext context,
        Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next,
        CancellationToken cancellationToken)
    {
        var state = AgentHooksRunState.Current;
        if (state is null)
        {
            // No run state means the agent seam never ran (the guarded agent's inner
            // pieces were extracted and reused). The tool is never dispatched and the
            // loop is stopped — throwing here would be converted into a tool error by
            // the function-invocation loop and the run would continue unguarded.
            context.Terminate = true;
            return new JsonObject
            {
                ["error"] = "The agent-hooks function seam was invoked without an active agent-hooks run. " +
                    "The agent-hooks decorators must be installed as one unit by the agent-hooks factory.",
            };
        }

        if (!ReferenceEquals(state.Configuration, configuration))
        {
            // A different installation owns the innermost run state (nested guarded
            // agents sharing seams): binding to it would silently misroute emissions.
            return HaltEnforcementFailure(
                state,
                context,
                new InvalidOperationException(
                    "The agent-hooks function seam found an active agent-hooks run owned by a different " +
                    "agent-hooks installation. Nesting one guarded agent's tools inside another guarded agent " +
                    "is not supported."),
                "pre_tool_call");
        }

        string callId = context.CallContent?.CallId is { Length: > 0 } id
            ? id
            : Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture);
        string name = context.Function?.Name ?? context.CallContent?.Name ?? "unknown";

        JsonObject args;
        try
        {
            // The projection runs inside the guarded block: a projection failure (e.g. a
            // poisoned argument value whose serialization throws) is an enforcement-layer
            // failure and must halt the run, not crash it with a trail gap.
            args = ToolArgumentsCodec.ToWire(context.Arguments);
            var outcome = await state.Emitter.EmitAsync(state.Builder.PreToolCall(callId, name, args), cancellationToken).ConfigureAwait(false);
            args = ToolArgumentsCodec.WriteBack(context.Arguments, args, outcome.Target, out var merged);
            if (merged is not null)
            {
                // The transform rewrote (some of) the arguments: execute the approved
                // values, keeping untouched keys' original native values. The argument
                // dictionary is mutated in place to preserve any framework-managed
                // context riding on it.
                foreach (var key in context.Arguments.Keys.ToArray())
                {
                    if (!merged.ContainsKey(key))
                    {
                        _ = context.Arguments.Remove(key);
                    }
                }

                foreach (var (key, value) in merged)
                {
                    context.Arguments[key] = value;
                }
            }
        }
        catch (InterceptionBlockedException exception)
        {
            // §6.2: the tool is not dispatched and no post_tool_call is emitted.
            return Block(state, context, exception, "pre_tool_call");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception exception)
        {
            return HaltEnforcementFailure(state, context, exception, "pre_tool_call");
        }

        object? result;
        try
        {
            result = await next(context, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception invokeException)
        {
            // The invocation errored: the contract still brackets it (is_error=true).
            // Only the exception type name crosses the boundary (spec §6.3/§14).
            try
            {
                _ = await state.Emitter.EmitAsync(
                    state.Builder.PostToolCall(callId, name, args, JsonValue.Create(invokeException.GetType().Name), isError: true),
                    cancellationToken).ConfigureAwait(false);
            }
            catch (InterceptionBlockedException blocked)
            {
                // A policy deny over an already-errored call changes nothing (the
                // result is discarded either way); a host error still halts the run.
                MaybeHalt(state, context, blocked, "post_tool_call");
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception emitException)
            {
                _ = HaltEnforcementFailure(state, context, emitException, "post_tool_call");
            }

            throw;
        }

        try
        {
            var value = ToolResultCodec.ToWire(result);
            var outcome = await state.Emitter.EmitAsync(state.Builder.PostToolCall(callId, name, args, value), cancellationToken).ConfigureAwait(false);
            return ToolResultCodec.WriteBack(result, value, outcome.Target);
        }
        catch (InterceptionBlockedException exception)
        {
            // §6.1: the result must be discarded as if the call had errored.
            return Block(state, context, exception, "post_tool_call");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception exception)
        {
            return HaltEnforcementFailure(state, context, exception, "post_tool_call");
        }
    }

    /// <summary>Enforce a tool-seam deny: surface a tool error and, on host errors, halt the run.</summary>
    private static JsonObject Block(
        AgentHooksRunState state, FunctionInvocationContext context, InterceptionBlockedException exception, string point)
    {
        var payload = new JsonObject
        {
            ["error"] = $"Tool call blocked by agent-hooks at {point}.",
            ["reason"] = exception.Result.Verdict.Reason ?? "deny",
        };
        if (exception.Result.Verdict.Message is string message)
        {
            payload["message"] = message;
        }

        MaybeHalt(state, context, exception, point);
        return payload;
    }

    private static void MaybeHalt(
        AgentHooksRunState state, FunctionInvocationContext context, InterceptionBlockedException exception, string point)
    {
        if (exception.Result.Verdict.Reason?.StartsWith("host_error:", StringComparison.Ordinal) is true)
        {
            // The enforcement layer itself failed (interceptor crash/timeout, invalid
            // context): continuing the loop would run unguarded. Halt the run; the
            // agent seam rethrows the block to the caller at the run boundary.
            state.Halted = exception;
            context.Terminate = true;
        }
    }

    /// <summary>
    /// Route an unexpected failure inside the enforcement layer through the fail-closed
    /// halt path: the function-invocation loop converts thrown exceptions into
    /// tool-error results and keeps running, so for a failure of the enforcement layer
    /// itself that would fail open. Instead the loop is stopped via
    /// <see cref="FunctionInvocationContext.Terminate"/> and the agent seam rethrows the
    /// failure at the run boundary.
    /// </summary>
    private static JsonObject HaltEnforcementFailure(
        AgentHooksRunState state, FunctionInvocationContext context, Exception exception, string point)
    {
        string message = $"agent-hooks {point} enforcement failed: {exception.GetType().Name}";
        state.Halted = exception as InvalidOperationException ?? new InvalidOperationException(message, exception);
        context.Terminate = true;
        return new JsonObject { ["error"] = message };
    }
}
