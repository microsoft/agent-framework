# Dockerfile for the ClawAgent.Hosted Foundry Hosted Agent, built from the agent-framework repo source.
#
# This project uses ProjectReference to local repo sources (ClawAgent, Microsoft.Agents.AI.Foundry,
# Microsoft.Agents.AI.Foundry.Hosting, Microsoft.Agents.AI.LocalCodeAct) and to the repo's Central
# Package Management, so a standard in-container `dotnet restore`/`publish` cannot resolve everything
# from this folder alone. Instead, PRE-PUBLISH the app on your machine (inside the full repo, where the
# references and package versions resolve) and COPY the output into the image:
#
#   # 1. Build and publish separately, targeting the container runtime (glibc x64):
#   dotnet publish -c Release -f net10.0 -r linux-x64 --self-contained false -o out
#
#   # 2. Then build the image from the pre-published output:
#   docker build -t personal-finance-claw .
#
#   # 3. (Optional) run it locally:
#   docker run --rm -p 8088:8088 --env-file .env personal-finance-claw
#
# `azd deploy` performs step 2 for you (building remotely in Azure Container Registry) — but you must
# still run step 1 (publish to ./out) first. See README.md.
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app

# LocalCodeAct spawns Python to run and validate model-generated code, so the image needs python3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY out/ .
EXPOSE 8088
ENV ASPNETCORE_URLS=http://+:8088
ENV LOCAL_CODEACT_PYTHON=python3
# The container is non-interactive: never block on a console prompt for a missing setting.
ENV AF_DEMO_NONINTERACTIVE=1
ENTRYPOINT ["dotnet", "ClawAgent.Hosted.dll"]
