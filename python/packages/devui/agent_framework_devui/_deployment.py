# Copyright (c) Microsoft. All rights reserved.

"""Azure Container Apps deployment manager for DevUI entities."""

import asyncio
import logging
import re
import secrets
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path

from .models._discovery_models import Deployment, DeploymentConfig, DeploymentEvent

logger = logging.getLogger(__name__)


class DeploymentManager:
    """Manages entity deployments to Azure Container Apps."""

    def __init__(self) -> None:
        """Initialize deployment manager."""
        self._deployments: dict[str, Deployment] = {}

    async def deploy(self, config: DeploymentConfig, entity_path: Path) -> AsyncGenerator[DeploymentEvent, None]:
        """Deploy entity to Azure Container Apps with streaming events.

        Args:
            config: Deployment configuration
            entity_path: Path to entity directory

        Yields:
            DeploymentEvent objects for real-time progress updates

        Raises:
            ValueError: If prerequisites not met or deployment fails
        """
        deployment_id = str(uuid.uuid4())

        try:
            # Step 1: Validate prerequisites
            yield DeploymentEvent(
                type="deploy.validating",
                message="Checking prerequisites (Azure CLI, Docker, authentication)...",
            )

            await self._validate_prerequisites()

            # Step 2: Generate Dockerfile
            yield DeploymentEvent(
                type="deploy.dockerfile",
                message="Generating Dockerfile with authentication enabled...",
            )

            _ = await self._generate_dockerfile(entity_path, config)

            # Step 3: Generate auth token
            yield DeploymentEvent(
                type="deploy.token",
                message="Generating secure authentication token...",
            )

            auth_token = secrets.token_urlsafe(32)

            # Step 4: Discover existing Container App Environment
            yield DeploymentEvent(
                type="deploy.environment",
                message="Checking for existing Container App Environment...",
            )

            # Step 5: Build and deploy with Azure CLI
            yield DeploymentEvent(
                type="deploy.building",
                message=f"Deploying to Azure Container Apps ({config.region})...",
            )

            # Create a queue for streaming events from subprocess
            event_queue: asyncio.Queue[DeploymentEvent] = asyncio.Queue()

            # Run deployment in background task with event queue
            deployment_task = asyncio.create_task(self._deploy_to_azure(config, entity_path, auth_token, event_queue))

            # Stream events from queue while deployment runs
            while True:
                try:
                    # Check if deployment task is done
                    if deployment_task.done():
                        # Get the result or exception
                        deployment_url = await deployment_task
                        break

                    # Get event from queue with short timeout
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    # No event in queue, continue waiting
                    continue

            # Step 5: Store deployment record
            deployment = Deployment(
                id=deployment_id,
                entity_id=config.entity_id,
                resource_group=config.resource_group,
                app_name=config.app_name,
                region=config.region,
                url=deployment_url,
                status="deployed",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._deployments[deployment_id] = deployment

            # Step 6: Success - return URL and token
            yield DeploymentEvent(
                type="deploy.completed",
                message=f"Deployment successful! URL: {deployment_url}",
                url=deployment_url,
                auth_token=auth_token,  # Shown once to user
            )

        except Exception as e:
            error_msg = f"Deployment failed: {e!s}"
            logger.exception(error_msg)

            # Store failed deployment
            deployment = Deployment(
                id=deployment_id,
                entity_id=config.entity_id,
                resource_group=config.resource_group,
                app_name=config.app_name,
                region=config.region,
                url="",
                status="failed",
                created_at=datetime.now(timezone.utc).isoformat(),
                error=str(e),
            )
            self._deployments[deployment_id] = deployment

            yield DeploymentEvent(
                type="deploy.failed",
                message=error_msg,
            )

    async def _validate_prerequisites(self) -> None:
        """Validate that Azure CLI, Docker, authentication, and resource providers are available.

        Raises:
            ValueError: If prerequisites not met
        """
        # Check Azure CLI
        az_check = await asyncio.create_subprocess_exec(
            "az", "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await az_check.communicate()
        if az_check.returncode != 0:
            raise ValueError(
                "Azure CLI not found. Install from: https://learn.microsoft.com/cli/azure/install-azure-cli"
            )

        # Check Docker
        docker_check = await asyncio.create_subprocess_exec(
            "docker", "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await docker_check.communicate()
        if docker_check.returncode != 0:
            raise ValueError("Docker not found. Install from: https://www.docker.com/get-started")

        # Check Azure authentication
        az_account_check = await asyncio.create_subprocess_exec(
            "az", "account", "show", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await az_account_check.communicate()
        if az_account_check.returncode != 0:
            raise ValueError("Not authenticated with Azure. Run: az login")

        # Check required resource providers are registered
        required_providers = ["Microsoft.App", "Microsoft.ContainerRegistry", "Microsoft.OperationalInsights"]
        unregistered_providers = []

        # Get list of registered providers
        provider_check = await asyncio.create_subprocess_exec(
            "az",
            "provider",
            "list",
            "--query",
            "[?registrationState=='Registered'].namespace",
            "--output",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await provider_check.communicate()

        if provider_check.returncode == 0:
            import json

            try:
                registered = json.loads(stdout.decode())
                for provider in required_providers:
                    if provider not in registered:
                        unregistered_providers.append(provider)
            except json.JSONDecodeError:
                logger.warning("Could not parse provider list, skipping provider validation")
        else:
            logger.warning("Could not check provider registration status")

        if unregistered_providers:
            commands = [f"az provider register -n {p} --wait" for p in unregistered_providers]
            raise ValueError(
                f"Required Azure resource providers not registered: {', '.join(unregistered_providers)}\n\n"
                f"Register them by running:\n" + "\n".join(commands) + "\n\n"
                "This is a one-time setup per Azure subscription."
            )

        logger.info("All prerequisites validated successfully")

    async def _generate_dockerfile(self, entity_path: Path, config: DeploymentConfig) -> Path:
        """Generate Dockerfile for entity deployment.

        Args:
            entity_path: Path to entity directory
            config: Deployment configuration

        Returns:
            Path to generated Dockerfile
        """
        # Validate ui_mode
        if config.ui_mode not in ["user", "developer"]:
            raise ValueError(f"Invalid ui_mode: {config.ui_mode}. Must be 'user' or 'developer'.")

        # Check if requirements.txt exists in the entity directory
        has_requirements = (entity_path / "requirements.txt").exists()

        requirements_section = ""
        if has_requirements:
            logger.info(f"Found requirements.txt in {entity_path}, will include in Dockerfile")
            requirements_section = """# Install entity dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt
"""
        else:
            logger.info(f"No requirements.txt found in {entity_path}, skipping dependency installation")

        dockerfile_content = f"""FROM python:3.11-slim
WORKDIR /app

{requirements_section}# Install DevUI from PyPI
RUN pip install agent-framework-devui --pre

# Copy entity code
COPY . /app/entity/

ENV PORT=8080
EXPOSE 8080

# Launch DevUI with auth enabled (token from environment variable)
CMD ["devui", "/app/entity", "--mode", "{config.ui_mode}", "--host", "0.0.0.0", "--port", "8080", "--auth"]
"""

        dockerfile_path = entity_path / "Dockerfile"

        # Warn if Dockerfile already exists
        if dockerfile_path.exists():
            logger.warning(f"Dockerfile already exists at {dockerfile_path}, overwriting...")

        dockerfile_path.write_text(dockerfile_content)
        logger.info(f"Generated Dockerfile at {dockerfile_path}")

        return dockerfile_path

    async def _discover_container_app_environment(self, resource_group: str, region: str) -> str | None:
        """Discover existing Container App Environment in resource group.

        Args:
            resource_group: Resource group name
            region: Azure region (for filtering if needed)

        Returns:
            Environment name if found, None otherwise
        """
        cmd = [
            "az",
            "containerapp",
            "env",
            "list",
            "--resource-group",
            resource_group,
            "--query",
            "[0].name",
            "--output",
            "tsv",
        ]

        logger.info(f"Discovering existing Container App Environments in {resource_group}...")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            env_name = stdout.decode().strip()
            if env_name:
                logger.info(f"Found existing environment: {env_name}")
                return env_name
            logger.info("No existing environments found in resource group")
            return None
        logger.warning(f"Failed to query environments: {stderr.decode()}")
        return None

    async def _deploy_to_azure(
        self, config: DeploymentConfig, entity_path: Path, auth_token: str, event_queue: asyncio.Queue[DeploymentEvent]
    ) -> str:
        """Deploy to Azure Container Apps, reusing existing environments.

        Args:
            config: Deployment configuration
            entity_path: Path to entity directory
            auth_token: Authentication token to inject
            event_queue: Queue for streaming progress events

        Returns:
            Deployment URL

        Raises:
            ValueError: If deployment fails
        """
        # Step 1: Try to discover existing Container App Environment
        existing_env = await self._discover_container_app_environment(config.resource_group, config.region)

        if existing_env:
            # Use existing environment - avoids needing environment creation permissions
            logger.info(f"Reusing existing Container App Environment: {existing_env} (cost efficient, no side effects)")
            cmd = [
                "az",
                "containerapp",
                "up",
                "--name",
                config.app_name,
                "--resource-group",
                config.resource_group,
                "--environment",
                existing_env,
                "--source",
                str(entity_path),
                "--env-vars",
                f"DEVUI_AUTH_TOKEN={auth_token}",
                "--ingress",
                "external",
                "--target-port",
                "8080",
            ]
            logger.info(f"Creating new Container App '{config.app_name}' in environment '{existing_env}'...")
        else:
            # No existing environment - try to create one (may fail if no permissions)
            logger.warning(
                "No existing Container App Environment found. "
                "Attempting to create new environment (requires Microsoft.App/managedEnvironments/write permission)..."
            )
            cmd = [
                "az",
                "containerapp",
                "up",
                "--name",
                config.app_name,
                "--resource-group",
                config.resource_group,
                "--location",
                config.region,
                "--source",
                str(entity_path),
                "--env-vars",
                f"DEVUI_AUTH_TOKEN={auth_token}",
                "--ingress",
                "external",
                "--target-port",
                "8080",
            ]

        logger.info(f"Running: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )

        # Stream output line by line
        output_lines = []
        try:
            if not process.stdout:
                raise ValueError("Failed to capture process output")

            while True:
                # Read with timeout
                line = await asyncio.wait_for(process.stdout.readline(), timeout=600)
                if not line:
                    break

                line_text = line.decode().strip()
                if line_text:
                    output_lines.append(line_text)

                    # Stream meaningful updates to user
                    if "WARNING:" in line_text:
                        # Parse and send user-friendly warnings
                        if "Creating resource group" in line_text:
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress",
                                    message=f"Creating resource group '{config.resource_group}'...",
                                )
                            )
                        elif "Creating ContainerAppEnvironment" in line_text:
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress",
                                    message="Setting up Container App Environment (this may take 2-3 minutes)...",
                                )
                            )
                        elif "Registering resource provider" in line_text:
                            provider = line_text.split("provider")[-1].strip()
                            if provider.endswith("..."):
                                provider = provider[:-3]
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress", message=f"Registering Azure provider{provider}..."
                                )
                            )
                        elif "Creating Azure Container Registry" in line_text:
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress", message="Creating Container Registry for your images..."
                                )
                            )
                        elif "No Log Analytics workspace" in line_text:
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress", message="Creating Log Analytics workspace for monitoring..."
                                )
                            )
                        elif "Building image" in line_text:
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress",
                                    message="Building Docker image (this may take several minutes)...",
                                )
                            )
                        elif "Pushing image" in line_text:
                            await event_queue.put(
                                DeploymentEvent(
                                    type="deploy.progress", message="Pushing image to Azure Container Registry..."
                                )
                            )
                        elif "Creating Container App" in line_text:
                            await event_queue.put(
                                DeploymentEvent(type="deploy.progress", message="Creating your Container App...")
                            )
                        elif "Container app created" in line_text:
                            await event_queue.put(
                                DeploymentEvent(type="deploy.progress", message="Container app created successfully!")
                            )
                    elif "ERROR:" in line_text:
                        # Stream errors immediately
                        await event_queue.put(DeploymentEvent(type="deploy.error", message=line_text))
                    elif "Step" in line_text and "/" in line_text:
                        # Docker build steps
                        await event_queue.put(
                            DeploymentEvent(type="deploy.progress", message=f"Docker build: {line_text}")
                        )
                    elif "https://" in line_text and ".azurecontainerapps.io" in line_text:
                        # Deployment URL detected
                        await event_queue.put(
                            DeploymentEvent(type="deploy.progress", message="Deployment URL generated!")
                        )

            # Wait for process to complete
            return_code = await process.wait()

            if return_code != 0:
                error_output = "\n".join(output_lines[-10:])  # Last 10 lines for context
                raise ValueError(f"Azure deployment failed:\n{error_output}")

        except asyncio.TimeoutError as e:
            process.kill()
            raise ValueError(
                "Azure deployment timed out after 10 minutes. Please check Azure portal for status."
            ) from e

        # Parse output to extract FQDN
        output = "\n".join(output_lines)
        logger.debug(f"Azure CLI output: {output}")

        # Extract FQDN from output (az containerapp up returns it)
        # Format: https://<app-name>.<random-id>.<region>.azurecontainerapps.io
        deployment_url = self._extract_fqdn_from_output(output, config.app_name)

        logger.info(f"Deployment successful: {deployment_url}")
        return deployment_url

    def _extract_fqdn_from_output(self, output: str, app_name: str) -> str:
        """Extract FQDN from Azure CLI output.

        Args:
            output: Azure CLI command output
            app_name: Container app name

        Returns:
            Full HTTPS URL to deployed app
        """
        # Try to find FQDN in output
        for line in output.split("\n"):
            if "fqdn" in line.lower() or app_name in line:
                # Extract URL-like string
                match = re.search(r"https?://[\w\-\.]+\.azurecontainerapps\.io", line)
                if match:
                    return match.group(0)

        # If we can't extract FQDN, fail explicitly rather than return a broken URL
        logger.error(f"Could not extract FQDN from Azure CLI output. Output:\n{output}")
        raise ValueError(
            "Could not extract deployment URL from Azure CLI output. "
            "The deployment may have succeeded - check the Azure portal for your container app URL."
        )

    async def list_deployments(self, entity_id: str | None = None) -> list[Deployment]:
        """List all deployments, optionally filtered by entity.

        Args:
            entity_id: Optional entity ID to filter by

        Returns:
            List of deployment records
        """
        if entity_id:
            return [d for d in self._deployments.values() if d.entity_id == entity_id]
        return list(self._deployments.values())

    async def get_deployment(self, deployment_id: str) -> Deployment | None:
        """Get deployment by ID.

        Args:
            deployment_id: Deployment ID

        Returns:
            Deployment record or None if not found
        """
        return self._deployments.get(deployment_id)

    async def delete_deployment(self, deployment_id: str) -> None:
        """Delete deployment from Azure Container Apps.

        Args:
            deployment_id: Deployment ID to delete

        Raises:
            ValueError: If deployment not found or deletion fails
        """
        deployment = self._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        # Execute: az containerapp delete
        cmd = [
            "az",
            "containerapp",
            "delete",
            "--name",
            deployment.app_name,
            "--resource-group",
            deployment.resource_group,
            "--yes",  # Skip confirmation
        ]

        logger.info(f"Deleting deployment: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode() if stderr else stdout.decode()
            raise ValueError(f"Deployment deletion failed: {error_output}")

        # Remove from store
        del self._deployments[deployment_id]
        logger.info(f"Deployment {deployment_id} deleted successfully")
