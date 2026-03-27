"""Base class for hardware test steps."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from hw_test.types import StepResult, TestStatus, HardwareInfo, TestConfig


logger = logging.getLogger(__name__)


class BaseHWStep(ABC):
    """
    Abstract base class for all hardware test steps.
    
    Each test step should inherit from this class and implement:
    - name: Human-readable name of the step
    - description: Detailed description of what the step does
    - execute(): Main test logic
    """
    
    name: str = "Base Step"
    description: str = "Base test step"
    required_privileges: bool = False
    timeout_seconds: int = 300
    
    def __init__(self, config: TestConfig, hardware_info: Optional[HardwareInfo] = None):
        """
        Initialize the test step.
        
        Args:
            config: Test configuration
            hardware_info: Detected hardware information (may be None for early steps)
        """
        self.config = config
        self.hardware_info = hardware_info
        self.logger = logging.getLogger(f"hw_test.steps.{self.__class__.__name__}")
    
    def setup(self) -> bool:
        """
        Setup hook called before execute().
        
        Returns:
            True if setup succeeded, False otherwise
        """
        self.logger.debug(f"Setting up step: {self.name}")
        return True
    
    def teardown(self) -> None:
        """Cleanup hook called after execute(), even if it failed."""
        self.logger.debug(f"Tearing down step: {self.name}")
    
    @abstractmethod
    def execute(self) -> StepResult:
        """
        Execute the test step.
        
        Returns:
            StepResult with status, message, and any errors/warnings
        """
        pass
    
    def run(self) -> StepResult:
        """
        Run the complete step lifecycle: setup -> execute -> teardown.
        
        Returns:
            StepResult from execute() or error result if setup/teardown fails
        """
        start_time = time.time()
        
        # Setup phase
        if not self.setup():
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message="Setup failed",
                errors=["Step setup failed"]
            )
        
        try:
            # Execute phase
            self.logger.info(f"Starting step: {self.name}")
            result = self.execute()
            result.duration_seconds = time.time() - start_time
            
            if result.errors:
                self.logger.error(f"Step {self.name} completed with errors: {result.errors}")
            if result.warnings:
                self.logger.warning(f"Step {self.name} completed with warnings: {result.warnings}")
            
            self.logger.info(
                f"Step {self.name} completed: {result.status.value} "
                f"in {result.duration_seconds:.2f}s"
            )
            
            return result
            
        except Exception as e:
            self.logger.exception(f"Step {self.name} raised exception: {e}")
            return StepResult(
                step_name=self.name,
                status=TestStatus.ERROR,
                message=f"Exception during execution: {str(e)}",
                errors=[str(e)],
                duration_seconds=time.time() - start_time
            )
            
        finally:
            # Teardown phase (always runs)
            try:
                self.teardown()
            except Exception as e:
                self.logger.warning(f"Teardown for {self.name} failed: {e}")
    
    def get_result_dict(self, result: StepResult) -> Dict[str, Any]:
        """Convert StepResult to dictionary for JSON serialization."""
        return {
            "step_name": result.step_name,
            "status": result.status.value,
            "message": result.message,
            "details": result.details,
            "duration_seconds": result.duration_seconds,
            "errors": result.errors,
            "warnings": result.warnings,
        }
