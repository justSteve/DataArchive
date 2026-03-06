"""
Progress reporting for long-running Python tasks
Emits JSON progress updates that TypeScript can capture via stdout
"""

import sys
import json
from typing import Optional, Dict, Any
from datetime import datetime


class ProgressReporter:
    """Report progress for long-running tasks"""

    def __init__(self, task_type: str, task_id: str, total_items: Optional[int] = None):
        """
        Initialize progress reporter

        Args:
            task_type: Type of task (scan, hash_computation, inspection, etc.)
            task_id: Unique identifier for this task
            total_items: Total number of items to process (if known)
        """
        self.task_type = task_type
        self.task_id = task_id
        self.total_items = total_items
        self.processed_items = 0
        self.error_count = 0
        self.start_time = datetime.now()

    def report(
        self,
        processed: Optional[int] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit a progress update

        Args:
            processed: Number of items processed (updates counter)
            message: Optional status message
            details: Optional additional details
        """
        if processed is not None:
            self.processed_items = processed

        progress_pct = 0.0
        if self.total_items and self.total_items > 0:
            progress_pct = (self.processed_items / self.total_items) * 100.0

        elapsed = (datetime.now() - self.start_time).total_seconds()

        # Estimate remaining time
        eta_seconds = None
        if progress_pct > 0:
            eta_seconds = (elapsed / progress_pct) * (100.0 - progress_pct)

        progress_data = {
            "type": "progress",
            "task_type": self.task_type,
            "task_id": self.task_id,
            "processed_items": self.processed_items,
            "total_items": self.total_items,
            "progress_pct": round(progress_pct, 2),
            "elapsed_seconds": round(elapsed, 2),
            "eta_seconds": round(eta_seconds, 2) if eta_seconds else None,
            "error_count": self.error_count,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

        if details:
            progress_data["details"] = details

        # Emit as JSON to stdout (PythonBridge captures this)
        print(json.dumps(progress_data), flush=True)

    def increment(self, count: int = 1, message: Optional[str] = None) -> None:
        """
        Increment processed counter and report

        Args:
            count: Number of items to add to counter
            message: Optional status message
        """
        self.processed_items += count
        self.report(message=message)

    def report_error(self, error_message: str) -> None:
        """
        Report an error

        Args:
            error_message: Description of the error
        """
        self.error_count += 1
        self.report(message=f"Error: {error_message}")

    def complete(self, message: Optional[str] = None) -> None:
        """
        Mark task as complete

        Args:
            message: Optional completion message
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()

        completion_data = {
            "type": "complete",
            "task_type": self.task_type,
            "task_id": self.task_id,
            "processed_items": self.processed_items,
            "total_items": self.total_items,
            "error_count": self.error_count,
            "elapsed_seconds": round(elapsed, 2),
            "message": message or "Task completed successfully",
            "timestamp": datetime.now().isoformat()
        }

        print(json.dumps(completion_data), flush=True)


def emit_progress(
    task_type: str,
    task_id: str,
    processed: int,
    total: Optional[int] = None,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Utility function to emit a one-time progress update without maintaining state

    Args:
        task_type: Type of task
        task_id: Task identifier
        processed: Items processed
        total: Total items (if known)
        message: Optional status message
        details: Optional additional details
    """
    progress_pct = 0.0
    if total and total > 0:
        progress_pct = (processed / total) * 100.0

    progress_data = {
        "type": "progress",
        "task_type": task_type,
        "task_id": task_id,
        "processed_items": processed,
        "total_items": total,
        "progress_pct": round(progress_pct, 2),
        "message": message,
        "timestamp": datetime.now().isoformat()
    }

    if details:
        progress_data["details"] = details

    print(json.dumps(progress_data), flush=True)
