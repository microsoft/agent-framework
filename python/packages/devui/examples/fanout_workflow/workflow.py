# Copyright (c) Microsoft. All rights reserved.

"""Complex Fan-In/Fan-Out Data Processing Workflow

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
import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Literal, Optional

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from pydantic import BaseModel, Field


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
    transformations: List[Literal["normalize", "enrich", "aggregate"]] = Field(
        description="List of transformations to apply", default=["normalize", "enrich"]
    )

    # Optional description
    description: Optional[str] = Field(description="Optional description of the processing request", default=None)

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
    recommendations: List[str]
    processing_time: float


@dataclass
class ProcessingSummary:
    """Summary of all processing stages."""

    batch_id: str
    total_processing_time: float
    validation_reports: List[ValidationReport]
    transformation_results: List[TransformationResult]
    quality_assessments: List[QualityAssessment]
    final_status: str


# Data Ingestion Stage
class DataIngestion(Executor):
    """Simulates ingesting data from multiple sources with delays."""

    @handler
    async def ingest_data(self, request: ProcessingRequest, ctx: WorkflowContext[DataBatch]) -> None:
        """Simulate data ingestion with realistic delays based on input configuration."""
        # Simulate network delay based on data source
        delay_map = {"database": (1, 2), "api": (2, 4), "file_upload": (3, 5), "streaming": (0.5, 1.5)}
        delay_range = delay_map.get(request.data_source, (2, 4))
        await asyncio.sleep(random.uniform(*delay_range))

        # Simulate data size based on priority and configuration
        base_size = request.batch_size
        if request.processing_priority == "critical":
            size_multiplier = random.uniform(1.5, 2.0)
        elif request.processing_priority == "high":
            size_multiplier = random.uniform(1.2, 1.5)
        elif request.processing_priority == "low":
            size_multiplier = random.uniform(0.5, 0.8)
        else:  # normal
            size_multiplier = random.uniform(0.8, 1.2)

        actual_size = int(base_size * size_multiplier)

        batch = DataBatch(
            batch_id=f"batch_{random.randint(1000, 9999)}",
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
        processing_time = random.uniform(1, 3)
        await asyncio.sleep(processing_time)

        # Simulate validation results - consider force failure flag
        if request.force_validation_failure:
            issues = random.randint(3, 5)  # Force more issues
        else:
            issues = random.randint(0, 4)

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

        processing_time = random.uniform(1.5, 4)
        await asyncio.sleep(processing_time)

        # Quality checks are stricter for higher priority data
        if request.processing_priority in ["critical", "high"]:
            issues = random.randint(0, 4)  # Fewer issues for high priority
        else:
            issues = random.randint(0, 6)

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

        processing_time = random.uniform(2, 5)
        await asyncio.sleep(processing_time)

        # Security is more stringent for customer/transaction data
        if batch.data_type in [DataType.CUSTOMER, DataType.TRANSACTION]:
            issues = random.randint(0, 2)  # Fewer issues expected for sensitive data
        else:
            issues = random.randint(0, 3)

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
    async def aggregate_validations(self, reports: List[ValidationReport], ctx: WorkflowContext[DataBatch]) -> None:
        """Aggregate all validation reports and make processing decision."""
        if not reports:
            return

        batch_id = reports[0].batch_id
        request = await ctx.get_shared_state(f"request_{batch_id}")

        await asyncio.sleep(1)  # Aggregation processing time

        total_issues = sum(report.issues_found for report in reports)
        has_errors = any(report.result == ValidationResult.ERROR for report in reports)
        warning_count = sum(1 for report in reports if report.result == ValidationResult.WARNING)

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
            await ctx.add_event(
                WorkflowCompletedEvent(
                    f"Batch {batch_id} failed validation: {reason}. "
                    f"Total issues: {total_issues}, Quality score: {quality_score:.2f}"
                )
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

        processing_time = random.uniform(2, 6)
        await asyncio.sleep(processing_time)

        # Simulate data size change during normalization
        processed_size = int(batch.size * random.uniform(0.8, 1.2))

        # Consider force failure flag
        if request.force_transformation_failure:
            success = False
        else:
            success = random.choice([True, True, True, False])  # 75% success rate

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

        processing_time = random.uniform(3, 7)
        await asyncio.sleep(processing_time)

        processed_size = int(batch.size * random.uniform(1.1, 1.5))  # Enrichment increases data

        # Consider force failure flag
        if request.force_transformation_failure:
            success = False
        else:
            success = random.choice([True, True, False])  # 67% success rate

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

        processing_time = random.uniform(1.5, 4)
        await asyncio.sleep(processing_time)

        processed_size = int(batch.size * random.uniform(0.3, 0.7))  # Aggregation reduces data

        # Consider force failure flag
        if request.force_transformation_failure:
            success = False
        else:
            success = random.choice([True, True, True, True, False])  # 80% success rate

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
        self, results: List[TransformationResult], ctx: WorkflowContext[QualityAssessment]
    ) -> None:
        """Assess performance of transformations."""
        if not results:
            return

        batch_id = results[0].batch_id

        processing_time = random.uniform(1, 3)
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
        self, results: List[TransformationResult], ctx: WorkflowContext[QualityAssessment]
    ) -> None:
        """Assess accuracy of transformations."""
        if not results:
            return

        batch_id = results[0].batch_id

        processing_time = random.uniform(2, 4)
        await asyncio.sleep(processing_time)

        # Simulate accuracy analysis
        accuracy_score = random.uniform(75, 95)

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
    async def process_final_results(self, assessments: List[QualityAssessment], ctx: WorkflowContext[None]) -> None:
        """Generate final processing summary and complete workflow."""
        if not assessments:
            await ctx.add_event(WorkflowCompletedEvent("No quality assessments received"))
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

        await ctx.add_event(WorkflowCompletedEvent(completion_message))


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
    workflow = (
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

    return workflow


# Export the workflow for DevUI discovery
workflow = create_complex_workflow()


async def main():
    """Main function to test the workflow."""
    print("🚀 Starting Complex Fan-In/Fan-Out Data Processing Workflow")
    print("=" * 70)

    # Test different scenarios with structured inputs
    test_scenarios = [
        {
            "name": "High Priority Customer Data (Success Path)",
            "request": ProcessingRequest(
                data_source="database",
                data_type="customer",
                processing_priority="high",
                batch_size=750,
                quality_threshold=0.7,
                transformations=["normalize", "enrich"],
                description="Processing customer data for monthly report",
                force_validation_failure=False,
                force_transformation_failure=False,
            ),
        },
        {
            "name": "Critical Transaction Data (All Transformations)",
            "request": ProcessingRequest(
                data_source="api",
                data_type="transaction",
                processing_priority="critical",
                batch_size=1200,
                quality_threshold=0.9,
                transformations=["normalize", "enrich", "aggregate"],
                description="Real-time transaction processing",
                enable_security_validation=True,
                force_validation_failure=False,
                force_transformation_failure=False,
            ),
        },
        {
            "name": "Low Priority Analytics (Validation Failure Test)",
            "request": ProcessingRequest(
                data_source="file_upload",
                data_type="analytics",
                processing_priority="low",
                batch_size=300,
                quality_threshold=0.8,
                transformations=["aggregate"],
                description="Analytics batch processing",
                force_validation_failure=True,  # Force failure
                force_transformation_failure=False,
            ),
        },
        {
            "name": "Streaming Product Data (Minimal Validation)",
            "request": ProcessingRequest(
                data_source="streaming",
                data_type="product",
                processing_priority="normal",
                batch_size=500,
                quality_threshold=0.6,
                transformations=["normalize"],
                description="Product catalog updates",
                enable_security_validation=False,  # Disable security check
                enable_quality_validation=False,  # Disable quality check
                force_validation_failure=False,
                force_transformation_failure=False,
            ),
        },
    ]

    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n🧪 Test Scenario {i}: {scenario['name']}")
        print("-" * 60)
        print("📋 Configuration:")
        print(f"   Source: {scenario['request'].data_source}")
        print(f"   Type: {scenario['request'].data_type}")
        print(f"   Priority: {scenario['request'].processing_priority}")
        print(f"   Batch Size: {scenario['request'].batch_size}")
        print(f"   Quality Threshold: {scenario['request'].quality_threshold}")
        print(f"   Transformations: {', '.join(scenario['request'].transformations)}")
        print(f"   Schema Validation: {scenario['request'].enable_schema_validation}")
        print(f"   Security Validation: {scenario['request'].enable_security_validation}")
        print(f"   Quality Validation: {scenario['request'].enable_quality_validation}")
        if scenario["request"].description:
            print(f"   Description: {scenario['request'].description}")
        print()

        start_time = asyncio.get_event_loop().time()

        async for event in workflow.run_stream(scenario["request"]):
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"[{elapsed:.1f}s] {event}")

            if isinstance(event, WorkflowCompletedEvent):
                print(f"\n🎉 Scenario completed in {elapsed:.1f} seconds!")
                break

        print("\n" + "=" * 70)

        # Wait between test runs
        if i < len(test_scenarios):
            print("⏳ Waiting 2 seconds before next scenario...")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
