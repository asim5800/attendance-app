#!/usr/bin/env python3
"""
Simple Attendance Tracking Web Server
------------------------------------

This script runs a basic HTTP server using Python's built-in `http.server` module.
It serves static files, handles API requests for recording attendance punches,
and provides a minimal admin interface with login and CSV export functionality.
Data is stored in an SQLite database (`attendance.db`). The server does not
depend on any external Python packages, making it suitable for environments
without internet access.

Usage:
    python3 server.py

The server will listen on http://localhost:8000 by default. You can set the
PORT environment variable to change the port.
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import sqlite3
import os
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import uuid

# Directory configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DB_PATH = os.path.join(BASE_DIR, 'attendance.db')

# In-memory session store: maps session_id to True if admin is authenticated
sessions = {}


def init_db():
    """Create the attendance table if it does not exist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            latitude REAL,
            longitude REAL
        );
        """
    )
    conn.commit()
    conn.close()


class AttendanceHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler for the attendance application."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        # Serve static files from /static/
        if path.startswith('/static/'):
            return self.serve_static(path)
        # Root index page
        if path == '/' or path == '/index.html':
            return self.serve_template('index.html')
        # Admin login page
        if path == '/admin/login':
            return self.serve_template('admin_login.html')
        # Admin dashboard
        if path == '/admin':
            return self.serve_admin()
        # Admin logout
        if path == '/admin/logout':
            return self.handle_logout()
        # CSV export
        if path == '/admin/export':
            return self.handle_export()
        # 404 for all other paths
        self.send_error(404, 'Not Found')

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/punch':
            return self.handle_punch()
        if path == '/admin/login':
            return self.handle_login()
        # Unknown POST path
        self.send_error(404, 'Not Found')

    # Utility methods
    def serve_static(self, path):
        """Serve static assets located under the static directory."""
        # Map URL path to local filesystem path
        local_path = os.path.normpath(path.lstrip('/'))
        file_path = os.path.join(BASE_DIR, local_path)
        # Security check: ensure the file is within the static directory
        if not os.path.commonprefix([file_path, STATIC_DIR]) == STATIC_DIR:
            self.send_error(403, 'Forbidden')
            return
        return super().do_GET()

    def serve_template(self, template_name):
        """Serve an HTML template without any templating engine."""
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            self.send_error(404, 'Template not found')
            return
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def get_session_id(self):
        """Retrieve session_id from request cookies, if present."""
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            cookies = cookie_header.split(';')
            for cookie in cookies:
                cookie = cookie.strip()
                if cookie.startswith('session_id='):
                    return cookie.split('=', 1)[1]
        return None

    def is_authenticated(self):
        """Check if an admin session is authenticated."""
        session_id = self.get_session_id()
        return bool(session_id and sessions.get(session_id))

    def serve_admin(self):
        """Render and serve the admin dashboard. Redirect to login if not authenticated."""
        if not self.is_authenticated():
            self.send_response(302)
            self.send_header('Location', '/admin/login')
            self.end_headers()
            return
        # Pull attendance records from DB (descending by timestamp)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            'SELECT id, employee_id, action, timestamp, latitude, longitude '
            'FROM attendance ORDER BY timestamp DESC'
        )
        records = cur.fetchall()
        conn.close()
        # Build table rows
        rows = []
        for rec_id, employee_id, action, ts, lat, lon in records:
            lat_display = lat if lat is not None else '-'
            lon_display = lon if lon is not None else '-'
            rows.append(
                f'<tr>'
                f'<td>{rec_id}</td>'
                f'<td>{employee_id}</td>'
                f'<td>{action}</td>'
                f'<td>{ts}</td>'
                f'<td>{lat_display}</td>'
                f'<td>{lon_display}</td>'
                f'</tr>'
            )
        rows_html = ''.join(rows)
        # Load admin template and inject rows into placeholder
        template_path = os.path.join(TEMPLATES_DIR, 'admin.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('<!-- Records will be injected by the server -->', rows_html)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def handle_punch(self):
        """API endpoint to record a punch action (in/out) with geolocation."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'message': 'Invalid JSON.'}).encode('utf-8'))
            return
        employee_id = data.get('employee_id')
        action = data.get('action')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        if not employee_id or action not in ('in', 'out'):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'message': 'Invalid payload.'}).encode('utf-8'))
            return
        timestamp = datetime.utcnow().isoformat()
        # Insert record into database
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO attendance (employee_id, action, timestamp, latitude, longitude) VALUES (?, ?, ?, ?, ?)',
            (employee_id, action, timestamp, latitude, longitude)
        )
        conn.commit()
        conn.close()
        # Respond success
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'success': True, 'message': 'Punch recorded successfully.'}).encode('utf-8'))

    def handle_login(self):
        """Process admin login. Set a session cookie on successful authentication."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        params = parse_qs(body.decode('utf-8'))
        username = params.get('username', [''])[0]
        password = params.get('password', [''])[0]
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if username == admin_username and password == admin_password:
            session_id = str(uuid.uuid4())
            sessions[session_id] = True
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.send_header('Set-Cookie', f'session_id={session_id}; HttpOnly; Path=/')
            self.end_headers()
        else:
            # Redirect back to login page with error query parameter
            self.send_response(302)
            self.send_header('Location', '/admin/login?error=1')
            self.end_headers()

    def handle_logout(self):
        """Log out the admin by clearing session cookie and memory."""
        session_id = self.get_session_id()
        if session_id and session_id in sessions:
            del sessions[session_id]
        self.send_response(302)
        # Expire the cookie
        self.send_header('Set-Cookie', 'session_id=deleted; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/')
        self.send_header('Location', '/admin/login')
        self.end_headers()

    def handle_export(self):
        """Export attendance records as a CSV file. Admin only."""
        if not self.is_authenticated():
            self.send_response(302)
            self.send_header('Location', '/admin/login')
            self.end_headers()
            return
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT employee_id, action, timestamp, latitude, longitude FROM attendance ORDER BY timestamp')
        rows = cur.fetchall()
        conn.close()
        # Build CSV text
        csv_lines = ['Employee ID,Action,Timestamp (UTC),Latitude,Longitude']
        for emp_id, action, ts, lat, lon in rows:
            lat_val = '' if lat is None else lat
            lon_val = '' if lon is None else lon
            csv_lines.append(f'{emp_id},{action},{ts},{lat_val},{lon_val}')
        csv_data = '\n'.join(csv_lines)
        filename = f'attendance_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.csv'
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(csv_data.encode('utf-8'))


def run():
    init_db()
    port = int(os.environ.get('PORT', 8000))
    httpd = HTTPServer(('0.0.0.0', port), AttendanceHandler)
    print(f"Serving attendance app on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nServer shutting down...')
        httpd.server_close()


if __name__ == '__main__':
    run()