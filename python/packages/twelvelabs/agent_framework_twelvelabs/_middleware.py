# Copyright (c) Microsoft. All rights reserved.

"""Middleware for video upload progress and monitoring."""

import time
from typing import Any, Callable, Dict

from agent_framework._middleware import AgentMiddleware, FunctionMiddleware


class VideoUploadProgressMiddleware(AgentMiddleware):
    """Middleware to track and report video upload progress.

    This middleware intercepts video upload operations and provides
    real-time progress updates to the user.

    Example:
        ```python
        from agent_framework_twelvelabs import (
            VideoProcessingAgent,
            VideoUploadProgressMiddleware
        )

        middleware = VideoUploadProgressMiddleware(
            update_interval=2.0,  # Update every 2 seconds
            show_speed=True       # Show upload speed
        )

        agent = VideoProcessingAgent(
            middleware=[middleware]
        )
        ```

    """

    def __init__(
        self,
        update_interval: float = 1.0,
        show_speed: bool = True,
        show_eta: bool = True,
    ):
        """Initialize progress middleware.

        Args:
            update_interval: Seconds between progress updates
            show_speed: Whether to show upload speed
            show_eta: Whether to show estimated time remaining

        """
        super().__init__()
        self.update_interval = update_interval
        self.show_speed = show_speed
        self.show_eta = show_eta
        self._upload_sessions: Dict[str, Dict[str, Any]] = {}

    async def process(self, context: Any, next: Callable) -> Any:
        """Process the middleware pipeline.

        Args:
            context: Agent context containing request information
            next: Next middleware in the chain

        Returns:
            Result from the next middleware

        """
        # Check if this is a video upload operation
        if self._is_video_upload(context):
            # Wrap with progress tracking
            return await self._track_upload_progress(context, next)
        else:
            # Pass through for non-upload operations
            return await next(context)

    def _is_video_upload(self, context: Any) -> bool:
        """Check if the current operation is a video upload.

        Args:
            context: Current context

        Returns:
            True if this is a video upload operation

        """
        if not hasattr(context, "function"):
            return False

        function = context.function
        if hasattr(function, "__name__"):
            return "upload_video" in function.__name__

        # Check for function metadata
        if hasattr(function, "__wrapped__"):
            wrapped = function.__wrapped__
            if hasattr(wrapped, "__name__"):
                return "upload_video" in wrapped.__name__

        return False

    async def _track_upload_progress(self, context: Any, next: Callable) -> Any:
        """Track upload progress and provide updates.

        Args:
            context: Current context
            next: Next middleware

        Returns:
            Upload result

        """
        # Create upload session
        session_id = self._create_session()
        start_time = time.time()
        last_update = start_time

        # Create progress callback
        async def progress_callback(current_bytes: int, total_bytes: int):
            nonlocal last_update

            current_time = time.time()
            elapsed = current_time - start_time

            # Update session data
            self._upload_sessions[session_id] = {
                "current": current_bytes,
                "total": total_bytes,
                "elapsed": elapsed,
                "start_time": start_time,
            }

            # Check if we should send an update
            if current_time - last_update >= self.update_interval:
                last_update = current_time

                # Calculate metrics
                percentage = (current_bytes / total_bytes) * 100
                speed = current_bytes / elapsed if elapsed > 0 else 0
                remaining = (
                    (total_bytes - current_bytes) / speed if speed > 0 else 0
                )

                # Build progress message
                message = f"Upload progress: {percentage:.1f}%"

                if self.show_speed:
                    speed_mb = speed / (1024 * 1024)
                    message += f" ({speed_mb:.1f} MB/s)"

                if self.show_eta and remaining > 0:
                    if remaining < 60:
                        message += f" - {remaining:.0f}s remaining"
                    else:
                        minutes = remaining / 60
                        message += f" - {minutes:.1f}m remaining"

                # Send progress update
                await self._send_progress_update(context, message, percentage)

        # Inject progress callback into context
        if hasattr(context, "kwargs"):
            context.kwargs["progress_callback"] = progress_callback

        try:
            # Execute the upload
            result = await next(context)

            # Send completion message
            await self._send_progress_update(
                context, "Upload complete!", 100.0
            )

            return result

        finally:
            # Clean up session
            self._cleanup_session(session_id)

    def _create_session(self) -> str:
        """Create a new upload session.

        Returns:
            Session ID

        """
        import uuid

        session_id = str(uuid.uuid4())
        self._upload_sessions[session_id] = {
            "current": 0,
            "total": 0,
            "start_time": time.time(),
        }
        return session_id

    def _cleanup_session(self, session_id: str):
        """Clean up an upload session.

        Args:
            session_id: Session to clean up

        """
        if session_id in self._upload_sessions:
            del self._upload_sessions[session_id]

    async def _send_progress_update(
        self, context: Any, message: str, percentage: float
    ):
        """Send progress update to the user.

        Args:
            context: Current context
            message: Progress message
            percentage: Completion percentage

        """
        # Try to get agent reference for sending updates
        if hasattr(context, "agent"):
            agent = context.agent
            if hasattr(agent, "send_update"):
                await agent.send_update(
                    {
                        "type": "upload_progress",
                        "message": message,
                        "percentage": percentage,
                    }
                )
        else:
            # Fallback to print if no agent available
            print(message)


