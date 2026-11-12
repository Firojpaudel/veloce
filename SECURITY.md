# Security Policy

## Supported Versions

Security updates and patches are provided for the current major release series:

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

The Veloce project takes security vulnerabilities seriously. If you discover a vulnerability in Veloce (engine, browser extension, or web UI), please help us resolve it responsibly.

**Please do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

Instead, report them privately using one of the following methods:

1. **GitHub Private Vulnerability Reporting (Recommended)**:
   Navigate to the repository's [Security tab](https://github.com/Firojpaudel/veloce/security) and click **Report a vulnerability**. This creates a confidential advisory draft visible only to project maintainers.

2. **Email**:
   If private vulnerability reporting is unavailable, email the maintainer directly at `firojpaudel@gmail.com` with the subject line `[SECURITY] Veloce Vulnerability Report`.

### What to Include

To help us triage and resolve the issue quickly, please include:
- A clear description of the vulnerability and its potential impact.
- Step-by-step reproduction instructions or a minimal Proof of Concept (PoC).
- The affected component(s) (e.g. `engine/server.py`, extension service worker, `media.py`).
- Operating system and environment details.
- Any suggested mitigations or patches, if available.

## Response SLA and Process

- **Initial Response**: We will acknowledge receipt of your report within **48 hours**.
- **Triage & Assessment**: We will assess the severity and reproduce the issue within **7 days**.
- **Fix & Disclosure**: We will develop and test a fix, coordinate disclosure timing with you, and release a security advisory alongside the patched release. Credit will be given in release notes and advisory unless you request anonymity.
