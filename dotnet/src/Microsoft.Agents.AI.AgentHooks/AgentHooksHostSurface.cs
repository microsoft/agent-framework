// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using AgentHooks;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// The agent-hooks code surface of this package (AGENT-HOOKS-0.1 §7.7.4, §13.1): what the
/// enforcement installed by <see cref="AgentHooksChatClientExtensions"/> emits and honours.
/// A host declaration document is resolved against this surface, so a document that names
/// anything outside it is refused before any agent exists.
/// </summary>
/// <remarks>
/// <para>
/// The surface is a fact about this package's code, not a setting: every interception
/// point of the contract is emitted, streamed output is buffered behind the verdicts,
/// and a <c>host_error:*</c> deny at the tool seam terminates the run (ADR 0035). A
/// document therefore has to state <c>"posture": {"tool_seam_host_error": "terminate"}</c>
/// explicitly; the contract's default posture (<c>continue</c>) does not match this code
/// and is refused as <c>declaration_error:surface_unsupported</c>.
/// </para>
/// <para>
/// Every point in the surface needs a binding that runs at it: a point with no binding
/// denies with <c>host_error:no_interceptor</c>, by the contract's zero-interceptor rule.
/// </para>
/// <para>
/// <c>int64_json</c> and <c>bigint_json</c> state that an integer token the model produced
/// reaches the core as that token. Tool-call arguments arrive as <see cref="System.Text.Json.JsonElement"/>
/// values and the wire projection keeps their text, so an integer beyond 2^53 or beyond
/// u64 is seen by the identity provider and refused (<c>host_error:context_invalid</c>)
/// rather than rounded to a double on the way.
/// </para>
/// </remarks>
public static class AgentHooksHostSurface
{
    /// <summary>Gets the surface the per-run factory resolves declarations against.</summary>
    public static HostSurface Surface { get; } = HostSurface.SdkDefault() with
    {
        InterceptionPoints = new HashSet<InterceptionPoint>
        {
            InterceptionPoint.AgentStartup,
            InterceptionPoint.Input,
            InterceptionPoint.PreModelCall,
            InterceptionPoint.PostModelCall,
            InterceptionPoint.PreToolCall,
            InterceptionPoint.PostToolCall,
            InterceptionPoint.Output,
            InterceptionPoint.AgentShutdown,
        },
        Capabilities = new HashSet<string>
        {
            "model_calls",
            "tool_calls",
            "parallel_tool_calls",
            "streaming",
            "multi_turn",
            "int64_json",
            "bigint_json",
            "host_declaration",
        },
        ToolSeamHostError = ToolSeamPosture.Terminate,
        StreamsUnbuffered = false,
    };
}
