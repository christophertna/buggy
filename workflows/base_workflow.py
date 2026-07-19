"""
workflows/base_workflow.py

A Workflow is an ordered sequence of tasks with shared context, sitting one
level above the raw task queue main.py consumes. Workflows are how you
compose multi-step operations (e.g. "read current inventory, then write an
adjustment") while still letting each individual step go through the same
Harness-gated orchestrator.run_task() used everywhere else.

This is intentionally minimal — extend per-project as needed.
"""
from dataclasses import dataclass, field


@dataclass
class WorkflowStep:
    id: str
    description: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    name: str
    steps: list[WorkflowStep]

    def to_tasks(self) -> list[dict]:
        """
        Flattens the workflow into the same task dict shape main.py reads
        from tasks.json, preserving ordering. Dependency enforcement beyond
        ordering (e.g. skip downstream steps if an upstream one fails) is
        the outer loop's responsibility — see main.py's SKIPPED handling.
        """
        return [
            {"id": f"{self.name}:{step.id}", "description": step.description}
            for step in self.steps
        ]


def build_example_workflow() -> Workflow:
    """Example: adjust inventory only after confirming current stock."""
    return Workflow(
        name="inventory_adjustment",
        steps=[
            WorkflowStep(
                id="check_stock",
                description="Read the current quantity for SKU 'ABC-123' from the inventory table.",
            ),
            WorkflowStep(
                id="apply_adjustment",
                description=(
                    "If SKU 'ABC-123' has quantity > 0, decrement it by 1 "
                    "using a parameterized UPDATE scoped with WHERE sku = 'ABC-123'."
                ),
                depends_on=["check_stock"],
            ),
        ],
    )
