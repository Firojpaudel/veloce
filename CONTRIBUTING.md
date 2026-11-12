# Contributing to Veloce

Thank you for your interest in contributing to Veloce!

Veloce is built with a few strict architectural principles:
1. **Standard Library Only Engine**: The core download engine (`engine/segmenter.py`, `engine/server.py`, `engine/share.py`) has **zero runtime dependencies** outside the Python 3.10+ standard library.
2. **Adaptive Performance**: The probe request *is* the first stream. Connections ramp only when throughput measurably increases; slow sockets are shed; tail segments are bisected based on time-to-finish (ETA), not raw byte size.
3. **Crash Safety & Atomic Writes**: In-progress downloads write to `<final>.veloce.part` alongside a `.veloce.json` sidecar. The file is only committed to its final path via `os.replace` once all byte ranges are verified.
4. **Offline Testability**: All tests run completely offline against local `http.server` mock instances without external network access.

---

## Development Setup

Clone the repository and verify the test suite:

```bash
git clone https://github.com/Firojpaudel/veloce.git
cd veloce

# Run the full unit test suite (offline, ~20s)
python -m unittest discover -s tests -v

# Check JavaScript syntax
npm run check:js

# Verify version synchronization
python scripts/check_version.py
```

Optional dependencies for running the desktop tray and full video tools locally:
```bash
pip install -r requirements.txt
```

---

## Code Guidelines

- **Standard Library Only**: Do not add runtime dependencies to the engine.
- **Short, Intent-Focused Docstrings**: Explain *why* a decision was made (e.g. why 0.4s measurement window, why socket resets), not just *what* the code does.
- **User-Facing Errors**: Use plain, friendly language rather than low-level tracebacks where errors reach the UI.
- **Every Change Gets a Test**: Add offline tests under `tests/` verifying bug fixes or new features. All tests must pass cleanly across Windows, macOS, and Linux.

---

## Submitting Pull Requests

1. Fork the repository and create your branch from `main`.
2. Ensure all tests pass (`python -m unittest discover -s tests -v`) and `npm run check:js` passes.
3. If changing version numbers, run `python scripts/check_version.py` to ensure consistency.
4. Submit your pull request with a descriptive title and summary of changes.

