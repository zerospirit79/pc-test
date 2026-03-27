"""CLI entry point for HW-Test."""

import argparse
import logging
import sys
import os
import json
from datetime import datetime
from typing import List, Optional

from hw_test import __version__
from hw_test.types import TestConfig, TestStatus, HardwareInfo
from hw_test.steps import (
    AVAILABLE_STEPS,
    DEFAULT_STEP_ORDER,
    get_step_class,
)


def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> logging.Logger:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    return logging.getLogger('hw_test')


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog='hw-test',
        description='Hardware compatibility testing tool for ALT Linux',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  hw-test --start                    # Run all tests interactively
  hw-test --start --batch            # Run all tests in batch mode
  hw-test --start --steps hardware_detection,express_test
  hw-test --list-steps               # Show available test steps
  hw-test --version                  # Show version
        """
    )
    
    # Main modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--start',
        action='store_true',
        help='Start hardware testing'
    )
    mode_group.add_argument(
        '--list-steps',
        action='store_true',
        help='List available test steps'
    )
    
    # Options
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Run in batch mode (no interactive prompts)'
    )
    parser.add_argument(
        '--name',
        type=str,
        default='default',
        help='Test session name (default: default)'
    )
    parser.add_argument(
        '--steps',
        type=str,
        help='Comma-separated list of steps to run (default: all)'
    )
    parser.add_argument(
        '--skip',
        type=str,
        help='Comma-separated list of steps to skip'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='/var/lib/hw-test',
        help='Directory for output files (default: /var/lib/hw-test)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        help='Log file path (default: stdout only)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=3600,
        help='Global timeout in seconds (default: 3600)'
    )
    parser.add_argument(
        '--language',
        type=str,
        choices=['en', 'ru'],
        default='ru',
        help='Interface language (default: ru)'
    )
    
    return parser


def list_steps() -> None:
    """Print available test steps."""
    print("\nAvailable test steps:")
    print("-" * 50)
    
    for step_name in DEFAULT_STEP_ORDER:
        step_class = get_step_class(step_name)
        if step_class:
            print(f"\n  {step_name}")
            print(f"    Description: {step_class.description}")
            print(f"    Requires root: {'Yes' if step_class.required_privileges else 'No'}")
    
    print("\n" + "-" * 50)
    print(f"Total: {len(AVAILABLE_STEPS)} steps")


def run_tests(config: TestConfig, logger: logging.Logger) -> int:
    """Run the test suite."""
    logger.info(f"Starting HW-Test v{__version__}")
    logger.info(f"Test name: {config.name}")
    logger.info(f"Batch mode: {config.batch_mode}")
    logger.info(f"Steps to run: {config.steps_to_run}")
    
    # Determine steps to execute
    if config.steps_to_run:
        steps_to_execute = config.steps_to_run
    else:
        steps_to_execute = DEFAULT_STEP_ORDER.copy()
    
    # Remove skipped steps
    if config.skip_steps:
        steps_to_execute = [s for s in steps_to_execute if s not in config.skip_steps]
    
    logger.info(f"Executing {len(steps_to_execute)} steps: {', '.join(steps_to_execute)}")
    
    # Initialize hardware info (will be populated by first step)
    hardware_info = HardwareInfo()
    
    # Execute steps
    results = []
    failed_count = 0
    warning_count = 0
    
    for step_name in steps_to_execute:
        step_class = get_step_class(step_name)
        
        if not step_class:
            logger.warning(f"Unknown step: {step_name}, skipping...")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Running step: {step_name}")
        logger.info(f"{'='*60}")
        
        try:
            step = step_class(config=config, hardware_info=hardware_info)
            result = step.run()
            results.append(result)
            
            # Update hardware info for subsequent steps
            if hasattr(step, 'detected_hardware'):
                hardware_info = step.detected_hardware
            
            # Count results
            if result.status == TestStatus.FAILED or result.status == TestStatus.ERROR:
                failed_count += 1
            elif result.status == TestStatus.WARNING:
                warning_count += 1
            
            # Print summary for this step
            print(f"\n[{result.status.value.upper()}] {step_name}: {result.message}")
            if result.duration_seconds > 0:
                print(f"  Duration: {result.duration_seconds:.2f}s")
            
            if result.warnings:
                for w in result.warnings:
                    print(f"  ⚠ Warning: {w}")
            
            if result.errors:
                for e in result.errors:
                    print(f"  ✗ Error: {e}")
                    
        except Exception as e:
            logger.exception(f"Step {step_name} failed with exception: {e}")
            failed_count += 1
            print(f"\n[ERROR] {step_name}: {str(e)}")
    
    # Final summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total steps executed: {len(results)}")
    print(f"Passed: {len(results) - failed_count - warning_count}")
    print(f"Warnings: {warning_count}")
    print(f"Failed/Errors: {failed_count}")
    
    if failed_count > 0:
        print("\n⚠ Some tests failed. Review the logs for details.")
        return 1
    elif warning_count > 0:
        print("\n✓ Tests completed with warnings.")
        return 0
    else:
        print("\n✓ All tests passed successfully!")
        return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Handle --list-steps
    if args.list_steps:
        list_steps()
        return 0
    
    # Require --start for running tests
    if not args.start:
        parser.print_help()
        return 1
    
    # Setup logging
    logger = setup_logging(verbose=args.verbose, log_file=args.log_file)
    
    # Parse steps
    steps_to_run = []
    if args.steps:
        steps_to_run = [s.strip() for s in args.steps.split(',')]
        # Validate steps
        for step in steps_to_run:
            if step not in AVAILABLE_STEPS:
                print(f"Error: Unknown step '{step}'")
                print(f"Available steps: {', '.join(AVAILABLE_STEPS.keys())}")
                return 1
    
    skip_steps = []
    if args.skip:
        skip_steps = [s.strip() for s in args.skip.split(',')]
    
    # Create configuration
    config = TestConfig(
        name=args.name,
        batch_mode=args.batch,
        verbose=args.verbose,
        data_dir=args.output_dir,
        log_dir=os.path.join(args.output_dir, 'logs'),
        steps_to_run=steps_to_run,
        skip_steps=skip_steps,
        timeout_seconds=args.timeout,
        language=args.language,
    )
    
    # Check for root privileges if needed
    if os.geteuid() != 0:
        print("⚠ Warning: Running without root privileges. Some tests may be skipped.")
        print("  For full functionality, run with: sudo hw-test ...")
    
    # Run tests
    return run_tests(config, logger)


if __name__ == '__main__':
    sys.exit(main())
