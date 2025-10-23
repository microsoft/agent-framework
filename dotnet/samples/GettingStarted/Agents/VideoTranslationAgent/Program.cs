// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to create an AI agent that can translate videos using Azure Video Translation service.
// The agent has tools to upload videos to Azure Blob Storage, translate videos, list translations, get details, and delete translations.

using System;
using System.ComponentModel;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Azure.Storage.Blobs;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

// Get required environment variables
var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") 
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";
var storageAccountName = Environment.GetEnvironmentVariable("AZURE_STORAGE_ACCOUNT_NAME");
var containerName = Environment.GetEnvironmentVariable("AZURE_STORAGE_CONTAINER_NAME");

// Create credential for authentication
var credential = new DefaultAzureCredential();

// Initialize the video translation client
var videoClient = new VideoTranslationAgent.VideoTranslationClient(credential: credential);

[Description("Downloads a video from a public URL and uploads it to Azure Blob Storage. Returns the Azure blob URL.")]
async Task<string> DownloadAndUploadVideo(
    [Description("The public URL of the video to download")] string publicUrl,
    [Description("Optional local filename")] string? localFilename = null)
{
    try
    {
        localFilename ??= Path.GetFileName(new Uri(publicUrl).AbsolutePath);
        
        Console.WriteLine($"Downloading video from {publicUrl}...");
        using var httpClient = new HttpClient();
        var response = await httpClient.GetAsync(publicUrl);
        response.EnsureSuccessStatusCode();
        
        await using var fileStream = File.Create(localFilename);
        await response.Content.CopyToAsync(fileStream);
        await fileStream.FlushAsync();
        fileStream.Close();
        
        Console.WriteLine($"Downloaded video to {localFilename}");
        var blobUrl = await UploadVideoToBlob(localFilename);
        Console.WriteLine($"Uploaded video to Azure Blob Storage: {blobUrl}");
        
        File.Delete(localFilename);
        return blobUrl;
    }
    catch (Exception ex)
    {
        return $"Error downloading/uploading video: {ex.Message}";
    }
}

[Description("Uploads a local video file to Azure Blob Storage and returns the blob URL. Requires AZURE_STORAGE_ACCOUNT_NAME and AZURE_STORAGE_CONTAINER_NAME environment variables.")]
async Task<string> UploadVideoToBlob(
    [Description("Path to the local video file")] string localFilePath)
{
    var accountName = Environment.GetEnvironmentVariable("AZURE_STORAGE_ACCOUNT_NAME");
    var containerName = Environment.GetEnvironmentVariable("AZURE_STORAGE_CONTAINER_NAME");
    
    if (string.IsNullOrEmpty(accountName) || string.IsNullOrEmpty(containerName))
    {
        return "Missing Azure Storage configuration in environment variables.";
    }
    
    try
    {
        var credential = new DefaultAzureCredential();
        var blobServiceClient = new BlobServiceClient(
            new Uri($"https://{accountName}.blob.core.windows.net"),
            credential);
        
        var blobName = Path.GetFileName(localFilePath);
        var containerClient = blobServiceClient.GetBlobContainerClient(containerName);
        var blobClient = containerClient.GetBlobClient(blobName);
        
        await using var fileStream = File.OpenRead(localFilePath);
        await blobClient.UploadAsync(fileStream, overwrite: true);
        
        var blobUrl = $"https://{accountName}.blob.core.windows.net/{containerName}/{blobName}";
        Console.WriteLine($"Uploaded video to blob: {blobUrl}");
        return blobUrl;
    }
    catch (Exception ex)
    {
        return $"Error uploading video: {ex.Message}";
    }
}

[Description("Translates a video to the target language using Azure Video Translation. The target language must be a full locale code (e.g., 'fr-FR' for French, 'en-US' for English, 'es-ES' for Spanish).")]
async Task<string> TranslateVideo(
    [Description("The URL of the video to translate (must be accessible from Azure)")] string videoUrl,
    [Description("The target language locale code (e.g., 'fr-FR', 'en-US', 'es-ES')")] string targetLanguage)
{
    try
    {
        Console.WriteLine($"Starting video translation: url={videoUrl}, target_language={targetLanguage}");
        const string sourceLocale = "en-US";
        const VideoTranslationAgent.VoiceKind voiceKind = VideoTranslationAgent.VoiceKind.PlatformVoice;
        
        var (success, error, translation, iteration) = await videoClient.CreateTranslateAndRunFirstIterationUntilTerminatedAsync(
            videoUrl, sourceLocale, targetLanguage, voiceKind);
        
        if (success && translation != null && iteration != null)
        {
            Console.WriteLine($"Translation successful! Translation ID: {translation.Id}, Iteration ID: {iteration.Id}");
            return $"Translation successful! Translation ID: {translation.Id} | Iteration ID: {iteration.Id}";
        }
        else
        {
            Console.WriteLine($"Translation failed: {error}");
            return $"Translation failed: {error}";
        }
    }
    catch (Exception ex)
    {
        return $"Error during translation: {ex.Message}";
    }
}

