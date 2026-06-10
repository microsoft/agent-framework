// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Error codes emitted by <see cref="A2UIComponentValidator"/>.
/// </summary>
/// <remarks>
/// The string values are part of the cross-language A2UI contract (shared with the
/// TypeScript and Python toolkits) and feed back into subagent retry prompts; they
/// must not diverge from the sibling implementations.
/// </remarks>
public static class A2UIValidationErrorCodes
{
    /// <summary>The component set is missing or empty.</summary>
    public const string EmptyComponents = "empty_components";

    /// <summary>A component has no usable string <c>id</c>.</summary>
    public const string MissingId = "missing_id";

    /// <summary>A component has no usable string <c>component</c> type.</summary>
    public const string MissingComponentType = "missing_component_type";

    /// <summary>Two or more components share the same <c>id</c>.</summary>
    public const string DuplicateId = "duplicate_id";

    /// <summary>No component carries the mandatory <c>id</c> of <c>"root"</c>.</summary>
    public const string NoRoot = "no_root";

    /// <summary>A component type is not present in the supplied catalog.</summary>
    public const string UnknownComponent = "unknown_component";

    /// <summary>A component lacks a property the catalog marks as required.</summary>
    public const string MissingRequiredProp = "missing_required_prop";

    /// <summary>A child reference points at a component id that does not exist.</summary>
    public const string UnresolvedChild = "unresolved_child";

    /// <summary>An absolute data binding path does not resolve in the data model.</summary>
    public const string UnresolvedBinding = "unresolved_binding";
}

/// <summary>
/// A single semantic validation finding for an A2UI component tree.
/// </summary>
/// <param name="Code">One of the <see cref="A2UIValidationErrorCodes"/> values.</param>
/// <param name="Path">A JSON-pointer-style location, e.g. <c>components[1].rating</c>.</param>
/// <param name="Message">A human/model-readable description used in retry prompts.</param>
public sealed record A2UIValidationError(string Code, string Path, string Message);

/// <summary>
/// The outcome of validating an A2UI component tree.
/// </summary>
/// <param name="Valid"><see langword="true"/> when no errors were found.</param>
/// <param name="Errors">The findings, empty when <paramref name="Valid"/> is <see langword="true"/>.</param>
public sealed record A2UIValidationResult(bool Valid, IReadOnlyList<A2UIValidationError> Errors);

/// <summary>
/// An inline component catalog used for semantic validation: component schemas
/// (standard JSON Schema fragments with an optional <c>required</c> array) keyed by component name.
/// </summary>
public sealed class A2UIValidationCatalog
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2UIValidationCatalog"/> class.
    /// </summary>
    /// <param name="components">Component schemas keyed by component name.</param>
    public A2UIValidationCatalog(JsonObject components)
    {
        this.Components = components ?? throw new ArgumentNullException(nameof(components));
    }

    /// <summary>
    /// Gets the component schemas keyed by component name.
    /// </summary>
    public JsonObject Components { get; }
}

/// <summary>
/// Semantic validator for A2UI v0.9 component trees, mirroring
/// <c>validateA2UIComponents</c> / <c>validate_a2ui_components</c> in the sibling toolkits.
/// </summary>
/// <remarks>
/// Structural checks (ids, component types, root presence, child references) always run.
/// Catalog checks (component existence, required props) run only when a catalog is supplied.
/// Absolute data-binding checks run unless <c>validateBindings</c> is <see langword="false"/>;
/// relative binding paths are never validated globally because they resolve per item inside
/// repeated templates.
/// </remarks>
public static class A2UIComponentValidator
{
    /// <summary>
    /// Validates a flat A2UI component array against structural rules and, optionally,
    /// a component catalog and a data model.
    /// </summary>
    /// <param name="components">The flat component array. <see langword="null"/> or empty fails validation.</param>
    /// <param name="data">The surface data model used to resolve absolute binding paths.</param>
    /// <param name="catalog">The component catalog enabling semantic checks.</param>
    /// <param name="validateBindings">
    /// When <see langword="false"/>, absolute binding checks are deferred (used while the data
    /// model has not finished streaming).
    /// </param>
    /// <returns>The validation outcome.</returns>
    public static A2UIValidationResult Validate(
        JsonArray? components,
        JsonObject? data = null,
        A2UIValidationCatalog? catalog = null,
        bool validateBindings = true)
        => throw new NotImplementedException();
}
