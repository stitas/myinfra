# Infra setup for virtual private server (VPS) that hosts multiple apps

Create internal docker network before hand to allow communication between containers:
```bash
sudo docker network create app_internal
```

Create new databases later using:
```bash
APP_DB_NAME=app_db
APP_DB_USER=app_user
APP_DB_PASSWORD=$(openssl rand -hex 32)

sudo docker exec -i shared-postgres psql -U postgres <<SQL
CREATE USER ${APP_DB_USER} WITH PASSWORD '${APP_DB_PASSWORD}';
CREATE DATABASE ${APP_DB_NAME} OWNER ${APP_DB_USER};
SQL

echo "DATABASE_URL=postgresql://${APP_DB_USER}:${APP_DB_PASSWORD}@postgres/${APP_DB_NAME}"
```

Run compose with:
```bash
sudo docker compose up -d
```

## TODO

check why TASK [argocd : Bootstrap Argo CD projects] is always changing

## VPS Infrastructure — 12-Hour Implementation Plan

### Phase 2 — Applications

[ ] Hour 4: Deploy Umami with PostgreSQL, Sealed Secrets and HTTPS.
[ ] Hour 5: Deploy Copyparty with persistent storage, authentication and HTTPS.
[ ] Hour 6: Configure media backups and verify persistence after restarts.

### Phase 3 — Personal App CI/CD

[ ] Hour 7: Create a reusable Helm chart for personal applications.
[ ] Hour 8: Configure reusable GitHub Actions to build and publish images to GHCR.
[ ] Hour 9: Configure Argo CD Image Updater, Git write-back and automatic deployment triggers.
[ ] Hour 10: Deploy a test application and verify push-to-master automatic deployment.

### Phase 4 — Production Readiness

[ ] Hour 11: Configure monitoring and alerts for applications, server resources and backups.
[ ] Hour 12: Test VPS disaster recovery and document infrastructure setup and migration procedures.