[Description("Lists all video translations.")]
async Task<string> ListTranslations()
{
    try
    {
        Console.WriteLine("Listing all translations...");
        var (success, error, paged) = await videoClient.RequestListTranslationsAsync();
        
        if (success && paged?.Value != null)
        {
            var ids = string.Join(", ", Array.ConvertAll(paged.Value, t => t.Id ?? "unknown"));
            return $"Translations: [{ids}]";
        }
        else
        {
            return $"Failed to list translations: {error}";
        }
    }
    catch (Exception ex)
    {
        return $"Error listing translations: {ex.Message}";
    }
}

[Description("Gets detailed information about a specific video translation.")]
async Task<string> GetTranslationDetails(
    [Description("The ID of the translation to get details for")] string translationId)
{
    try
    {
        Console.WriteLine($"Getting details for translation: {translationId}");
        var (success, error, translation) = await videoClient.RequestGetTranslationAsync(translationId);
        
        if (success && translation != null)
        {
            return $"Translation details: {JsonSerializer.Serialize(translation, new JsonSerializerOptions { WriteIndented = true })}";
        }
        else
        {
            return $"Failed to get translation details: {error}";
        }
    }
    catch (Exception ex)
    {
        return $"Error getting translation details: {ex.Message}";
    }
}

[Description("Deletes a video translation.")]
async Task<string> DeleteTranslation(
    [Description("The ID of the translation to delete")] string translationId)
{
    try
    {
        Console.WriteLine($"Deleting translation: {translationId}");
        var (success, error) = await videoClient.RequestDeleteTranslationAsync(translationId);
        
        if (success)
        {
            return $"Translation {translationId} deleted successfully.";
        }
        else
        {
            return $"Failed to delete translation: {error}";
        }
    }
    catch (Exception ex)
    {
        return $"Error deleting translation: {ex.Message}";
    }
}

[Description("Lists all iterations for a specific video translation.")]
async Task<string> ListIterations(
    [Description("The ID of the translation to list iterations for")] string translationId)
{
    try
    {
        Console.WriteLine($"Listing iterations for translation: {translationId}");
        var (success, error, paged) = await videoClient.RequestListIterationsAsync(translationId);
        
        if (success && paged?.Value != null)
        {
            var ids = string.Join(", ", Array.ConvertAll(paged.Value, i => i.Id ?? "unknown"));
            return $"Iterations: [{ids}]";
        }
        else
        {
            return $"Failed to list iterations: {error}";
        }
    }
    catch (Exception ex)
    {
        return $"Error listing iterations: {ex.Message}";
    }
}

// Create the AI agent with video translation tools
AIAgent agent = new AzureOpenAIClient(new Uri(azureOpenAIEndpoint), credential)
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        instructions: """
            You are a helpful assistant for Azure Video Translation.
            If you have a local video file, first upload it to Azure Blob Storage using the UploadVideoToBlob tool, then use the resulting blob URL for translation.
            If you have a publicly accessible video URL, you can use it directly with the TranslateVideo tool.
            When translating videos, always use the full locale code for languages (e.g., 'fr-FR' for French, 'en-US' for English, 'es-ES' for Spanish).
            You can upload videos, translate videos, list translations, get details, delete translations, and list iterations.
            """,
        tools: [
            AIFunctionFactory.Create(UploadVideoToBlob),
            AIFunctionFactory.Create(DownloadAndUploadVideo),
            AIFunctionFactory.Create(TranslateVideo),
            AIFunctionFactory.Create(ListTranslations),
            AIFunctionFactory.Create(GetTranslationDetails),
            AIFunctionFactory.Create(DeleteTranslation),
            AIFunctionFactory.Create(ListIterations)
        ]);

// Example query - you can modify this or make it interactive
var query = "Translate this video \"https://kchandistorage.blob.core.windows.net/videos/en-US-TryoutOriginalTTSIntro.mp4%20(1).mp4?sp=r&st=2025-09-12T22:31:35Z&se=2025-09-13T06:46:35Z&skoid=f742ec34-98c1-4a09-800c-fe1ce6fc1e33&sktid=72f988bf-86f1-41af-91ab-2d7cd011db47&skt=2025-09-12T22:31:35Z&ske=2025-09-13T06:46:35Z&sks=b&skv=2024-11-04&spr=https&sv=2024-11-04&sr=b&sig=1VNyUh00q8XYp6ucR09WQ839B38jjXbVA8m5zcojuwk%3D\" to French.";

Console.WriteLine($"Running agent with query: {query}");
Console.WriteLine();

// Run the agent
var result = await agent.RunAsync(query);
Console.WriteLine($"\nAgent response: {result}");
