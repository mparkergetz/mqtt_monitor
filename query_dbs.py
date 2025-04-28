from flask import Flask, render_template, jsonify, redirect, url_for, g
import sqlite3, json
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)
app.config['DATABASES'] = {
    'sensors': 'sensor_data.db',
    'events':  'system_events.db'
}

def get_db(db_key):
    """Get or open a sqlite3 connection stored on `g`."""
    attr = f'_db_{db_key}'
    if not hasattr(g, attr):
        conn = sqlite3.connect(
            app.config['DATABASES'][db_key],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        conn.row_factory = sqlite3.Row
        setattr(g, attr, conn)
    return getattr(g, attr)

@app.teardown_appcontext
def close_dbs(exc):
    """Close any open sqlite3 connections on teardown."""
    for key in list(g):
        if key.startswith('_db_'):
            g.pop(key).close()

def query_db(db_key, sql, args=(), one=False):
    """Execute SQL and return rows as sqlite3.Row (dict‐like)."""
    cur = get_db(db_key).execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows and one else rows) if one else rows

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    # 1) fetch station list
    stations = [r['station'] for r in query_db('sensors',
                     'SELECT DISTINCT station FROM sensor_data')]
    # 2) fetch all three payloads
    weather_data = get_weather_data(stations)
    alerts_data  = get_alerts(limit=500)
    status_data  = get_camera_status()
    return render_template(
        'dashboard.html',
        stations=stations,
        weather_data=weather_data,
        alerts_data=alerts_data,
        camera_status=status_data['cameras'],
        station_last_seen=status_data['station_last_seen']
    )

@app.route('/api/weather/<station>')
def api_weather(station):
    return jsonify(get_weather_data([station])[station])

@app.route('/api/camera_status')
def api_camera_status():
    return jsonify(get_camera_status())

def get_weather_data(stations, limit=None):
    """Return { station: { field: [(ts, val), …] } }."""
    sql = """
      SELECT timestamp, field, value
        FROM sensor_data
       WHERE station = ?
    """
    # append ORDER and optional LIMIT
    sql += ' ORDER BY timestamp ASC' + (f' LIMIT {limit}' if limit else '')
    out = {}
    for st in stations:
        rows = query_db('sensors', sql, (st,))
        tmp = defaultdict(list)
        for r in rows:
            tmp[r['field']].append((r['timestamp'], r['value']))
        out[st] = dict(tmp)
    return out

def get_alerts(limit=500):
    """Return [(formatted_ts, message), …]."""
    rows = query_db('events',
        'SELECT timestamp, message FROM alerts '
        'ORDER BY timestamp DESC LIMIT ?',
        (limit,)
    )
    alerts = []
    for r in rows:
        ts = r['timestamp']
        try:
            ts = datetime.fromisoformat(ts).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
        alerts.append((ts, r['message']))
    return alerts

def get_camera_status():
    """
    - Pull last 1,000 system_events whose message is JSON
    - group by station→camera, keeping only the newest timestamp
    - record per‐station last_seen
    """
    rows = query_db('events', """
      SELECT timestamp, station, message
        FROM system_events
       WHERE message LIKE '{%%'
       ORDER BY timestamp DESC
       LIMIT 1000
    """)
    cams = defaultdict(dict)
    last_seen = {}

    for r in rows:
        ts, st, msg = r['timestamp'], r['station'], r['message']
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            continue

        cam_id = data.get('camera')
        if not cam_id:
            continue

        dt = datetime.fromisoformat(ts)
        # update station_last_seen
        if st not in last_seen or dt > last_seen[st]:
            last_seen[st] = dt

        # update per‐camera if newer
        prev = cams[st].get(cam_id)
        prev_dt = datetime.fromisoformat(prev['timestamp']) if prev else None
        if not prev_dt or dt > prev_dt:
            data['timestamp'] = ts
            cams[st][cam_id] = data

    return {
        'cameras': cams,
        'station_last_seen': {
            st: dt.isoformat() for st, dt in last_seen.items()
        }
    }

if __name__ == '__main__':
    app.run(debug=True, port=5000)
