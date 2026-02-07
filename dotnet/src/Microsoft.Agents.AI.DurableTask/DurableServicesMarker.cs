// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Marker class used to track whether core durable task services have been registered.
/// </summary>
/// <remarks>
/// <para>
/// <b>Problem it solves:</b> Users may call configuration methods multiple times:
/// <code>
/// services.ConfigureDurableOptions(...);     // 1st call - registers agent A
/// services.ConfigureDurableOptions(...);     // 2nd call - registers workflow X
/// services.ConfigureDurableOptions(...);     // 3rd call - registers agent B and workflow Y
/// </code>
/// Each call invokes <c>EnsureDurableServicesRegistered</c>. Without this marker, core services like
/// <c>AddDurableTaskWorker</c> and <c>AddDurableTaskClient</c> would be registered multiple times,
/// causing runtime errors or unexpected behavior.
/// </para>
/// <para>
/// <b>How it works:</b>
/// <list type="number">
/// <item><description>First call: No marker in services → register marker + all core services</description></item>
/// <item><description>Subsequent calls: Marker exists → early return, skip core service registration</description></item>
/// </list>
/// </para>
/// <para>
/// <b>Why not use TryAddSingleton for everything?</b>
/// While <c>TryAddSingleton</c> prevents duplicate simple service registrations, it doesn't work for
/// complex registrations like <c>AddDurableTaskWorker</c> which have side effects and configure
/// internal builders. The marker pattern provides a clean, explicit guard for the entire registration block.
/// </para>
/// </remarks>
internal sealed class DurableServicesMarker;
