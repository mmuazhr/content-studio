#!/bin/sh
# Start Airflow standalone for content-studio — macOS-safe.
# Usage: sh scripts/start-airflow.sh   (from content-studio/)
#
# The OS exports below are REQUIRED on macOS: without them every
# gunicorn/scheduler worker segfaults instantly (macOS os_log is not
# fork-safe; diagnosed 2026-07-26, see docs/uat-checklist.md).
set -e
cd "$(dirname "$0")/.."

export AIRFLOW_HOME="$PWD/airflow_home"
export OS_ACTIVITY_MODE=disable
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export NO_PROXY="*"
# standalone spawns bare `airflow` subprocesses — venv must lead PATH
export PATH="$PWD/.venv/bin:$PATH"

# NOTE: airflow_home/airflow.cfg is gitignored. If you ever regenerate it,
# re-apply this or REST triggers from the dashboard will 403:
#   [api] auth_backends = airflow.api.auth.backend.basic_auth,airflow.api.auth.backend.session

if pgrep -f "airflow standalone" > /dev/null; then
  echo "airflow standalone already running (http://localhost:8080)"
  exit 0
fi

nohup .venv/bin/airflow standalone >> airflow_home/standalone.log 2>&1 &
echo "starting... log: airflow_home/standalone.log"
for i in $(seq 1 24); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null || true)
  if [ "$code" = "200" ]; then echo "healthy: http://localhost:8080 (admin password: airflow_home/standalone_admin_password.txt)"; exit 0; fi
  sleep 5
done
echo "did not become healthy in 120s — check airflow_home/standalone.log" >&2
exit 1
