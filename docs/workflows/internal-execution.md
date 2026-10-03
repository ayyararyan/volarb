# Internal Execution — legacy name

The reusable strategy-agnostic component formerly called **Internal Execution** is now canonically **Execution Engine**.

- Canonical root VID remains `[5,0,0,0,0]`.
- Canonical component ID is `component.execution_engine`.
- `component.internal_execution` remains a compatibility alias only.
- A strategy-specific execution layer, if needed, belongs upstream as a **Strategy Execution Adapter**.

See [execution-engine.md](execution-engine.md).
