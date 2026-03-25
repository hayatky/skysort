#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
pnpm --filter @skysort/web dev
