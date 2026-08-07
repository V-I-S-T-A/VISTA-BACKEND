#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PYEOF'
import os, time, sys
import psycopg
for attempt in range(30):
    try:
        psycopg.connect(
            dbname=os.environ.get("DB_NAME"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            host=os.environ.get("DB_HOST", "db"),
            port=os.environ.get("DB_PORT", "5432"),
        ).close()
        print("Database is up.")
        sys.exit(0)
    except Exception as e:
        print(f"DB not ready yet ({attempt+1}/30): {e}")
        time.sleep(2)
print("Database never became available.")
sys.exit(1)
PYEOF

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn vista.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120