# Complex Fan-In/Fan-Out Data Processing Workflow

This workflow demonstrates a sophisticated multi-stage data processing pipeline with realistic delays and complex fan-in/fan-out patterns.

## Workflow Architecture

```
Input Request
     ↓
Data Ingestion
     ↓
[Fan-Out] → Schema Validator
          → Quality Validator
          → Security Validator
     ↓
[Fan-In] → Validation Aggregator
     ↓
[Fan-Out] → Data Normalizer
          → Data Enrichment
          → Data Aggregator
     ↓
[Fan-In] → Performance Assessor
         → Accuracy Assessor
     ↓
[Fan-In] → Final Processor
     ↓
Completion Event
```

## Processing Stages

### 1. Data Ingestion

- **Executor**: `DataIngestion`
- **Purpose**: Simulates loading data from various sources
- **Delay**: 2-4 seconds (network/IO simulation)
- **Output**: `DataBatch` object with metadata

### 2. Validation Stage (Fan-Out)

Three validators run in parallel:

- **Schema Validator**: Validates data structure (1-3s delay)
- **Quality Validator**: Checks data completeness (1.5-4s delay)
- **Security Validator**: Scans for security issues (2-5s delay)

### 3. Validation Aggregation (Fan-In)

- **Executor**: `ValidationAggregator`
- **Purpose**: Combines validation results and decides whether to proceed
- **Logic**: Stops processing if any validator finds errors
- **Delay**: 1 second aggregation time

### 4. Transformation Stage (Fan-Out)

Three transformers run in parallel:

- **Data Normalizer**: Cleans and normalizes data (2-6s delay)
- **Data Enrichment**: Adds additional information (3-7s delay)
- **Data Aggregator**: Summarizes data (1.5-4s delay)

Each transformer has a configurable success rate to simulate real-world failures.

### 5. Quality Assurance Stage (Fan-Out)

Two assessors run in parallel, both receiving all transformation results:

- **Performance Assessor**: Evaluates processing performance (1-3s delay)
- **Accuracy Assessor**: Assesses data accuracy (2-4s delay)

### 6. Final Processing (Fan-In)

- **Executor**: `FinalProcessor`
- **Purpose**: Generates comprehensive summary and completion report
- **Delay**: 2 seconds final processing
- **Output**: Detailed completion event with metrics

## Key Features

### Realistic Processing Delays

- Each stage has randomized delays to simulate actual processing time
- Network delays, CPU-intensive operations, and I/O operations are modeled

### Error Handling and Conditional Flow

- Validation failures can stop the entire workflow
- Transformation failures are tracked but don't stop processing
- Quality scores determine final status ratings

### Complex Data Flow

- Multiple fan-out points create parallel processing
- Multiple fan-in points aggregate results from parallel streams
- Shared state management for passing data between stages

### Rich Monitoring and Logging

- Detailed progress logging at each stage
- Performance metrics and quality scores
- Comprehensive final reports with recommendations

## Running the Workflow

### In DevUI

1. Start DevUI: `devui --agents-dir examples/sample_agents`
2. Navigate to the workflow in the UI
3. Provide input like "Customer data from Q4 2024"
4. Watch the real-time execution flow

### Standalone Testing

```bash
cd examples/sample_agents/complex_fanout_workflow
python workflow.py
```

## Example Outputs

The workflow processes various types of data:

- Customer data
- Transaction logs
- Product catalogs
- Analytics data

Each run provides:

- Real-time progress updates
- Processing time tracking
- Quality assessment scores
- Performance recommendations
- Final status (EXCELLENT/GOOD/ACCEPTABLE/NEEDS_IMPROVEMENT)

## Customization

You can modify:

- Processing delays by adjusting `asyncio.sleep()` values
- Success rates by changing probability distributions
- Quality thresholds for different status levels
- Number of parallel processors in each stage
- Data validation criteria and scoring algorithms
