#!/bin/sh
# Run every topic, then find and crawl fund sites; embeddings fill alongside.
# Safe to rerun: each step skips what is already stored.
cd "$(dirname "$0")"
mkdir -p logs
.venv/bin/python embed.py --follow >> logs/embed.log 2>&1 &
EMBED=$!
for t in topics/[!_]*.yaml; do
    .venv/bin/python run.py "$t" >> logs/run.log 2>&1
done
.venv/bin/python funds.py discover >> logs/funds.log 2>&1
.venv/bin/python funds.py crawl >> logs/funds.log 2>&1
kill $EMBED
.venv/bin/python embed.py >> logs/embed.log 2>&1
