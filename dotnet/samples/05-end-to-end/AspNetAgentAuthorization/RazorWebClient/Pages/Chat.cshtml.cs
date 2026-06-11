// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace AspNetAgentAuthorization.RazorWebClient.Pages;

public class ChatModel : PageModel
{
    private readonly IHttpClientFactory _httpClientFactory;

    public ChatModel(IHttpClientFactory httpClientFactory)
    {
        this._httpClientFactory = httpClientFactory;
    }

    [BindProperty]
    public string? Message { get; set; }

    public string? Reply { get; set; }
    public string? ReplyUser { get; set; }
    public string? Error { get; set; }

    public void OnGet()
    {
    }

    public async Task OnPostAsync()
    {
        if (string.IsNullOrWhiteSpace(this.Message))
        {
            return;
        }

        try
        {
            // Get the access token stored during OIDC login
            string? accessToken = await this.HttpContext.GetTokenAsync("access_token");
            if (accessToken is null)
            {
                this.Error = "No access token available. Please log in again.";
                return;
            }

            // Call the AgentService with the Bearer token
            var client = this._httpClientFactory.CreateClient("AgentService");
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);

            var payload = JsonSerializer.Serialize(new { message = this.Message });
            var content = new StringContent(payload, Encoding.UTF8, "application/json");

            var response = await client.PostAsync(new Uri("/chat", UriKind.Relative), content);

            if (response.IsSuccessStatusCode)
            {
                using var json = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync());
                this.Reply = json.RootElement.GetProperty("reply").GetString();
                this.ReplyUser = json.RootElement.GetProperty("user").GetString();
            }
            else
            {
                this.Error = response.StatusCode switch
                {
                    System.Net.HttpStatusCode.Unauthorized => "Authentication failed (401). Your session may have expired.",
                    System.Net.HttpStatusCode.Forbidden => "Access denied (403). Your account does not have the required 'agent.chat' scope.",
                    _ => $"AgentService returned {(int)response.StatusCode} {response.ReasonPhrase}."
                };
            }
        }
        catch (Exception ex)
        {
            this.Error = $"Failed to contact the AgentService: {ex.Message}";
        }
    }
}
