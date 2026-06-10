// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AGUI.A2UI.UnitTests;

/// <summary>
/// Unit tests for <see cref="A2UIComponentValidator"/>.
/// </summary>
/// <remarks>
/// Ported from the Python toolkit's <c>tests/test_validate.py</c> and the TypeScript toolkit's
/// <c>validate.test.ts</c> so all three languages agree on what counts as a valid A2UI surface.
/// The Python "non-list components" case is covered by the type system here (the parameter is a
/// <see cref="JsonArray"/>), so only the null/empty variants are ported.
/// </remarks>
public sealed class A2UIComponentValidatorTests
{
    private static A2UIValidationCatalog CreateCatalog() => new(new JsonObject
    {
        ["Row"] = new JsonObject
        {
            ["type"] = "object",
            ["required"] = new JsonArray("children"),
        },
        ["HotelCard"] = new JsonObject
        {
            ["type"] = "object",
            ["required"] = new JsonArray("name", "location", "rating", "pricePerNight"),
        },
    });

    private static JsonArray CreateValidComponents() => new(
        new JsonObject
        {
            ["id"] = "root",
            ["component"] = "Row",
            ["children"] = new JsonObject { ["componentId"] = "card", ["path"] = "/items" },
        },
        new JsonObject
        {
            ["id"] = "card",
            ["component"] = "HotelCard",
            ["name"] = new JsonObject { ["path"] = "name" },
            ["location"] = new JsonObject { ["path"] = "location" },
            ["rating"] = new JsonObject { ["path"] = "rating" },
            ["pricePerNight"] = new JsonObject { ["path"] = "pricePerNight" },
        });

    private static JsonObject CreateValidData() => new()
    {
        ["items"] = new JsonArray(new JsonObject
        {
            ["name"] = "Ritz",
            ["location"] = "NYC",
            ["rating"] = 4.8,
            ["pricePerNight"] = "$450",
        }),
    };

    private static HashSet<string> Codes(A2UIValidationResult result)
        => result.Errors.Select(e => e.Code).ToHashSet();

    [Fact]
    public void Validate_WellFormedSurface_IsValid()
    {
        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            CreateValidComponents(), CreateValidData(), CreateCatalog());