class VideoProcessingMetricsMiddleware(FunctionMiddleware):
    """Middleware to collect metrics on video processing operations.

    Tracks operation counts, processing times, and error rates.

    Example:
        ```python
        metrics = VideoProcessingMetricsMiddleware()

        agent = VideoProcessingAgent(
            middleware=[metrics]
        )

        # Later, get metrics
        stats = metrics.get_statistics()
        print(f"Total operations: {stats['total_operations']}")
        print(f"Average processing time: {stats['avg_processing_time']}")
        ```

    """

    def __init__(self):
        """Initialize metrics middleware."""
        super().__init__()
        self.metrics = {
            "operations": {},
            "errors": {},
            "total_operations": 0,
            "total_errors": 0,
            "start_time": time.time(),
        }

    async def process(self, context: Any, next: Callable) -> Any:
        """Track metrics for the operation.

        Args:
            context: Function context
            next: Next middleware

        Returns:
            Operation result

        """
        operation = self._get_operation_name(context)
        start_time = time.time()

        try:
            # Execute operation
            result = await next(context)

            # Record success
            self._record_success(operation, time.time() - start_time)

            return result

        except Exception as e:
            # Record error
            self._record_error(operation, type(e).__name__, time.time() - start_time)
            raise

    def _get_operation_name(self, context: Any) -> str:
        """Get the operation name from context.

        Args:
            context: Current context

        Returns:
            Operation name

        """
        if hasattr(context, "function"):
            function = context.function
            if hasattr(function, "__name__"):
                return function.__name__
            elif hasattr(function, "__wrapped__"):
                return function.__wrapped__.__name__
        return "unknown"

    def _record_success(self, operation: str, duration: float):
        """Record a successful operation.

        Args:
            operation: Operation name
            duration: Operation duration in seconds

        """
        if operation not in self.metrics["operations"]:
            self.metrics["operations"][operation] = {
                "count": 0,
                "total_duration": 0.0,
                "min_duration": float("inf"),
                "max_duration": 0.0,
            }

        op_metrics = self.metrics["operations"][operation]
        op_metrics["count"] += 1
        op_metrics["total_duration"] += duration
        op_metrics["min_duration"] = min(op_metrics["min_duration"], duration)
        op_metrics["max_duration"] = max(op_metrics["max_duration"], duration)

        self.metrics["total_operations"] += 1

    def _record_error(self, operation: str, error_type: str, duration: float):
        """Record an operation error.

        Args:
            operation: Operation name
            error_type: Type of error
            duration: Operation duration before error

        """
        error_key = f"{operation}:{error_type}"

        if error_key not in self.metrics["errors"]:
            self.metrics["errors"][error_key] = {
                "count": 0,
                "operation": operation,
                "error_type": error_type,
            }

        self.metrics["errors"][error_key]["count"] += 1
        self.metrics["total_errors"] += 1

        # Still record timing for failed operations
        self._record_success(operation, duration)

    def get_statistics(self) -> Dict[str, Any]:
        """Get current metrics statistics.

        Returns:
            Dictionary with metrics summary

        """
        uptime = time.time() - self.metrics["start_time"]
        stats = {
            "uptime_seconds": uptime,
            "total_operations": self.metrics["total_operations"],
            "total_errors": self.metrics["total_errors"],
            "error_rate": (
                self.metrics["total_errors"] / self.metrics["total_operations"]
                if self.metrics["total_operations"] > 0
                else 0
            ),
            "operations": {},
        }

        # Calculate per-operation statistics
        for op_name, op_data in self.metrics["operations"].items():
            count = op_data["count"]
            if count > 0:
                stats["operations"][op_name] = {
                    "count": count,
                    "avg_duration": op_data["total_duration"] / count,
                    "min_duration": op_data["min_duration"],
                    "max_duration": op_data["max_duration"],
                    "total_duration": op_data["total_duration"],
                }

        # Add error breakdown
        if self.metrics["errors"]:
            stats["errors"] = {
                error_key: error_data
                for error_key, error_data in self.metrics["errors"].items()
            }

        return stats

    def reset_metrics(self):
        """Reset all collected metrics."""
        self.metrics = {
            "operations": {},
            "errors": {},
            "total_operations": 0,
            "total_errors": 0,
            "start_time": time.time(),
        }
