#!/bin/sh
# The one verification gate. Local runs and CI both go through this script.
set -eu

echo "--- ruff format --check"
ruff format --check .

echo "--- ruff check"
ruff check .

echo "--- mypy --strict"
mypy

echo "--- pytest"
pytest

echo "--- verification complete"
