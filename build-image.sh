#!/bin/bash
set -e

IMAGE_NAME="trading-bot"
TAG="${1:-latest}"

echo "Building ${IMAGE_NAME}:${TAG}..."
docker compose build

echo "Done. Run with: docker compose up -d"
