#!/usr/bin/env python3
"""
GAIA Result Viewer - Simple console output using Rich
Displays GAIA evaluation results with task details, predictions, and answers.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import orjson
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import track


# -----------------------------
# Data models
# -----------------------------

@dataclass
class GaiaResult:
    id: str
    level: int
    prediction: str
    answer: str
    correct: bool
    file_path: str


@dataclass
class GaiaMetadata:
    task_id: str
    question: str
    level: int
    final_answer: str
    file_name: str
    annotator_metadata: Dict[str, Any]


# -----------------------------
# GAIA Viewer Class
# -----------------------------

class GaiaViewer:
    """Simple GAIA result viewer that prints to console or saves to HTML."""

    def __init__(self, results_file: Path, dataset_dir: Path, output_html: Optional[Path] = None):
        self.results_file = results_file
        self.dataset_dir = dataset_dir
        self.output_html = output_html
        self.console = Console(record=True if output_html else False)
        self.metadata_cache: Dict[str, GaiaMetadata] = {}
        
    def load_metadata_cache(self) -> None:
        """Load all GAIA metadata into cache for quick lookup."""
        self.metadata_cache = {}
        metadata_files = list(self.dataset_dir.rglob("metadata.jsonl"))
        
        if not metadata_files:
            self.console.print(f"[yellow]Warning: No metadata.jsonl files found in {self.dataset_dir}[/yellow]")
            return
            
        for metadata_file in track(metadata_files, description="Loading metadata..."):
            try:
                with metadata_file.open("rb") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            data = orjson.loads(line)
                        except Exception:
                            data = json.loads(line)

                        id_candidates = [
                            data.get("task_id"),
                            data.get("question_id"),
                            data.get("id"),
                            data.get("uuid"),
                        ]
                        meta = GaiaMetadata(
                            task_id=str(data.get("task_id") or ""),
                            question=data.get("Question", "") or data.get("question", "") or "",
                            level=int(data.get("Level", 0) or data.get("level", 0) or 0),
                            final_answer=data.get("Final answer", "") or data.get("answer", "") or "",
                            file_name=data.get("file_name", "") or data.get("File name", "") or "",
                            annotator_metadata=data.get("Annotator Metadata", {}) or data.get("annotator_metadata", {}) or {},
                        )
                        for k in {str(x) for x in id_candidates if x}:
                            self.metadata_cache[k] = meta
                            
            except Exception as e:
                self.console.print(f"[red]Error loading metadata from {metadata_file}: {e}[/red]")

    def load_results(self) -> List[GaiaResult]:
        """Load results from the specified JSONL file."""
        results: List[GaiaResult] = []
        try:
            with self.results_file.open("rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = orjson.loads(line)
                    except Exception:
                        data = json.loads(line)
                    results.append(
                        GaiaResult(
                            id=data.get("id", ""),
                            level=int(data.get("level", 0) or 0),
                            prediction=str(data.get("prediction", "") or ""),
                            answer=str(data.get("answer", "") or ""),
                            correct=bool(data.get("correct", False)),
                            file_path=str(self.results_file),
                        )
                    )
        except Exception as e:
            self.console.print(f"[red]Error loading results from {self.results_file}: {e}[/red]")
        return results

    def print_summary_table(self, results: List[GaiaResult]) -> None:
        """Print a summary table of all results."""
        table = Table(title=f"GAIA Results Summary - {self.results_file.name}")
        table.add_column("Task ID", style="cyan", no_wrap=True)
        table.add_column("Level", justify="center", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Prediction Preview", style="green")
        table.add_column("Expected Answer Preview", style="blue")

        for result in results:
            status = "✅ CORRECT" if result.correct else "❌ INCORRECT"
            status_style = "green" if result.correct else "red"
            
            pred_preview = (result.prediction[:50] + "...") if len(result.prediction) > 50 else result.prediction
            answer_preview = (result.answer[:50] + "...") if len(result.answer) > 50 else result.answer
            
            table.add_row(
                result.id[:12] + ("..." if len(result.id) > 12 else ""),
                str(result.level),
                Text(status, style=status_style),
                pred_preview,
                answer_preview
            )

        self.console.print(table)
        
        # Print accuracy stats
        total = len(results)
        correct = sum(1 for r in results if r.correct)
        accuracy = correct / total if total > 0 else 0.0
        
        stats_panel = Panel(
            f"[bold]Total Results:[/bold] {total}\n"
            f"[bold]Correct:[/bold] [green]{correct}[/green]\n"
            f"[bold]Incorrect:[/bold] [red]{total - correct}[/red]\n"
            f"[bold]Accuracy:[/bold] [yellow]{accuracy:.2%}[/yellow]",
            title="Statistics",
            border_style="blue"
        )
        self.console.print(stats_panel)

    def print_detailed_results(self, results: List[GaiaResult]) -> None:
        """Print detailed view of each result."""
        self.console.print(f"\n[bold cyan]Detailed Results ({len(results)} tasks)[/bold cyan]\n")
        
        for i, result in enumerate(results, 1):
            metadata = self.metadata_cache.get(result.id)
            
            # Status indicator
            status = "✅ CORRECT" if result.correct else "❌ INCORRECT"
            status_style = "green" if result.correct else "red"
            
            # Build the content for this result
            content = f"[bold]Task ID:[/bold] {result.id}\n"
            content += f"[bold]Level:[/bold] {result.level}\n"
            content += f"[bold]Status:[/bold] [{status_style}]{status}[/{status_style}]\n\n"
            
            if metadata:
                content += f"[bold blue]Question:[/bold blue]\n{metadata.question}\n\n"
                content += f"[bold green]Expected Answer:[/bold green]\n{metadata.final_answer}\n\n"
                if metadata.file_name:
                    content += f"[bold magenta]File Attachment:[/bold magenta] {metadata.file_name}\n\n"
            else:
                content += f"[yellow]⚠️  Metadata not found for task {result.id}[/yellow]\n\n"
                content += f"[bold green]Expected Answer:[/bold green]\n{result.answer}\n\n"
            
            content += f"[bold red]Model Prediction:[/bold red]\n{result.prediction}\n"
            
            # Add annotator metadata if available
            if metadata and metadata.annotator_metadata:
                content += f"\n[bold cyan]Annotator Metadata:[/bold cyan]\n"
                for key, value in metadata.annotator_metadata.items():
                    if value not in (None, ""):
                        content += f"[yellow]{key}:[/yellow] {value}\n"
            
            panel = Panel(
                content,
                title=f"Result {i}/{len(results)}",
                border_style="green" if result.correct else "red"
            )
            self.console.print(panel)

    def run(self, detailed: bool = False) -> None:
        """Main execution method."""
        self.console.print(f"[bold]GAIA Result Viewer[/bold]")
        self.console.print(f"Results file: {self.results_file}")
        self.console.print(f"Dataset directory: {self.dataset_dir}\n")
        
        # Load metadata
        self.load_metadata_cache()
        self.console.print(f"Loaded metadata for {len(self.metadata_cache)} tasks\n")
        
        # Load results
        results = self.load_results()
        if not results:
            self.console.print("[red]No results found in the specified file.[/red]")
            return
            
        # Print summary table
        self.print_summary_table(results)
        
        # Print detailed results if requested
        if detailed:
            self.print_detailed_results(results)
        
        # Save to HTML if requested
        if self.output_html:
            self.save_to_html()
            self.console.print(f"\n[green]Results saved to {self.output_html}[/green]")

    def save_to_html(self) -> None:
        """Save the console output to an HTML file."""
        if self.output_html and self.console.record:
            html_content = self.console.export_html()
            with open(self.output_html, 'w', encoding='utf-8') as f:
                f.write(html_content)


# -----------------------------
# CLI
# -----------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="GAIA Result Viewer - Simple console viewer for GAIA evaluation results"
    )
    parser.add_argument(
        "results_file",
        type=Path,
        help="Path to the GAIA results JSONL file"
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data_gaia_hub"),
        help="Directory containing cached GAIA dataset (default: data_gaia_hub)"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed view of each result (default: summary only)"
    )
    parser.add_argument(
        "--output-html",
        type=Path,
        help="Save output to HTML file instead of just printing to console"
    )
    
    args = parser.parse_args()

    if not args.results_file.exists():
        print(f"Error: Results file '{args.results_file}' does not exist")
        return 1
    if not args.dataset_dir.exists():
        print(f"Error: Dataset directory '{args.dataset_dir}' does not exist")
        return 1

    viewer = GaiaViewer(args.results_file, args.dataset_dir, args.output_html)
    viewer.run(detailed=args.detailed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
