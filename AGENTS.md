# Project Rules & Workflow Instructions

## Post-Change Summary Structure
After making changes to the codebase, configuration, or database, always provide a structured summary containing:
1. **Root Cause**: The underlying reason for the bug, failure, or missing behavior.
2. **What Was Fixed**: The concrete modifications made to files, endpoints, or data.
3. **Status**: Real verification results, metrics/test outcomes, and current state.

## Git & GitHub Push Approval Policy
- **CRITICAL**: ALWAYS ask the user for explicit approval BEFORE executing any `git push` to GitHub or remote repositories.
- Never push autonomously to `origin/main` or any remote branch without the user explicitly reviewing and approving the changes.
