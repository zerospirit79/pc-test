"""
Base step module defining the interface for all test steps.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import time


class StepStatus(Enum):
    """Status of a test step execution."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class StepResult:
    """Result of a test step execution."""
    step_name: str
    status: StepStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "step_name": self.step_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "duration": self.duration,
            "errors": self.errors,
            "warnings": self.warnings
        }


class BaseStep(ABC):
    """Abstract base class for all test steps."""
    
    def __init__(self, config: Dict[str, Any], logger: Any):
        """
        Initialize the step.
        
        Args:
            config: Configuration dictionary for the step
            logger: Logger instance for logging messages
        """
        self.config = config
        self.logger = logger
        self.name = self.__class__.__name__
    
    @abstractmethod
    def execute(self) -> StepResult:
        """
        Execute the test step.
        
        Returns:
            StepResult with the outcome of the test
        """
        pass
    
    def setup(self) -> bool:
        """
        Setup prerequisites for the step.
        
        Returns:
            True if setup was successful, False otherwise
        """
        return True
    
    def teardown(self) -> None:
        """Cleanup after the step execution."""
        pass
    
    def run(self) -> StepResult:
        """
        Run the complete step lifecycle: setup -> execute -> teardown.
        
        Returns:
            StepResult with the outcome of the test
        """
        start_time = time.time()
        
        try:
            # Setup phase
            if not self.setup():
                return StepResult(
                    step_name=self.name,
                    status=StepStatus.SKIPPED,
                    message="Setup failed, skipping step",
                    duration=time.time() - start_time
                )
            
            # Execute phase
            result = self.execute()
            result.duration = time.time() - start_time
            return result
            
        except Exception as e:
            self.logger.exception(f"Step {self.name} failed with exception")
            return StepResult(
                step_name=self.name,
                status=StepStatus.FAILED,
                message=f"Exception: {str(e)}",
                errors=[str(e)],
                duration=time.time() - start_time
            )
        
        finally:
            # Teardown phase
            self.teardown()
