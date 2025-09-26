# Copyright (c) Microsoft. All rights reserved.

"""Complex Fan-In/Fan-Out Data Processing Workflow.

This workflow demonstrates a sophisticated data processing pipeline with multiple stages:
1. Data Ingestion - Simulates loading data from multiple sources
2. Data Validation - Multiple validators run in parallel to check data quality
3. Data Transformation - Fan-out to different transformation processors
4. Quality Assurance - Multiple QA checks run in parallel
5. Data Aggregation - Fan-in to combine processed results
6. Final Processing - Generate reports and complete workflow

The workflow includes realistic delays to simulate actual processing time and
shows complex fan-in/fan-out patterns with conditional processing.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from pydantic import BaseModel, Field
from typing_extensions import Never


class DataType(Enum):
    """Types of data being processed."""

    CUSTOMER = "customer"
    TRANSACTION = "transaction"
    PRODUCT = "product"
    ANALYTICS = "analytics"


class ValidationResult(Enum):
    """Results of data validation."""

    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


class ProcessingRequest(BaseModel):
    """Complex input structure for data processing workflow."""

    # Basic information
    data_source: Literal["database", "api", "file_upload", "streaming"] = Field(
        description="The source of the data to be processed", default="database"
    )

    data_type: Literal["customer", "transaction", "product", "analytics"] = Field(
        description="Type of data being processed", default="customer"
    )

    processing_priority: Literal["low", "normal", "high", "critical"] = Field(
        description="Processing priority level", default="normal"
    )

    # Processing configuration
    batch_size: int = Field(description="Number of records to process in each batch", default=500, ge=100, le=10000)

    quality_threshold: float = Field(
        description="Minimum quality score required (0.0-1.0)", default=0.8, ge=0.0, le=1.0
    )

    # Validation settings
    enable_schema_validation: bool = Field(description="Enable schema validation checks", default=True)

    enable_security_validation: bool = Field(description="Enable security validation checks", default=True)

    enable_quality_validation: bool = Field(description="Enable data quality validation checks", default=True)

    # Transformation options
    transformations: list[Literal["normalize", "enrich", "aggregate"]] = Field(
        description="List of transformations to apply", default=["normalize", "enrich"]
    )

    # Optional description
    description: str | None = Field(description="Optional description of the processing request", default=None)

    # Test failure scenarios
    force_validation_failure: bool = Field(
        description="Force validation failure for testing (demo purposes)", default=False
    )

    force_transformation_failure: bool = Field(
        description="Force transformation failure for testing (demo purposes)", default=False
    )


@dataclass
class DataBatch:
    """Represents a batch of data being processed."""

    batch_id: str
    data_type: DataType
    size: int
    content: str
    source: str = "unknown"
    timestamp: float = 0.0


@dataclass
class ValidationReport:
    """Report from data validation."""

    batch_id: str
    validator_id: str
    result: ValidationResult
    issues_found: int
    processing_time: float
    details: str


@dataclass
class TransformationResult:
    """Result from data transformation."""

    batch_id: str
    transformer_id: str
    original_size: int
    processed_size: int
    transformation_type: str
    processing_time: float
    success: bool


@dataclass
class QualityAssessment:
    """Quality assessment result."""

    batch_id: str
    assessor_id: str
    quality_score: float
    recommendations: list[str]
    processing_time: float


@dataclass
class ProcessingSummary:
    """Summary of all processing stages."""

    batch_id: str
    total_processing_time: float
    validation_reports: list[ValidationReport]
    transformation_results: list[TransformationResult]
    quality_assessments: list[QualityAssessment]
    final_status: str


# Data Ingestion Stage
class DataIngestion(Executor):
    """Simulates ingesting data from multiple sources with delays."""

    @handler
    async def ingest_data(self, request: ProcessingRequest, ctx: WorkflowContext[DataBatch]) -> None:
        """Simulate data ingestion with realistic delays based on input configuration."""
        # Simulate network delay based on data source
        delay_map = {"database": 1.5, "api": 3.0, "file_upload": 4.0, "streaming": 1.0}
        delay = delay_map.get(request.data_source, 3.0)
        await asyncio.sleep(delay)  # Fixed delay for demo

        # Simulate data size based on priority and configuration
        base_size = request.batch_size
        if request.processing_priority == "critical":
            size_multiplier = 1.7  # Critical priority gets the largest batches
        elif request.processing_priority == "high":
            size_multiplier = 1.3  # High priority gets larger batches
        elif request.processing_priority == "low":
            size_multiplier = 0.6  # Low priority gets smaller batches
        else:  # normal
            size_multiplier = 1.0  # Normal priority uses base size

        actual_size = int(base_size * size_multiplier)

        batch = DataBatch(
            batch_id=f"batch_{5555}",  # Fixed batch ID for demo
            data_type=DataType(request.data_type),
            size=actual_size,
            content=f"Processing {request.data_type} data from {request.data_source}",
            source=request.data_source,
            timestamp=asyncio.get_event_loop().time(),
        )

        # Store both batch data and original request in shared state
        await ctx.set_shared_state(f"batch_{batch.batch_id}", batch)
        await ctx.set_shared_state(f"request_{batch.batch_id}", request)

        await ctx.send_message(batch)


# Validation Stage (Fan-out)
class SchemaValidator(Executor):
    """Validates data schema and structure."""

    @handler
    async def validate_schema(self, batch: DataBatch, ctx: WorkflowContext[ValidationReport]) -> None:
        """Perform schema validation with processing delay."""
        # Check if schema validation is enabled
        request = await ctx.get_shared_state(f"request_{batch.batch_id}")
        if not request or not request.enable_schema_validation:
            return

        # Simulate schema validation processing
        processing_time = 2.0  # Fixed processing time
        await asyncio.sleep(processing_time)

        # Simulate validation results - consider force failure flag
        issues = 4 if request.force_validation_failure else 2  # Fixed issue counts

        result = (
            ValidationResult.VALID
            if issues <= 1
            else (ValidationResult.WARNING if issues <= 2 else ValidationResult.ERROR)
        )

        report = ValidationReport(
            batch_id=batch.batch_id,
            validator_id=self.id,
            result=result,
            issues_found=issues,
            processing_time=processing_time,
            details=f"Schema validation found {issues} issues in {batch.data_type.value} data from {batch.source}",
        )

        await ctx.send_message(report)


class DataQualityValidator(Executor):
    """Validates data quality and completeness."""

    @handler
    async def validate_quality(self, batch: DataBatch, ctx: WorkflowContext[ValidationReport]) -> None:
        """Perform data quality validation."""
        # Check if quality validation is enabled
        request = await ctx.get_shared_state(f"request_{batch.batch_id}")
        if not request or not request.enable_quality_validation:
            return

        processing_time = 2.5  # Fixed processing time
        await asyncio.sleep(processing_time)

        # Quality checks are stricter for higher priority data
        issues = (
            2  # Fixed issue count for high priority
            if request.processing_priority in ["critical", "high"]
            else 3  # Fixed issue count for normal priority
        )

        if request.force_validation_failure:
            issues = max(issues, 4)  # Ensure failure

        result = (
            ValidationResult.VALID
            if issues <= 1
            else (ValidationResult.WARNING if issues <= 3 else ValidationResult.ERROR)
        )

        report = ValidationReport(
            batch_id=batch.batch_id,
            validator_id=self.id,
            result=result,
            issues_found=issues,
            processing_time=processing_time,
            details=f"Quality check found {issues} data quality issues (priority: {request.processing_priority})",
        )

        await ctx.send_message(report)


class SecurityValidator(Executor):
    """Validates data for security and compliance issues."""

    @handler
    async def validate_security(self, batch: DataBatch, ctx: WorkflowContext[ValidationReport]) -> None:
        """Perform security validation."""
        # Check if security validation is enabled
        request = await ctx.get_shared_state(f"request_{batch.batch_id}")
        if not request or not request.enable_security_validation:
            return

        processing_time = 3.0  # Fixed processing time
        await asyncio.sleep(processing_time)

        # Security is more stringent for customer/transaction data
        issues = 1 if batch.data_type in [DataType.CUSTOMER, DataType.TRANSACTION] else 2

        if request.force_validation_failure:
            issues = max(issues, 1)  # Force at least one security issue

        # Security errors are more serious - less tolerance
        result = ValidationResult.VALID if issues == 0 else ValidationResult.ERROR

        report = ValidationReport(
            batch_id=batch.batch_id,
            validator_id=self.id,
            result=result,
            issues_found=issues,
            processing_time=processing_time,
            details=f"Security scan found {issues} security issues in {batch.data_type.value} data",
        )

        await ctx.send_message(report)


# Validation Aggregator (Fan-in)
class ValidationAggregator(Executor):
    """Aggregates validation results and decides on next steps."""

    @handler
    async def aggregate_validations(
        self, reports: list[ValidationReport], ctx: WorkflowContext[DataBatch, str]
    ) -> None:
        """Aggregate all validation reports and make processing decision."""
        if not reports:
            return

        batch_id = reports[0].batch_id
        request = await ctx.get_shared_state(f"request_{batch_id}")

        await asyncio.sleep(1)  # Aggregation processing time

        total_issues = sum(report.issues_found for report in reports)
        has_errors = any(report.result == ValidationResult.ERROR for report in reports)

        # Calculate quality score (0.0 to 1.0)
        max_possible_issues = len(reports) * 5  # Assume max 5 issues per validator
        quality_score = max(0.0, 1.0 - (total_issues / max_possible_issues))

        # Decision logic: fail if errors OR quality below threshold
        should_fail = has_errors or (quality_score < request.quality_threshold)

        if should_fail:
            failure_reason = []
            if has_errors:
                failure_reason.append("validation errors detected")
            if quality_score < request.quality_threshold:
                failure_reason.append(
                    f"quality score {quality_score:.2f} below threshold {request.quality_threshold:.2f}"
                )

            reason = " and ".join(failure_reason)
            await ctx.yield_output(
                f"Batch {batch_id} failed validation: {reason}. "
                f"Total issues: {total_issues}, Quality score: {quality_score:.2f}"
            )
            return

        # Retrieve original batch from shared state
        batch_data = await ctx.get_shared_state(f"batch_{batch_id}")
        if batch_data:
            await ctx.send_message(batch_data)
        else:
            # Fallback: create a simplified batch
            batch = DataBatch(
                batch_id=batch_id,
                data_type=DataType.ANALYTICS,
                size=500,
                content="Validated data ready for transformation",
            )
            await ctx.send_message(batch)


# Transformation Stage (Fan-out)
class DataNormalizer(Executor):
    """Normalizes and cleans data."""

    @handler
    async def normalize_data(self, batch: DataBatch, ctx: WorkflowContext[TransformationResult]) -> None:
        """Perform data normalization."""
        request = await ctx.get_shared_state(f"request_{batch.batch_id}")

        # Check if normalization is enabled
        if not request or "normalize" not in request.transformations:
            # Send a "skipped" result
            result = TransformationResult(
                batch_id=batch.batch_id,
                transformer_id=self.id,
                original_size=batch.size,
                processed_size=batch.size,
                transformation_type="normalization",
                processing_time=0.1,
                success=True,  # Consider skipped as successful
            )
            await ctx.send_message(result)
            return

        processing_time = 4.0  # Fixed processing time
        await asyncio.sleep(processing_time)

        # Simulate data size change during normalization
        processed_size = int(batch.size * 1.0)  # No size change for demo

        # Consider force failure flag
        success = not request.force_transformation_failure  # 75% success rate simplified to always success

        result = TransformationResult(
            batch_id=batch.batch_id,
            transformer_id=self.id,
            original_size=batch.size,
            processed_size=processed_size,
            transformation_type="normalization",
            processing_time=processing_time,
            success=success,
        )

        await ctx.send_message(result)


class DataEnrichment(Executor):
    """Enriches data with additional information."""

    @handler
    async def enrich_data(self, batch: DataBatch, ctx: WorkflowContext[TransformationResult]) -> None:
        """Perform data enrichment."""
        request = await ctx.get_shared_state(f"request_{batch.batch_id}")

        # Check if enrichment is enabled
        if not request or "enrich" not in request.transformations:
            # Send a "skipped" result
            result = TransformationResult(
                batch_id=batch.batch_id,
                transformer_id=self.id,
                original_size=batch.size,
                processed_size=batch.size,
                transformation_type="enrichment",
                processing_time=0.1,
                success=True,  # Consider skipped as successful
            )
            await ctx.send_message(result)
            return

        processing_time = 5.0  # Fixed processing time
        await asyncio.sleep(processing_time)

        processed_size = int(batch.size * 1.3)  # Enrichment increases data

        # Consider force failure flag
        success = not request.force_transformation_failure  # 67% success rate simplified to always success

        result = TransformationResult(
            batch_id=batch.batch_id,
            transformer_id=self.id,
            original_size=batch.size,
            processed_size=processed_size,
            transformation_type="enrichment",
            processing_time=processing_time,
            success=success,
        )

        await ctx.send_message(result)


class DataAggregator(Executor):
    """Aggregates and summarizes data."""

    @handler
    async def aggregate_data(self, batch: DataBatch, ctx: WorkflowContext[TransformationResult]) -> None:
        """Perform data aggregation."""
        request = await ctx.get_shared_state(f"request_{batch.batch_id}")

        # Check if aggregation is enabled
        if not request or "aggregate" not in request.transformations:
            # Send a "skipped" result
            result = TransformationResult(
                batch_id=batch.batch_id,
                transformer_id=self.id,
                original_size=batch.size,
                processed_size=batch.size,
                transformation_type="aggregation",
                processing_time=0.1,
                success=True,  # Consider skipped as successful
            )
            await ctx.send_message(result)
            return

        processing_time = 2.5  # Fixed processing time
        await asyncio.sleep(processing_time)

        processed_size = int(batch.size * 0.5)  # Aggregation reduces data

        # Consider force failure flag
        success = not request.force_transformation_failure  # 80% success rate simplified to always success

        result = TransformationResult(
            batch_id=batch.batch_id,
            transformer_id=self.id,
            original_size=batch.size,
            processed_size=processed_size,
            transformation_type="aggregation",
            processing_time=processing_time,
            success=success,
        )

        await ctx.send_message(result)


# Quality Assurance Stage (Fan-out)
class PerformanceAssessor(Executor):
    """Assesses performance characteristics of processed data."""

    @handler
    async def assess_performance(
        self, results: list[TransformationResult], ctx: WorkflowContext[QualityAssessment]
    ) -> None:
        """Assess performance of transformations."""
        if not results:
            return

        batch_id = results[0].batch_id

        processing_time = 2.0  # Fixed processing time
        await asyncio.sleep(processing_time)

        avg_processing_time = sum(r.processing_time for r in results) / len(results)
        success_rate = sum(1 for r in results if r.success) / len(results)

        quality_score = (success_rate * 0.7 + (1 - min(avg_processing_time / 10, 1)) * 0.3) * 100

        recommendations = []
        if success_rate < 0.8:
            recommendations.append("Consider improving transformation reliability")
        if avg_processing_time > 5:
            recommendations.append("Optimize processing performance")
        if quality_score < 70:
            recommendations.append("Review overall data pipeline efficiency")

        assessment = QualityAssessment(
            batch_id=batch_id,
            assessor_id=self.id,
            quality_score=quality_score,
            recommendations=recommendations,
            processing_time=processing_time,
        )

        await ctx.send_message(assessment)


class AccuracyAssessor(Executor):
    """Assesses accuracy and correctness of processed data."""

    @handler
    async def assess_accuracy(
        self, results: list[TransformationResult], ctx: WorkflowContext[QualityAssessment]
    ) -> None:
        """Assess accuracy of transformations."""
        if not results:
            return

        batch_id = results[0].batch_id

        processing_time = 3.0  # Fixed processing time
        await asyncio.sleep(processing_time)

        # Simulate accuracy analysis
        accuracy_score = 85.0  # Fixed accuracy score

        recommendations = []
        if accuracy_score < 85:
            recommendations.append("Review data transformation algorithms")
        if accuracy_score < 80:
            recommendations.append("Implement additional validation steps")

        assessment = QualityAssessment(
            batch_id=batch_id,
            assessor_id=self.id,
            quality_score=accuracy_score,
            recommendations=recommendations,
            processing_time=processing_time,
        )

        await ctx.send_message(assessment)


# Final Processing and Completion
class FinalProcessor(Executor):
    """Final processing stage that combines all results."""

    @handler
    async def process_final_results(
        self, assessments: list[QualityAssessment], ctx: WorkflowContext[Never, str]
    ) -> None:
        """Generate final processing summary and complete workflow."""
        if not assessments:
            await ctx.yield_output("No quality assessments received")
            return

        batch_id = assessments[0].batch_id

        # Simulate final processing delay
        await asyncio.sleep(2)

        # Calculate overall metrics
        avg_quality_score = sum(a.quality_score for a in assessments) / len(assessments)
        total_recommendations = sum(len(a.recommendations) for a in assessments)
        total_processing_time = sum(a.processing_time for a in assessments)

        # Determine final status
        if avg_quality_score >= 85:
            final_status = "EXCELLENT"
        elif avg_quality_score >= 75:
            final_status = "GOOD"
        elif avg_quality_score >= 65:
            final_status = "ACCEPTABLE"
        else:
            final_status = "NEEDS_IMPROVEMENT"

        completion_message = (
            f"Batch {batch_id} processing completed!\n"
            f"📊 Overall Quality Score: {avg_quality_score:.1f}%\n"
            f"⏱️  Total Processing Time: {total_processing_time:.1f}s\n"
            f"💡 Total Recommendations: {total_recommendations}\n"
            f"🎖️  Final Status: {final_status}"
        )

        await ctx.yield_output(completion_message)


# Workflow Builder Helper
class WorkflowSetupHelper:
    """Helper class to set up the complex workflow with shared state management."""

    @staticmethod
    async def store_batch_data(batch: DataBatch, ctx: WorkflowContext) -> None:
        """Store batch data in shared state for later retrieval."""
        await ctx.set_shared_state(f"batch_{batch.batch_id}", batch)


# Create the workflow instance
def create_complex_workflow():
    """Create the complex fan-in/fan-out workflow."""
    # Create all executors
    data_ingestion = DataIngestion(id="data_ingestion")

    # Validation stage (fan-out)
    schema_validator = SchemaValidator(id="schema_validator")
    quality_validator = DataQualityValidator(id="quality_validator")
    security_validator = SecurityValidator(id="security_validator")
    validation_aggregator = ValidationAggregator(id="validation_aggregator")

    # Transformation stage (fan-out)
    data_normalizer = DataNormalizer(id="data_normalizer")
    data_enrichment = DataEnrichment(id="data_enrichment")
    data_aggregator_exec = DataAggregator(id="data_aggregator")

    # Quality assurance stage (fan-out)
    performance_assessor = PerformanceAssessor(id="performance_assessor")
    accuracy_assessor = AccuracyAssessor(id="accuracy_assessor")

    # Final processing
    final_processor = FinalProcessor(id="final_processor")

    # Build the workflow with complex fan-in/fan-out patterns
    return (
        WorkflowBuilder()
        .set_start_executor(data_ingestion)
        # Fan-out to validation stage
        .add_fan_out_edges(data_ingestion, [schema_validator, quality_validator, security_validator])
        # Fan-in from validation to aggregator
        .add_fan_in_edges([schema_validator, quality_validator, security_validator], validation_aggregator)
        # Fan-out to transformation stage
        .add_fan_out_edges(validation_aggregator, [data_normalizer, data_enrichment, data_aggregator_exec])
        # Fan-in to quality assurance stage (both assessors receive all transformation results)
        .add_fan_in_edges([data_normalizer, data_enrichment, data_aggregator_exec], performance_assessor)
        .add_fan_in_edges([data_normalizer, data_enrichment, data_aggregator_exec], accuracy_assessor)
        # Fan-in to final processor
        .add_fan_in_edges([performance_assessor, accuracy_assessor], final_processor)
        .build()
    )


# Export the workflow for DevUI discovery
workflow = create_complex_workflow()


def main():
    """Launch the fanout workflow in DevUI."""
    from agent_framework.devui import serve

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting Complex Fan-In/Fan-Out Data Processing Workflow")
    logger.info("Available at: http://localhost:8090")
    logger.info("Entity ID: workflow_complex_workflow")

    # Launch server with the workflow
    serve(entities=[workflow], port=8090, auto_open=True)


if __name__ == "__main__":
    main()
