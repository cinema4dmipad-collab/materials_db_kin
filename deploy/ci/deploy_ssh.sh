#!/bin/sh
# Деплой на сервер через SSH: pull образа и перезапуск docker compose.
# CI/CD variables (protected):
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_PATH, SSH_PRIVATE_KEY
#   DEPLOY_IMAGE — полный тег образа (передаётся из job build)
set -eu

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${DEPLOY_IMAGE:?DEPLOY_IMAGE is required}"

mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "$SSH_PRIVATE_KEY" | tr -d '\r' > ~/.ssh/id_rsa
chmod 600 ~/.ssh/id_rsa
ssh-keyscan -H "$DEPLOY_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true

ssh -o StrictHostKeyChecking=accept-new "${DEPLOY_USER}@${DEPLOY_HOST}" <<EOF
set -eu
cd "${DEPLOY_PATH}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-materials_db}"
export WEB_IMAGE="${DEPLOY_IMAGE}"
docker compose -f docker-compose.prod.yml pull web
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml ps
EOF
