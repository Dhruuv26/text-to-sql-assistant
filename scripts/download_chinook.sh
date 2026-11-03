#!/usr/bin/env bash
# Chinook sample DB (public, MIT-licensed): https://github.com/lerocha/chinook-database
set -euo pipefail
mkdir -p data
curl -sSL -o data/chinook.sqlite \
  https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite
