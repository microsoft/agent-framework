namespace Azure.AI.AgentsHosting.Ingress.Common.Id;

public interface IIdGenerator
{
    string Generate(string? category = null);
}

public static class IdGeneratorExtensions
{
    public static string GenerateFunctionCallId(this IIdGenerator idGenerator) => idGenerator.Generate("func");

    public static string GenerateFunctionOutputId(this IIdGenerator idGenerator) => idGenerator.Generate("funcout");

    public static string GenerateMessageId(this IIdGenerator idGenerator) => idGenerator.Generate("msg");
}
