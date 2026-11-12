# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.3] - 2026-11-12

### Added
- **Crash-Safe Atomic Downloads**:
  - In-progress downloads write to `<final>.veloce.part` alongside an atomic JSON sidecar (`<final>.veloce.json`).
  - Atomic rename (`os.replace`) to final destination only occurs once every segment is complete and byte count matches `total_size`.
  - Transparent resume across engine restarts verifying ETag, Last-Modified, and size via `If-Range`.
  - Cancel cleanly purges both `.part` and `.json` temp files.
- **Engine Test Coverage**:
  - Controllable local server offline test harness for edge conditions.
  - Test verifying ETA-based tail-splitting (bisection of the segment that finishes last, not raw largest byte count).
  - Multi-threaded stress test confirming contiguous, non-overlapping byte range integrity under concurrent work-stealing.
  - Tests for slow connection shedding (below 1/4 of peak throughput past grace period).
  - Tests for handling mid-stream HTTP 200 responses to ranged requests without file corruption.
  - Tests for server drop/reset recovery and adaptive single-stream mode for fast transfers.
- **Security Hardening**:
  - Pinned key in extension manifest providing a stable extension ID (`faaebjnfegkfoehnbilkajcdkjjngeap`).
  - Engine API rejects requests from unauthorized extension IDs with HTTP 403 Forbidden.
  - Scoped cookie retrieval (`chrome.cookies.getAll({ url })`) preventing public suffix leakage; cookies omitted from background prefetch.
  - Strict caption format validation (`webvtt`, `srt`, `ass`) with `-protocol_whitelist file` in ffmpeg subtitle processing.
  - Share server binds to detected LAN IP with fallback to `0.0.0.0`, with unencrypted HTTP warning note in dashboard.
  - Media title disambiguation (`<title> [<id/hash>]`) preventing silent collision with existing media files.
  - Formal `SECURITY.md` disclosure policy and SLA.
- **Release Trust & Verification**:
  - Sigstore Cosign keyless OIDC signing in release workflow producing `.sig`, `.pem`, and `.bundle` assets.
  - Self-update signature verification in `app_update.py`.
  - OS-specific SHA-256 verification instructions in `README.md`.
- **Repo Hygiene**:
  - Single source of truth version verification script (`scripts/check_version.py`).
  - Added `CONTRIBUTING.md`, issue templates for bugs and features.
