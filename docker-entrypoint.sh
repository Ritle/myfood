#!/bin/sh
set -eu

alembic upgrade head
python -m app.commands.seed_foods
exec python -m app.main
