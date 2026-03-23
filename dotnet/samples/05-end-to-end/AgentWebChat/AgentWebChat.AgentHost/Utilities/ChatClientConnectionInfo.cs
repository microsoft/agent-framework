// Copyright (c) Microsoft. All rights reserved.

using System.Data.Common;
using System.Diagnostics.CodeAnalysis;

namespace AgentWebChat.AgentHost.Utilities;

public class ChatClientConnectionInfo
{
    public Uri? Endpoint { get; init; }
    public required string SelectedModel { get; init; }

    public ClientChatProvider Provider { get; init; }
    public string? AccessKey { get; init; }

    // Example connection string:
    // Endpoint=https://localhost:4523;Model=phi3.5;AccessKey=1234;Provider=ollama;
    public static bool TryParse(string? connectionString, [NotNullWhen(true)] out ChatClientConnectionInfo? settings)
    {
        if (string.IsNullOrEmpty(connectionString))
        {
            settings = null;
            return false;
        }

        var connectionBuilder = new DbConnectionStringBuilder
        {
            ConnectionString = connectionString
        };

        Uri? endpoint = null;
        if (connectionBuilder.ContainsKey("Endpoint") && Uri.TryCreate(connectionBuilder["Endpoint"].ToString(), UriKind.Absolute, out endpoint))
        {
        }

        string? model = null;
        if (connectionBuilder.ContainsKey("Model"))
        {
            model = (string)connectionBuilder["Model"];
        }

        string? accessKey = null;
        if (connectionBuilder.ContainsKey("AccessKey"))
        {
            accessKey = (string)connectionBuilder["AccessKey"];
        }

        var provider = ClientChatProvider.Unknown;
        if (connectionBuilder.ContainsKey("Provider"))
        {
            var providerValue = (string)connectionBuilder["Provider"];
            Enum.TryParse(providerValue, ignoreCase: true, out provider);
        }

        if ((endpoint is null && provider != ClientChatProvider.OpenAI) || model is null || provider is ClientChatProvider.Unknown)
        {
            settings = null;
            return false;
        }

        settings = new ChatClientConnectionInfo
        {
            Endpoint = endpoint,
            SelectedModel = model,
            AccessKey = accessKey,
            Provider = provider
        };

        return true;
    }
}

public enum ClientChatProvider
{
    Unknown,
    Ollama,
    OpenAI,
    AzureOpenAI,
    AzureAIInference,
}
