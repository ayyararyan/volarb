# JavaScript execution-contract compatibility

This directory is a **transitional compatibility surface** for JavaScript consumers
that have not yet migrated to the canonical Python Execution Engine.

Canonical implementation:

`execution-engine/volarb_execution/`

Current consumers are the Dhan JavaScript provider and the legacy JavaScript
Execution Testbed. New Execution Engine boxes and sub-boxes must not be implemented
here. This compatibility layer preserves the established broker-operation and
provider-error wire vocabulary while those consumers are migrated independently.

It is not a second Execution Engine implementation and must not contain execution
policy, strategy logic, recovery policy, agentic decisions, or broker authorization.
