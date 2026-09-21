# .NET 10 runtime is required by the `powerfx` package, which
# agent-framework-declarative uses to evaluate `=...` expressions in the
# workflow YAML (e.g. =Local.Triage.NeedsClarification). Without it,
# ConditionGroup evaluation raises and the workflow produces no output.
FROM mcr.microsoft.com/dotnet/runtime:10.0 AS dotnet

FROM python:3.12-slim

WORKDIR /app

# libicu is required by the .NET runtime for globalization support.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the pinned .NET runtime from the official image.
COPY --from=dotnet /usr/share/dotnet /usr/share/dotnet
RUN ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet

ENV DOTNET_ROOT=/usr/share/dotnet

COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
