#!/bin/bash
for i in 1 2 3 4; do
  python3 -u /tmp/v3/gen_arc.py && [ -f /tmp/v3/honesty_run/arc.json ] && exit 0
  echo "$(date +%H:%M:%S) arc attempt $i failed, retrying" >> /tmp/v3/honesty_arc.log
  sleep 20
done
exit 1
