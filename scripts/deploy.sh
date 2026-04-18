#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENVIRONMENT="${1:-prod}"
case "${ENVIRONMENT}" in
  dev|staging|prod) ;;
  *)
    echo "Unsupported environment: ${ENVIRONMENT}"
    echo "Usage: scripts/deploy.sh [dev|staging|prod]"
    exit 1
    ;;
esac

load_env_file() {
  local env_file="$1"
  if [[ -f "${env_file}" ]]; then
    echo "Loading env file: ${env_file}"
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

load_env_file "${ROOT_DIR}/.env.local"
load_env_file "${ROOT_DIR}/deploy/env/${ENVIRONMENT}.env"

first_non_empty() {
  local value
  for value in "$@"; do
    if [[ -n "${value}" ]]; then
      printf '%s' "${value}"
      return 0
    fi
  done
  return 1
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}"
    exit 1
  fi
}

require_command docker
require_command python3

VERSION="$(python3 -c "import json, pathlib; print(json.loads(pathlib.Path('package.json').read_text(encoding='utf-8'))['version'])")"
REGISTRY="$(first_non_empty "${IMAGE_REGISTRY:-}" "${REGISTRY:-}" "${REGISTRY_URL:-}" "${DOCKER_REGISTRY:-}" || true)"
IMAGE_NAME="$(first_non_empty "${IMAGE_NAME:-}" "${REPOSITORY_NAME:-}" "${IMAGE_REPO:-}" "youtube-to-mp4" || true)"
IMAGE_NAMESPACE="$(first_non_empty "${IMAGE_NAMESPACE:-}" "${NAMESPACE:-}" "${REGISTRY_NAMESPACE:-}" || true)"
APP_ENV="$(first_non_empty "${APP_ENV:-}" "$([[ "${ENVIRONMENT}" == "prod" ]] && echo production || echo "${ENVIRONMENT}")" || true)"
IMAGE_TAG="$(first_non_empty "${IMAGE_TAG:-}" "$([[ "${ENVIRONMENT}" == "prod" ]] && echo "${VERSION}" || echo "${VERSION}-${ENVIRONMENT}")" || true)"
PLATFORMS="$(first_non_empty "${PLATFORMS:-}" "${TARGET_PLATFORMS:-}" "linux/amd64,linux/arm64" || true)"
BUILDER_NAME="$(first_non_empty "${BUILDER_NAME:-}" "${BUILDX_BUILDER_NAME:-}" "multiarch-builder" || true)"
BUILD_CONTEXT="$(first_non_empty "${BUILD_CONTEXT:-}" "${CONTEXT_PATH:-}" "." || true)"
DOCKERFILE_PATH="$(first_non_empty "${DOCKERFILE_PATH:-}" "${DOCKERFILE:-}" "Dockerfile" || true)"
DRY_RUN="$(first_non_empty "${DRY_RUN:-}" "false" || true)"

if [[ -z "${REGISTRY}" ]]; then
  echo "IMAGE_REGISTRY is required. Set it in .env.local or your shell environment."
  exit 1
fi

IMAGE_REPOSITORY="${IMAGE_NAME}"
if [[ -n "${IMAGE_NAMESPACE}" ]]; then
  IMAGE_REPOSITORY="${IMAGE_NAMESPACE}/${IMAGE_NAME}"
fi

IMAGE_REF="${REGISTRY}/${IMAGE_REPOSITORY}:${IMAGE_TAG}"

echo "Environment: ${ENVIRONMENT}"
echo "App version: ${VERSION}"
echo "App env: ${APP_ENV}"
echo "Dockerfile: ${DOCKERFILE_PATH}"
echo "Build context: ${BUILD_CONTEXT}"
echo "Docker image: ${IMAGE_REF}"
echo "Platforms: ${PLATFORMS}"
echo "Dry run: ${DRY_RUN}"

BUILD_COMMAND=(
  docker buildx build
  --platform "${PLATFORMS}"
  --build-arg "APP_VERSION=${VERSION}"
  --build-arg "APP_ENV=${APP_ENV}"
  -f "${DOCKERFILE_PATH}"
  -t "${IMAGE_REF}"
  --push
  "${BUILD_CONTEXT}"
)

if [[ "${DRY_RUN}" == "true" ]]; then
  printf 'Command:'
  printf ' %q' "${BUILD_COMMAND[@]}"
  printf '\n'
  exit 0
fi

if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
  docker buildx create --name "${BUILDER_NAME}" --use
else
  docker buildx use "${BUILDER_NAME}"
fi

"${BUILD_COMMAND[@]}"

echo "Done: ${IMAGE_REF}"
