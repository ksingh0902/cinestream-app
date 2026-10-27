# Workflow & Approval Rules

## Post-Change Summary Structure
After making changes to the codebase, configuration, or database, always provide a structured summary containing:
1. **Root Cause**: The underlying reason for the bug, failure, or missing behavior.
2. **What Was Fixed**: The concrete modifications made to files, endpoints, or data.
3. **Status**: Real verification results, metrics/test outcomes, and current state.

## Git & GitHub Push Approval Policy
- **CRITICAL**: ALWAYS ask the user for explicit approval BEFORE executing any `git push` to GitHub or remote repositories.
- Never push autonomously to `origin/main` or any remote branch without the user explicitly reviewing and approving the changes.

## Oracle redeploy rule
- After the user approves a push to `main`, follow [`DEPLOY_ORACLE.md`](../../DEPLOY_ORACLE.md): SSH to the Oracle VM, pull with `git pull --ff-only`, rebuild the Docker image, restart the `cinemymovies` container with the VM-only `.env` and `DB_PATH=yomovies.db`, and run the documented health checks.
- Do not put production secrets in the repository, in Gemini instructions, in commits, or in chat. Use only `/home/ubuntu/cinestream-app/.env` on the VM.
- Do not claim deployment succeeded until the container logs and public HTTPS check have been verified.
