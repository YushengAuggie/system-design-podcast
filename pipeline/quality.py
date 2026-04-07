"""Quality gate pattern for pipeline steps."""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class StepResult:
    """Result from a pipeline step with quality gate info."""

    output: Any
    passed: bool
    message: str
    attempt: int


def run_with_quality_gate(
    step_fn: Callable[..., Any],
    validate_fn: Callable[[Any], tuple[bool, str]],
    max_retries: int,
    feedback_fn: Callable[[Any, str], dict] | None = None,
    **kwargs: Any,
) -> StepResult:
    """Run a step, validate, retry with feedback if failed.

    Args:
        step_fn: Function that produces output. Called with **kwargs.
        validate_fn: Takes output, returns (passed, message).
        max_retries: Maximum number of attempts.
        feedback_fn: Optional. Takes (output, failure_message) and returns
                     updated kwargs for the next attempt.
        **kwargs: Arguments passed to step_fn.

    Returns:
        StepResult with the final output and quality gate verdict.
    """
    output: Any = None
    message: str = "Quality gate loop did not execute (max_retries=0)"

    for attempt in range(1, max_retries + 1):
        try:
            output = step_fn(**kwargs)
        except Exception as exc:
            return StepResult(
                output=None,
                passed=False,
                message=f"Step raised an exception on attempt {attempt}: {exc}",
                attempt=attempt,
            )

        passed, message = validate_fn(output)

        if passed:
            return StepResult(output=output, passed=True, message=message, attempt=attempt)

        print(f"  Quality gate failed (attempt {attempt}/{max_retries}): {message}")

        if attempt < max_retries and feedback_fn is not None:
            kwargs = feedback_fn(output, message)

    return StepResult(output=output, passed=False, message=message, attempt=max_retries)
