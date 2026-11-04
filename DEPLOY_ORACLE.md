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
  -e ENVIRONMENT=production \
  -e DISABLE_AUTO_SYNC=1 \
  -e ENABLE_AUTO_SYNC=0 \
  -e CATALOG_READ_ONLY=1 \
  -e DB_PATH=/app/yomovies.db \
  -v /home/ubuntu/cinestream-app/yomovies.db:/app/yomovies.db:ro \
  -v /home/ubuntu/cinestream-app/cinemymovies.sqlite3:/app/cinemymovies.sqlite3:rw \
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

## Catalogue imports (separate from production)

Do not run `run_full_sync` or a crawler inside the production web container. Run the
importer on a development/worker machine, validate the resulting `yomovies.db`, and
copy it to the VM only after taking a timestamped backup:

```bash
ssh -i /path/to/key ubuntu@137.23.48.95
cd ~/cinestream-app
cp yomovies.db backups/yomovies-$(date +%Y%m%d-%H%M%S).db
```

Copy the validated database to a temporary path, then atomically replace the live file
while the container is stopped. Restart only the application container using the
normal redeploy commands above. `DISABLE_AUTO_SYNC=1` is set for production so the
web process cannot start a background crawl.

## HLS relay: Nginx, not Python

The API container must never carry HLS segment bytes.  Set a long random
`HLS_SEGMENT_SIGNING_SECRET` plus a tested `HLS_PROXY_ALLOWED_HOSTS` list in the
VM-only `.env`. Then render and test the checked-in Nginx template:

```bash
cd ~/cinestream-app
set -a; . ./.env; set +a
envsubst '$HLS_SEGMENT_SIGNING_SECRET' < nginx/cinemymovies.conf.template | \
  sudo tee /etc/nginx/conf.d/cinemymovies.conf >/dev/null
sudo nginx -t && sudo systemctl reload nginx
```

The host list in `nginx/cinemymovies.conf.template` must match the `.env`
allow-list before enabling it. Test a resolved provider segment from the VM
first; a `403` or timeout means that provider cannot be safely relayed from the
Oracle data-centre and should not be added to the list.

## Catalogue imports are laptop-only

Run `python sync_latest.py` on the laptop, validate the new database with
`PRAGMA integrity_check`, copy it to `yomovies.new.db` on the VM, then atomically
replace the live file. The production container reads the mounted DB only:

```bash
mv yomovies.new.db yomovies.db
docker restart cinemymovies
```
