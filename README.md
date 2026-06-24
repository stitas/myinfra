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