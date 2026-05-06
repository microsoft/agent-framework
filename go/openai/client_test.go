package openai_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	af "github.com/microsoft/agent-framework/go"
	"github.com/microsoft/agent-framework/go/openai"
	gogpt "github.com/sashabaranov/go-openai"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestClientGetResponse(t *testing.T) {
	t.Run("sends messages and returns response", func(t *testing.T) {
		var capturedReq gogpt.ChatCompletionRequest

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &capturedReq)

			resp := gogpt.ChatCompletionResponse{
				ID: "chatcmpl-123",
				Choices: []gogpt.ChatCompletionChoice{
					{
						Message: gogpt.ChatCompletionMessage{
							Role:    "assistant",
							Content: "Paris is the capital of France.",
						},
						FinishReason: gogpt.FinishReasonStop,
					},
				},
				Usage: gogpt.Usage{
					PromptTokens:     10,
					CompletionTokens: 8,
					TotalTokens:      18,
				},
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		client := openai.NewClient("test-key", "gpt-4o",
			openai.WithBaseURL(server.URL+"/v1"),
		)

		messages := []af.Message{
			af.NewSystemMessage("You are helpful."),
			af.NewUserMessage("What is the capital of France?"),
		}

		resp, err := client.GetResponse(context.Background(), messages)

		require.NoError(t, err)

		// Verify request was mapped correctly
		require.Len(t, capturedReq.Messages, 2)
		assert.Equal(t, "system", capturedReq.Messages[0].Role)
		assert.Equal(t, "You are helpful.", capturedReq.Messages[0].Content)
		assert.Equal(t, "user", capturedReq.Messages[1].Role)
		assert.Equal(t, "What is the capital of France?", capturedReq.Messages[1].Content)
		assert.Equal(t, "gpt-4o", capturedReq.Model)

		// Verify response was mapped correctly
		require.Len(t, resp.Messages, 1)
		assert.Equal(t, af.RoleAssistant, resp.Messages[0].Role)
		assert.Equal(t, "Paris is the capital of France.", resp.Messages[0].Text())
		assert.Equal(t, "chatcmpl-123", resp.ResponseID)
		require.NotNil(t, resp.Usage)
		assert.Equal(t, 10, resp.Usage.InputTokens)
		assert.Equal(t, 8, resp.Usage.OutputTokens)
		assert.Equal(t, 18, resp.Usage.TotalTokens)
	})

	t.Run("applies chat options", func(t *testing.T) {
		var capturedReq gogpt.ChatCompletionRequest

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &capturedReq)

			resp := gogpt.ChatCompletionResponse{
				Choices: []gogpt.ChatCompletionChoice{
					{Message: gogpt.ChatCompletionMessage{Role: "assistant", Content: "ok"}},
				},
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		client := openai.NewClient("test-key", "gpt-4o",
			openai.WithBaseURL(server.URL+"/v1"),
		)

		_, err := client.GetResponse(context.Background(),
			[]af.Message{af.NewUserMessage("hi")},
			af.WithTemperature(0.5),
			af.WithMaxTokens(100),
		)

		require.NoError(t, err)
		assert.InDelta(t, 0.5, capturedReq.Temperature, 0.001)
		assert.Equal(t, 100, capturedReq.MaxTokens)
	})

	t.Run("returns error on API failure", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte(`{"error":{"message":"server error"}}`))
		}))
		defer server.Close()

		client := openai.NewClient("test-key", "gpt-4o",
			openai.WithBaseURL(server.URL+"/v1"),
		)

		_, err := client.GetResponse(context.Background(),
			[]af.Message{af.NewUserMessage("hi")},
		)

		assert.Error(t, err)
	})

	t.Run("model option overrides default model", func(t *testing.T) {
		var capturedReq gogpt.ChatCompletionRequest

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			body, _ := io.ReadAll(r.Body)
			_ = json.Unmarshal(body, &capturedReq)

			resp := gogpt.ChatCompletionResponse{
				Choices: []gogpt.ChatCompletionChoice{
					{Message: gogpt.ChatCompletionMessage{Role: "assistant", Content: "ok"}},
				},
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
		}))
		defer server.Close()

		client := openai.NewClient("test-key", "gpt-4o",
			openai.WithBaseURL(server.URL+"/v1"),
		)

		_, err := client.GetResponse(context.Background(),
			[]af.Message{af.NewUserMessage("hi")},
			af.WithModel("gpt-3.5-turbo"),
		)

		require.NoError(t, err)
		assert.Equal(t, "gpt-3.5-turbo", capturedReq.Model)
	})
}
