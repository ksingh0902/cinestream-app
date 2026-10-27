# Oracle deployment runbook

The production CineMyMovies service runs on the Oracle VM behind Nginx and Docker.

Public URL: <https://137-23-48-95.sslip.io>

## Secrets

Never commit, paste, or copy production secrets into Git. The production environment
file exists only on the VM at `/home/ubuntu/cinestream-app/.env`. The repository's
`.gitignore` excludes `.env` and other environment files.

## After every approved push to `main`

Run these commands from PowerShell:

```powershell
ssh -i "$env:USERPROFILE\Downloads\ssh-key-2026-10-27 (2).key" ubuntu@137.23.48.95
```

Then, on the VM:

```bash
cd ~/cinestream-app
git pull --ff-only origin main
docker build -t cinemymovies:latest .
docker rm -f cinemymovies 2>/dev/null || true
docker run -d \
  --name cinemymovies \
  --restart unless-stopped \
  --env-file /home/ubuntu/cinestream-app/.env \
  -e DB_PATH=yomovies.db \
  -p 127.0.0.1:8000:8000 \
  cinemymovies
```

## Verify before announcing the release

```bash
docker ps --filter name=cinemymovies
docker logs --tail 80 cinemymovies
curl -I http://127.0.0.1:8000/login
curl -I https://137-23-48-95.sslip.io/
```

The expected public response for `/` is a redirect to `/login` for unauthenticated
users. Do not replace the VM `.env` or catalogue database during a normal code deploy.

## Safety rules

- Ask the user for approval before every `git push`.
- Never print secret values in logs or chat.
- Do not expose the container directly; keep it bound to `127.0.0.1:8000`.
- Keep Nginx and the HTTPS certificate managed separately from application rebuilds.
