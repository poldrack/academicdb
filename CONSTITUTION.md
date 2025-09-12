# non-negotiable principles

**Code style (NON-NEGOTIABLE)**:

- Write code that is clean and modular
- Prefer shorter functions/methods over longer ones

**Package management (NON-NEGOTIABLE)**:

- use uv for package management
- use `uv run` for all local commands

**Development processes (NON-NEGOTIABLE)**:

- FORBIDDEN: including any code or imports within init.py files.

**Testing (NON-NEGOTIABLE)**:
- use pytest with a test-driven development approach
- Prefer functions over classes for testing, using pytest fixtures for persistent objects
- RED-GREEN-Refactor cycle enforced? Yes - tests written first
- Git commits show tests before implementation? Yes - test commits precede implementation
- Order: Contract→Integration→E2E→Unit strictly followed? Yes
- Real dependencies used? Yes - actual MongoDB instance for testing
- Integration tests for: new libraries, contract changes, shared schemas? Yes
- FORBIDDEN: Implementation before test, skipping RED phase - Understood and enforced
- FORBIDDEN: - Changing the tests simply in order to pass.  All changes to tests should reflect either a change in requirements or an error identified in the test.

