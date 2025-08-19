from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import csv
import io
import os
from datetime import datetime

"""
Attendance Tracking Web Application
----------------------------------

This Flask application provides a simple web interface for employees to punch in
and punch out from work. It captures the user's geolocation (latitude and
longitude) via the browser and records the timestamp on the server. An
administrator can log in to download attendance records as a CSV file. This
application uses a local SQLite database (attendance.db) to store records.

Usage:
    python app.py

The application will be served locally on http://localhost:5000. In production
environments, consider using a proper WSGI server (gunicorn) and host on a
platform that supports Python web apps.
"""

app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRET_KEY', 'replace-with-a-secure-random-string')

# Admin credentials (username: admin, password hashed)
# In a real deployment, store these in environment variables or a secure secrets
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))

# Database initialization
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'attendance.db')


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the SQLite database with the required table."""
    conn = get_db_connection()
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


# Ensure database is initialized when app starts
init_db()


@app.route('/')
def index():
    """
    Home page where employees enter their ID and punch in/out. The page uses
    JavaScript to obtain the user's location and send it to the server.
    """
    return render_template('index.html')


@app.route('/punch', methods=['POST'])
def punch():
    """
    Endpoint to record a punch action. Expects JSON data with employee_id,
    action ("in" or "out"), latitude, and longitude. The server records the
    current timestamp in ISO 8601 format (UTC) along with the provided data.
    Returns a JSON response indicating success or failure.
    """
    data = request.get_json()
    employee_id = data.get('employee_id')
    action = data.get('action')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not employee_id or not action:
        return jsonify({'success': False, 'message': 'Employee ID and action are required.'}), 400

    if action not in ['in', 'out']:
        return jsonify({'success': False, 'message': 'Invalid action specified.'}), 400

    timestamp = datetime.utcnow().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO attendance (employee_id, action, timestamp, latitude, longitude) VALUES (?, ?, ?, ?, ?)',
        (employee_id, action, timestamp, latitude, longitude)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Punch recorded successfully.'})


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """
    Admin login page. On POST, verify credentials and create a session. After
    successful login, redirect to the admin dashboard.
    """
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials', 'error')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')


@app.route('/admin')
def admin_dashboard():
    """
    Admin dashboard page. Requires admin to be logged in. Shows summary of
    attendance records and provides a link to export data.
    """
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM attendance ORDER BY timestamp DESC')
    records = cur.fetchall()
    conn.close()

    return render_template('admin.html', records=records)


@app.route('/admin/logout')
def admin_logout():
    """Logs out the admin by clearing the session and redirects to login."""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/export')
def export_csv():
    """
    Endpoint for admin to export attendance records as CSV. Requires admin
    authentication. Returns a CSV file as an attachment.
    """
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT employee_id, action, timestamp, latitude, longitude FROM attendance ORDER BY timestamp')
    data_rows = cur.fetchall()
    conn.close()

    # Create CSV in memory
    output = io.StringIO()
    csv_writer = csv.writer(output)
    csv_writer.writerow(['Employee ID', 'Action', 'Timestamp (UTC)', 'Latitude', 'Longitude'])
    for row in data_rows:
        csv_writer.writerow(row)
    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.csv'
    )


if __name__ == '__main__':
    # For development use only. Do not use app.run in production.
    app.run(host='0.0.0.0', port=5000, debug=True)