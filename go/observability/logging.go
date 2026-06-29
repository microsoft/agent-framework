package observability

import (
	"context"
	"log/slog"
	"time"

	af "github.com/microsoft/agent-framework/go"
)

func NewLoggingAgentMiddleware(logger *slog.Logger) af.AgentMiddleware {
	return af.AgentMiddlewareFunc(func(ctx context.Context, ac *af.AgentContext, next af.AgentHandler) error {
		start := time.Now()
		agentName := ac.Agent.Name()
		msgCount := len(ac.Messages)

		logger.InfoContext(ctx, "agent run started",
			slog.String("agent.name", agentName),
			slog.Int("message.count", msgCount),
		)

		err := next(ctx, ac)
		elapsed := time.Since(start)

		if err != nil {
			logger.ErrorContext(ctx, "agent run failed",
				slog.String("agent.name", agentName),
				slog.Duration("duration", elapsed),
				slog.String("error", err.Error()),
			)
			return err
		}

		attrs := []slog.Attr{
			slog.String("agent.name", agentName),
			slog.Duration("duration", elapsed),
		}
		if ac.Response != nil && ac.Response.Usage != nil {
			attrs = append(attrs,
				slog.Int("usage.input_tokens", ac.Response.Usage.InputTokens),
				slog.Int("usage.output_tokens", ac.Response.Usage.OutputTokens),
			)
		}
		logger.LogAttrs(ctx, slog.LevelInfo, "agent run completed", attrs...)

		return nil
	})
}