        // Assert
        Assert.True(result.Valid);
        Assert.Empty(result.Errors);
    }

    [Fact]
    public void Validate_MissingRoot_ReportsNoRoot()
    {
        // Arrange: rename the root component so no component carries id "root".
        JsonArray components = CreateValidComponents();
        components[0]!["id"] = "container";

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            components, CreateValidData(), CreateCatalog());

        // Assert
        Assert.False(result.Valid);
        Assert.Contains(A2UIValidationErrorCodes.NoRoot, Codes(result));
    }

    [Fact]
    public void Validate_MissingId_ReportsMissingId()
    {
        // Arrange
        var components = new JsonArray(new JsonObject
        {
            ["component"] = "Row",
            ["children"] = new JsonArray(),
        });

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(components);

        // Assert
        Assert.Contains(A2UIValidationErrorCodes.MissingId, Codes(result));
    }

    [Fact]
    public void Validate_MissingComponentType_ReportsMissingComponentType()
    {
        // Arrange
        var components = new JsonArray(new JsonObject { ["id"] = "root" });

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(components);

        // Assert
        Assert.Contains(A2UIValidationErrorCodes.MissingComponentType, Codes(result));
    }

    [Fact]
    public void Validate_DuplicateId_ReportsDuplicateId()
    {
        // Arrange
        var components = new JsonArray(
            new JsonObject { ["id"] = "root", ["component"] = "Row", ["children"] = new JsonArray("x") },
            new JsonObject { ["id"] = "x", ["component"] = "Row", ["children"] = new JsonArray() },
            new JsonObject { ["id"] = "x", ["component"] = "Row", ["children"] = new JsonArray() });

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(components);

        // Assert
        Assert.Contains(A2UIValidationErrorCodes.DuplicateId, Codes(result));
    }

    [Fact]
    public void Validate_EmptyOrNullComponents_FailsLoud()
    {
        // Act
        A2UIValidationResult emptyResult = A2UIComponentValidator.Validate(new JsonArray());
        A2UIValidationResult nullResult = A2UIComponentValidator.Validate(null);

        // Assert
        Assert.False(emptyResult.Valid);
        Assert.False(nullResult.Valid);
        Assert.Contains(A2UIValidationErrorCodes.EmptyComponents, Codes(emptyResult));
        Assert.Contains(A2UIValidationErrorCodes.EmptyComponents, Codes(nullResult));
    }

    [Fact]
    public void Validate_UnknownComponent_ReportsUnknownComponent()
    {
        // Arrange: point the card at a type the catalog does not define.
        JsonArray components = CreateValidComponents();
        components[1]!["component"] = "MysteryCard";

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            components, CreateValidData(), CreateCatalog());

        // Assert
        Assert.Contains(A2UIValidationErrorCodes.UnknownComponent, Codes(result));
    }

    [Fact]
    public void Validate_MissingRequiredProp_ReportsPropNameInMessage()
    {
        // Arrange: drop a catalog-required property from the card.
        JsonArray components = CreateValidComponents();
        ((JsonObject)components[1]!).Remove("pricePerNight");

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            components, CreateValidData(), CreateCatalog());

        // Assert
        Assert.Contains(result.Errors, e =>
            e.Code == A2UIValidationErrorCodes.MissingRequiredProp && e.Message.Contains("pricePerNight"));
    }

    [Fact]
    public void Validate_WithoutCatalog_RunsStructuralChecksOnly()
    {
        // Arrange: an unknown component type is acceptable when no catalog is supplied.
        JsonArray components = CreateValidComponents();
        components[1]!["component"] = "MysteryCard";

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(components, CreateValidData());

        // Assert
        Assert.DoesNotContain(A2UIValidationErrorCodes.UnknownComponent, Codes(result));
        Assert.True(result.Valid);
    }

    [Fact]
    public void Validate_StructuralChildUnresolved_ReportsReferencedId()
    {
        // Arrange: the repeated-template child references a component that does not exist.
        var components = new JsonArray(new JsonObject
        {
            ["id"] = "root",
            ["component"] = "Row",
            ["children"] = new JsonObject { ["componentId"] = "ghost", ["path"] = "/items" },
        });

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            components, CreateValidData(), CreateCatalog());

        // Assert
        Assert.Contains(result.Errors, e =>
            e.Code == A2UIValidationErrorCodes.UnresolvedChild && e.Message.Contains("ghost"));
    }

    [Fact]
    public void Validate_ArrayChildUnresolved_ReportsReferencedId()
    {
        // Arrange
        var components = new JsonArray(new JsonObject
        {
            ["id"] = "root",
            ["component"] = "Row",
            ["children"] = new JsonArray("missing-1"),
        });

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(components);

        // Assert
        Assert.Contains(result.Errors, e =>
            e.Code == A2UIValidationErrorCodes.UnresolvedChild && e.Message.Contains("missing-1"));
    }

    [Fact]
    public void Validate_AbsoluteBindingUnresolved_ReportsPathInMessage()
    {
        // Arrange: empty data model cannot satisfy the absolute "/items" template path.
        var emptyData = new JsonObject();

        // Act
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            CreateValidComponents(), emptyData, CreateCatalog());

        // Assert
        Assert.Contains(result.Errors, e =>
            e.Code == A2UIValidationErrorCodes.UnresolvedBinding && e.Message.Contains("/items"));
    }

    [Fact]
    public void Validate_RelativeBindings_AreNotValidated()
    {
        // Act: card props use relative paths (resolved per item inside the template).
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            CreateValidComponents(), CreateValidData(), CreateCatalog());

        // Assert
        Assert.DoesNotContain(A2UIValidationErrorCodes.UnresolvedBinding, Codes(result));
    }

    [Fact]
    public void Validate_ValidateBindingsFalse_DefersBindingChecks()
    {
        // Act: with binding checks deferred, an empty data model is acceptable.
        A2UIValidationResult result = A2UIComponentValidator.Validate(
            CreateValidComponents(), new JsonObject(), CreateCatalog(), validateBindings: false);

        // Assert
        Assert.DoesNotContain(A2UIValidationErrorCodes.UnresolvedBinding, Codes(result));
        Assert.True(result.Valid);
    }
}
