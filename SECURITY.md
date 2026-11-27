# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this repository:

1. **Do NOT open a public GitHub issue** for undisclosed vulnerabilities.
2. Submit a private report via GitHub Security Advisories (`Security -> Advisories -> Report a vulnerability`).
3. Include affected file paths, line numbers, reproduction steps, and estimated severity.
4. Initial acknowledgement will be provided within **48 hours**.

## Security Controls

- **Secret Hygiene**: `.env` and key files are excluded via `.gitignore`; zero credentials are stored in source control.
- **SQL Injection Prevention**: Every database query inside `src/techcorp_analytics/` uses strict parameterized SQL placeholders (`?`) and enforces `PRAGMA foreign_keys = ON`.
- **Automated Vulnerability Management**: Weekly Dependabot alerts (`semver-major` ignored for stability), Semgrep SAST, and Trivy container image scanning in CI.
- **Container Hardening**: Multi-stage non-root Docker runtime (`appuser`).
