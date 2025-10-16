namespace Azure.AI.AgentsHosting.Ingress.Common.Id;

/// <summary>
/// Defines the interface for generating IDs.
/// </summary>
public interface IIdGenerator
{
    /// <summary>
    /// Generates a new ID.
    /// </summary>
    /// <param name="category">The optional category for the ID.</param>
    /// <returns>A generated ID string.</returns>
    string Generate(string? category = null);
}

/// <summary>
/// Extension methods for IIdGenerator.
/// </summary>
public static class IdGeneratorExtensions
{
    /// <summary>
    /// Generates a function call ID.
    /// </summary>
    /// <param name="idGenerator">The ID generator.</param>
    /// <returns>A function call ID.</returns>
    public static string GenerateFunctionCallId(this IIdGenerator idGenerator) => idGenerator.Generate("func");

    /// <summary>
    /// Generates a function output ID.
    /// </summary>
    /// <param name="idGenerator">The ID generator.</param>
    /// <returns>A function output ID.</returns>
    public static string GenerateFunctionOutputId(this IIdGenerator idGenerator) => idGenerator.Generate("funcout");

    /// <summary>
    /// Generates a message ID.
    /// </summary>
    /// <param name="idGenerator">The ID generator.</param>
    /// <returns>A message ID.</returns>
    public static string GenerateMessageId(this IIdGenerator idGenerator) => idGenerator.Generate("msg");
}
