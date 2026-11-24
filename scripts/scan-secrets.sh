#!/usr/bin/env bash
set -euo pipefail

version=8.30.1
archive="gitleaks_${version}_linux_x64.tar.gz"
checksum=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
scan_dir=$(mktemp -d)
trap 'rm -rf -- "$scan_dir"' EXIT

curl --fail --silent --show-error --location --retry 3 --max-time 60 \
  --output "$scan_dir/$archive" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${version}/${archive}"
printf '%s  %s\n' "$checksum" "$scan_dir/$archive" | sha256sum --check --status
tar --extract --gzip --file "$scan_dir/$archive" --directory "$scan_dir" gitleaks
"$scan_dir/gitleaks" git --redact=100 --no-banner --log-opts=--all .
