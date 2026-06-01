#!/usr/bin/env bash
set -euo pipefail

registry="${REGISTRY:-sanfu.dockerhub.top}"
project="${PROJECT:-langgenius}"
repository="${REPOSITORY:-dify-api}"
tag="${TAG:-1.11.1-sanfu-log-20260529-3}"
username="${HARBOR_USERNAME:-ljq82}"
image="${registry}/${project}/${repository}:${tag}"
commit_sha="$(git rev-parse --short HEAD 2>/dev/null || echo 2058186f22)"
docker_config="$(mktemp -d)"

cleanup() {
  rm -rf "${docker_config}"
}
trap cleanup EXIT

if [[ -z "${HARBOR_PASSWORD:-}" ]]; then
  read -rsp "Harbor password: " HARBOR_PASSWORD
  echo
fi

export DOCKER_CONFIG="${docker_config}"

printf '%s\n' "${HARBOR_PASSWORD}" | docker login "${registry}" -u "${username}" --password-stdin
docker build --pull --build-arg COMMIT_SHA="${commit_sha}-sanfu-log" -f api/Dockerfile -t "${image}" api
docker push "${image}"

echo "Pushed image: ${image}"
