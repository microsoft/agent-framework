# Copyright (c) Microsoft. All rights reserved.

"""
Complex Fan-In/Fan-Out Data Processing Workflow

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
from typing import List, Optional
from enum import Enum

from agent_framework.workflow import (
    Case,
    Default,
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)


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
    async def ingest_data(self, input_request: str, ctx: WorkflowContext[DataBatch]) -> None:
        """Simulate data ingestion with realistic delays."""
        print(f"🔄 [DataIngestion] Starting data ingestion for: {input_request}")
        
        # Simulate network delay for data fetching
        await asyncio.sleep(random.uniform(2, 4))
        
        # Create a data batch based on input
        data_types = list(DataType)
        selected_type = random.choice(data_types)
        
        batch = DataBatch(
            batch_id=f"batch_{random.randint(1000, 9999)}",
            data_type=selected_type,
            size=random.randint(100, 1000),
            content=f"Processed data for: {input_request}",
            source=f"source_{selected_type.value}",
            timestamp=asyncio.get_event_loop().time()
        )
        
        print(f"✅ [DataIngestion] Ingested {batch.size} records of {batch.data_type.value} data (batch: {batch.batch_id})")
        await ctx.send_message(batch)


# Validation Stage (Fan-out)
class SchemaValidator(Executor):
    """Validates data schema and structure."""
    
    @handler
    async def validate_schema(self, batch: DataBatch, ctx: WorkflowContext[ValidationReport]) -> None:
        """Perform schema validation with processing delay."""
        print(f"🔍 [SchemaValidator] Validating schema for batch {batch.batch_id}")
        
        # Simulate schema validation processing
        processing_time = random.uniform(1, 3)
        await asyncio.sleep(processing_time)
        
        # Simulate validation results
        issues = random.randint(0, 5)
        result = ValidationResult.VALID if issues == 0 else (
            ValidationResult.WARNING if issues <= 2 else ValidationResult.ERROR
        )
        
        report = ValidationReport(
            batch_id=batch.batch_id,
            validator_id=self.id,
            result=result,
            issues_found=issues,
            processing_time=processing_time,
            details=f"Schema validation found {issues} issues in {batch.data_type.value} data"
        )
        
        print(f"📊 [SchemaValidator] Schema validation complete: {result.value} ({issues} issues)")
        await ctx.send_message(report)


class DataQualityValidator(Executor):
    """Validates data quality and completeness."""
    
    @handler
    async def validate_quality(self, batch: DataBatch, ctx: WorkflowContext[ValidationReport]) -> None:
        """Perform data quality validation."""
        print(f"🔍 [DataQualityValidator] Checking data quality for batch {batch.batch_id}")
        
        processing_time = random.uniform(1.5, 4)
        await asyncio.sleep(processing_time)
        
        issues = random.randint(0, 8)
        result = ValidationResult.VALID if issues <= 1 else (
            ValidationResult.WARNING if issues <= 4 else ValidationResult.ERROR
        )
        
        report = ValidationReport(
            batch_id=batch.batch_id,
            validator_id=self.id,
            result=result,
            issues_found=issues,
            processing_time=processing_time,
            details=f"Quality check found {issues} data quality issues"
        )
        
        print(f"📊 [DataQualityValidator] Quality validation complete: {result.value} ({issues} issues)")
        await ctx.send_message(report)


class SecurityValidator(Executor):
    """Validates data for security and compliance issues."""
    
    @handler
    async def validate_security(self, batch: DataBatch, ctx: WorkflowContext[ValidationReport]) -> None:
        """Perform security validation."""
        print(f"🔍 [SecurityValidator] Running security checks for batch {batch.batch_id}")
        
        processing_time = random.uniform(2, 5)
        await asyncio.sleep(processing_time)
        
        issues = random.randint(0, 3)
        result = ValidationResult.VALID if issues == 0 else ValidationResult.ERROR
        
        report = ValidationReport(
            batch_id=batch.batch_id,
            validator_id=self.id,
            result=result,
            issues_found=issues,
            processing_time=processing_time,
            details=f"Security scan found {issues} security issues"
        )
        
        print(f"📊 [SecurityValidator] Security validation complete: {result.value} ({issues} issues)")
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
        print(f"📋 [ValidationAggregator] Aggregating validation results for batch {batch_id}")
        
        await asyncio.sleep(1)  # Aggregation processing time
        
        total_issues = sum(report.issues_found for report in reports)
        has_errors = any(report.result == ValidationResult.ERROR for report in reports)
        
        print(f"📊 [ValidationAggregator] Total issues found: {total_issues}, Has errors: {has_errors}")
        
        if has_errors:
            print(f"❌ [ValidationAggregator] Batch {batch_id} failed validation - stopping processing")
            await ctx.add_event(WorkflowCompletedEvent(f"Batch {batch_id} failed validation with {total_issues} issues"))
            return
        
        # Retrieve original batch from shared state (set by ingestion)
        batch_data = await ctx.get_shared_state(f"batch_{batch_id}")
        if batch_data:
            print(f"✅ [ValidationAggregator] Batch {batch_id} passed validation - proceeding to transformation")
            await ctx.send_message(batch_data)
        else:
            # Fallback: create a simplified batch
            batch = DataBatch(
                batch_id=batch_id,
                data_type=DataType.ANALYTICS,
                size=500,
                content="Validated data ready for transformation"
            )
            await ctx.send_message(batch)


# Transformation Stage (Fan-out)
class DataNormalizer(Executor):
    """Normalizes and cleans data."""
    
    @handler
    async def normalize_data(self, batch: DataBatch, ctx: WorkflowContext[TransformationResult]) -> None:
        """Perform data normalization."""
        print(f"🔧 [DataNormalizer] Normalizing data for batch {batch.batch_id}")
        
        processing_time = random.uniform(2, 6)
        await asyncio.sleep(processing_time)
        
        # Simulate data size change during normalization
        processed_size = int(batch.size * random.uniform(0.8, 1.2))
        success = random.choice([True, True, True, False])  # 75% success rate
        
        result = TransformationResult(
            batch_id=batch.batch_id,
            transformer_id=self.id,
            original_size=batch.size,
            processed_size=processed_size,
            transformation_type="normalization",
            processing_time=processing_time,
            success=success
        )
        
        status = "✅" if success else "❌"
        print(f"{status} [DataNormalizer] Normalization {'completed' if success else 'failed'}: {batch.size} → {processed_size} records")
        await ctx.send_message(result)


class DataEnrichment(Executor):
    """Enriches data with additional information."""
    
    @handler
    async def enrich_data(self, batch: DataBatch, ctx: WorkflowContext[TransformationResult]) -> None:
        """Perform data enrichment."""
        print(f"🔧 [DataEnrichment] Enriching data for batch {batch.batch_id}")
        
        processing_time = random.uniform(3, 7)
        await asyncio.sleep(processing_time)
        
        processed_size = int(batch.size * random.uniform(1.1, 1.5))  # Enrichment increases data
        success = random.choice([True, True, False])  # 67% success rate
        
        result = TransformationResult(
            batch_id=batch.batch_id,
            transformer_id=self.id,
            original_size=batch.size,
            processed_size=processed_size,
            transformation_type="enrichment",
            processing_time=processing_time,
            success=success
        )
        
        status = "✅" if success else "❌"
        print(f"{status} [DataEnrichment] Enrichment {'completed' if success else 'failed'}: {batch.size} → {processed_size} records")
        await ctx.send_message(result)


class DataAggregator(Executor):
    """Aggregates and summarizes data."""
    
    @handler
    async def aggregate_data(self, batch: DataBatch, ctx: WorkflowContext[TransformationResult]) -> None:
        """Perform data aggregation."""
        print(f"🔧 [DataAggregator] Aggregating data for batch {batch.batch_id}")
        
        processing_time = random.uniform(1.5, 4)
        await asyncio.sleep(processing_time)
        
        processed_size = int(batch.size * random.uniform(0.3, 0.7))  # Aggregation reduces data
        success = random.choice([True, True, True, True, False])  # 80% success rate
        
        result = TransformationResult(
            batch_id=batch.batch_id,
            transformer_id=self.id,
            original_size=batch.size,
            processed_size=processed_size,
            transformation_type="aggregation",
            processing_time=processing_time,
            success=success
        )
        
        status = "✅" if success else "❌"
        print(f"{status} [DataAggregator] Aggregation {'completed' if success else 'failed'}: {batch.size} → {processed_size} records")
        await ctx.send_message(result)


# Quality Assurance Stage (Fan-out)
class PerformanceAssessor(Executor):
    """Assesses performance characteristics of processed data."""
    
    @handler
    async def assess_performance(self, results: List[TransformationResult], ctx: WorkflowContext[QualityAssessment]) -> None:
        """Assess performance of transformations."""
        if not results:
            return
            
        batch_id = results[0].batch_id
        print(f"⚡ [PerformanceAssessor] Assessing performance for batch {batch_id}")
        
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
            processing_time=processing_time
        )
        
        print(f"📈 [PerformanceAssessor] Performance score: {quality_score:.1f}% ({len(recommendations)} recommendations)")
        await ctx.send_message(assessment)


class AccuracyAssessor(Executor):
    """Assesses accuracy and correctness of processed data."""
    
    @handler
    async def assess_accuracy(self, results: List[TransformationResult], ctx: WorkflowContext[QualityAssessment]) -> None:
        """Assess accuracy of transformations."""
        if not results:
            return
            
        batch_id = results[0].batch_id
        print(f"🎯 [AccuracyAssessor] Assessing accuracy for batch {batch_id}")
        
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
            processing_time=processing_time
        )
        
        print(f"🎯 [AccuracyAssessor] Accuracy score: {accuracy_score:.1f}% ({len(recommendations)} recommendations)")
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
        print(f"🏁 [FinalProcessor] Generating final summary for batch {batch_id}")
        
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
        
        print(f"✅ [FinalProcessor] {completion_message}")
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
    
    test_inputs = [
        "Customer data from Q4 2024",
        "Transaction logs from payment system",
        "Product catalog with inventory data",
        "Analytics data from user behavior"
    ]
    
    for i, input_data in enumerate(test_inputs, 1):
        print(f"\n🧪 Test Run {i}: {input_data}")
        print("-" * 50)
        
        start_time = asyncio.get_event_loop().time()
        
        async for event in workflow.run_stream(input_data):
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"[{elapsed:.1f}s] {event}")
            
            if isinstance(event, WorkflowCompletedEvent):
                print(f"\n🎉 Workflow completed in {elapsed:.1f} seconds!")
                break
        
        print("\n" + "="*70)
        
        # Wait between test runs
        if i < len(test_inputs):
            print("⏳ Waiting 3 seconds before next test...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
