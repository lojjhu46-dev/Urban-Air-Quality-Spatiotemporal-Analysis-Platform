#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  DATABASE_URL
  DEEPSEEK_API_KEY
)

if [[ "${DATASET_STORAGE_MODE:-local}" == "supabase" ]]; then
  required_vars+=(
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    SUPABASE_STORAGE_BUCKET
  )
fi

missing=()
for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "Missing required environment variables:" >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 2
fi

export DATASET_STORAGE_MODE="${DATASET_STORAGE_MODE:-local}"
export WORKER_POLL_SECONDS="${WORKER_POLL_SECONDS:-5}"

python -m src.worker
