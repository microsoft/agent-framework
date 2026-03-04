// Copyright (c) Microsoft. All rights reserved.

namespace AgentWebChat.AppHost;

public static class ModelExtensions
{
    public static IResourceBuilder<AIModel> AddAIModel(this IDistributedApplicationBuilder builder, string name)
    {
        var model = new AIModel(name);
        return builder.CreateResourceBuilder(model);
    }

    public static IResourceBuilder<AIModel> RunAsOpenAI(this IResourceBuilder<AIModel> builder, string modelName, IResourceBuilder<ParameterResource> apiKey)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            return builder.AsOpenAI(modelName, apiKey);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> PublishAsOpenAI(this IResourceBuilder<AIModel> builder, string modelName, IResourceBuilder<ParameterResource> apiKey)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsPublishMode)
        {
            return builder.AsOpenAI(modelName, apiKey);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> RunAsAzureOpenAI(this IResourceBuilder<AIModel> builder, string modelName, Action<IResourceBuilder<AzureOpenAIResource>>? configure)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            return builder.AsAzureOpenAI(modelName, configure);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> PublishAsAzureOpenAI(this IResourceBuilder<AIModel> builder, string modelName, Action<IResourceBuilder<AzureOpenAIResource>>? configure)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsPublishMode)
        {
            return builder.AsAzureOpenAI(modelName, configure);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> AsAzureOpenAI(this IResourceBuilder<AIModel> builder, string modelName, Action<IResourceBuilder<AzureOpenAIResource>>? configure)
    {
        builder.Reset();

        var openAIModel = builder.ApplicationBuilder.AddAzureOpenAI(builder.Resource.Name);

        configure?.Invoke(openAIModel);

        builder.Resource.UnderlyingResource = openAIModel.Resource;
        // Add the model name to the connection string
        builder.Resource.ConnectionString = ReferenceExpression.Create($"{openAIModel.Resource.ConnectionStringExpression};Model={modelName}");
        builder.Resource.Provider = "AzureOpenAI";
        return builder;
    }

    public static IResourceBuilder<AIModel> RunAsAzureAIInference(this IResourceBuilder<AIModel> builder, string modelName, IResourceBuilder<ParameterResource> endpoint, IResourceBuilder<ParameterResource> apiKey)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            return builder.AsAzureAIInference(modelName, endpoint, apiKey);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> PublishAsAzureAIInference(this IResourceBuilder<AIModel> builder, string modelName, IResourceBuilder<ParameterResource> endpoint, IResourceBuilder<ParameterResource> apiKey)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsPublishMode)
        {
            return builder.AsAzureAIInference(modelName, endpoint, apiKey);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> AsAzureAIInference(this IResourceBuilder<AIModel> builder, string modelName, IResourceBuilder<ParameterResource> endpoint, IResourceBuilder<ParameterResource> apiKey)
    {
        builder.Reset();

        // See: https://github.com/dotnet/aspire/issues/7641
        var csb = new ReferenceExpressionBuilder();
        csb.Append($"Endpoint={endpoint.Resource};");
        csb.Append($"AccessKey={apiKey.Resource};");
        csb.Append($"Model={modelName}");
        var cs = csb.Build();

        builder.ApplicationBuilder.AddResource(builder.Resource);

        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            var csTask = cs.GetValueAsync(default).AsTask();
            if (!csTask.IsCompletedSuccessfully)
            {
                throw new InvalidOperationException("Connection string could not be resolved!");
            }

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
            builder.WithInitialState(new CustomResourceSnapshot
            {
                ResourceType = "Azure AI Inference Model",
                State = KnownResourceStates.Running,
                Properties = [
                  new("ConnectionString", csTask.Result ) { IsSensitive = true }
                ]
            });
#pragma warning restore VSTHRD002
        }

        builder.Resource.UnderlyingResource = builder.Resource;
        builder.Resource.ConnectionString = cs;
        builder.Resource.Provider = "AzureAIInference";

        return builder;
    }

    public static IResourceBuilder<AIModel> RunAsAzureAIInference(this IResourceBuilder<AIModel> builder, string modelName, string endpoint, IResourceBuilder<ParameterResource> apiKey)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            return builder.AsAzureAIInference(modelName, endpoint, apiKey);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> PublishAsAzureAIInference(this IResourceBuilder<AIModel> builder, string modelName, string endpoint, IResourceBuilder<ParameterResource> apiKey)
    {
        if (builder.ApplicationBuilder.ExecutionContext.IsPublishMode)
        {
            return builder.AsAzureAIInference(modelName, endpoint, apiKey);
        }

        return builder;
    }

    public static IResourceBuilder<AIModel> AsAzureAIInference(this IResourceBuilder<AIModel> builder, string modelName, string endpoint, IResourceBuilder<ParameterResource> apiKey)
    {
        builder.Reset();

        // See: https://github.com/dotnet/aspire/issues/7641
        var csb = new ReferenceExpressionBuilder();
        csb.Append($"Endpoint={endpoint};");
        csb.Append($"AccessKey={apiKey.Resource};");
        csb.Append($"Model={modelName}");
        var cs = csb.Build();

        builder.ApplicationBuilder.AddResource(builder.Resource);

        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            var csTask = cs.GetValueAsync(default).AsTask();
            if (!csTask.IsCompletedSuccessfully)
            {
                throw new InvalidOperationException("Connection string could not be resolved!");
            }

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
            builder.WithInitialState(new CustomResourceSnapshot
            {
                ResourceType = "Azure AI Inference Model",
                State = KnownResourceStates.Running,
                Properties = [
                  new("ConnectionString", csTask.Result ) { IsSensitive = true }
                ]
            });
#pragma warning restore VSTHRD002
        }

        builder.Resource.UnderlyingResource = builder.Resource;
        builder.Resource.ConnectionString = cs;
        builder.Resource.Provider = "AzureAIInference";

        return builder;
    }

    public static IResourceBuilder<AIModel> AsOpenAI(this IResourceBuilder<AIModel> builder, string modelName, IResourceBuilder<ParameterResource> apiKey)
    {
        builder.Reset();

        // See: https://github.com/dotnet/aspire/issues/7641
        var csb = new ReferenceExpressionBuilder();
        csb.Append($"AccessKey={apiKey.Resource};");
        csb.Append($"Model={modelName}");
        var cs = csb.Build();

        builder.ApplicationBuilder.AddResource(builder.Resource);

        if (builder.ApplicationBuilder.ExecutionContext.IsRunMode)
        {
            var csTask = cs.GetValueAsync(default).AsTask();
            if (!csTask.IsCompletedSuccessfully)
            {
                throw new InvalidOperationException("Connection string could not be resolved!");
            }

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
            builder.WithInitialState(new CustomResourceSnapshot
            {
                ResourceType = "OpenAI Model",
                State = KnownResourceStates.Running,
                Properties = [
                  new("ConnectionString", csTask.Result ) { IsSensitive = true }
                ]
            });
#pragma warning restore VSTHRD002
        }

        builder.Resource.UnderlyingResource = builder.Resource;
        builder.Resource.ConnectionString = cs;
        builder.Resource.Provider = "OpenAI";

        return builder;
    }

    private static void Reset(this IResourceBuilder<AIModel> builder)
    {
        // Reset the properties of the AIModel resource
        if (builder.Resource.UnderlyingResource is { } underlyingResource)
        {
            builder.ApplicationBuilder.Resources.Remove(underlyingResource);

            if (underlyingResource is IResourceWithParent resourceWithParent)
            {
                builder.ApplicationBuilder.Resources.Remove(resourceWithParent.Parent);
            }
        }

        builder.Resource.ConnectionString = null;
        builder.Resource.Provider = null;
    }
}

// A resource representing an AI model.
public class AIModel(string name) : Resource(name), IResourceWithConnectionString
{
    internal string? Provider { get; set; }
    internal IResourceWithConnectionString? UnderlyingResource { get; set; }
    internal ReferenceExpression? ConnectionString { get; set; }

    public ReferenceExpression ConnectionStringExpression =>
        this.Build();

    public ReferenceExpression Build()
    {
        var connectionString = this.ConnectionString ?? throw new InvalidOperationException("No connection string available.");

        if (this.Provider is null)
        {
            throw new InvalidOperationException("No provider configured.");
        }

        return ReferenceExpression.Create($"{connectionString};Provider={this.Provider}");
    }
}
