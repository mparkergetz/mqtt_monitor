#!/bin/bash
SENSOR_DB="sensor_data.db"
EVENT_DB="system_events.db"

check_db_exists() {
  if [ ! -f "$1" ]; then
    echo "Database '$1' not found!"
    exit 1
  fi
}

print_latest_sensor_data() {
  echo "---- Latest Sensor Readings (All Fields) ----"
  sqlite3 "$SENSOR_DB" <<EOF
.headers on
.mode column
SELECT * FROM sensor_data
WHERE timestamp = (SELECT MAX(timestamp) FROM sensor_data);
EOF
  echo ""
}

print_latest_event_data() {
  echo "---- Latest Status Updates ----"
  sqlite3 "$EVENT_DB" <<EOF
.headers on
.mode column
SELECT * FROM system_events ORDER BY timestamp DESC LIMIT 1;
EOF
  echo ""
}

print_latest_alert() {
  echo "---- Latest Alerts ----"
  sqlite3 "$EVENT_DB" <<EOF
.headers on
.mode column
SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 1;
EOF
  echo ""
}

check_db_exists "$SENSOR_DB"
check_db_exists "$EVENT_DB"

print_latest_sensor_data
print_latest_event_data
print_latest_alert