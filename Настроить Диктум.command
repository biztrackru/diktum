#!/bin/zsh

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/app/scripts/setup_local_mac.sh"
