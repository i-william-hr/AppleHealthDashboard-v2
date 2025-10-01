import sys
import os
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import threading
import time
from datetime import datetime, timedelta, timezone 
from flask import Flask, jsonify, request, Response, render_template, redirect, url_for
from werkzeug.utils import secure_filename

# --- CONFIGURATION ---
DB_FILE = 'health.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'zip'}

# --- GLOBAL STATUS VARIABLE ---
import_status = {
    "status": "idle",
    "message": "Awaiting new data upload."
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

# --- BACKGROUND IMPORT LOGIC ---
def run_full_import(zip_path):
    global import_status
    try:
        import_status["status"] = "running"
        import_status["message"] = "Extracting zip file..."
        xml_path = ""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if 'export.xml' in file_info.filename:
                    zip_ref.extract(file_info, path=app.config['UPLOAD_FOLDER'])
                    xml_path = os.path.join(app.config['UPLOAD_FOLDER'], file_info.filename)
                    break
        if not xml_path: raise ValueError("export.xml not found in the zip archive.")
        import_status["message"] = "Preparing database..."
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        record_count = parse_and_import(xml_path)
        import_status["status"] = "complete"
        import_status["message"] = f"Import complete! Processed {record_count:,} records. Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    except Exception as e:
        import_status["status"] = "error"
        import_status["message"] = f"An error occurred: {e}"
    finally:
        if os.path.exists(zip_path): os.remove(zip_path)
        if xml_path and os.path.exists(xml_path):
            parent_dir = os.path.dirname(xml_path)
            os.remove(xml_path)
            if parent_dir != app.config['UPLOAD_FOLDER']:
                 try: os.rmdir(parent_dir)
                 except OSError: pass

def parse_and_import(xml_path):
    global import_status
    init_db()
    context = ET.iterparse(xml_path, events=('end',))
    records_batch = []
    batch_size = 5000
    count = 0
    DATA_TYPES_TO_IMPORT = {
        'HKQuantityTypeIdentifierStepCount', 'HKQuantityTypeIdentifierActiveEnergyBurned', 'HKQuantityTypeIdentifierBasalEnergyBurned',
        'HKQuantityTypeIdentifierHeartRate', 'HKQuantityTypeIdentifierRestingHeartRate', 'HKQuantityTypeIdentifierWalkingHeartRateAverage',
        'HKQuantityTypeIdentifierHeartRateVariabilitySDNN', 'HKQuantityTypeIdentifierOxygenSaturation', 'HKQuantityTypeIdentifierRespiratoryRate',
        'HKQuantityTypeIdentifierBodyTemperature', 'HKQuantityTypeIdentifierBloodPressureSystolic', 'HKQuantityTypeIdentifierBloodPressureDiastolic',
        'HKCategoryTypeIdentifierSleepAnalysis',
    }
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        for event, elem in context:
            tag = elem.tag
            if tag == 'Record':
                record_type = elem.get('type')
                if record_type in DATA_TYPES_TO_IMPORT:
                    try:
                        if record_type == 'HKCategoryTypeIdentifierSleepAnalysis':
                            sleep_stage_type = elem.get('value')
                            start_date = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                            end_date = datetime.strptime(elem.get('endDate'), '%Y-%m-%d %H:%M:%S %z')
                            duration_minutes = (end_date - start_date).total_seconds() / 60
                            records_batch.append((sleep_stage_type, 'min', duration_minutes, start_date.isoformat()))
                        else:
                            value = float(elem.get('value'))
                            unit = elem.get('unit')
                            start_date = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                            records_batch.append((record_type, unit, value, start_date.isoformat()))
                        count += 1
                    except (ValueError, TypeError, AttributeError): pass
            elif tag == 'Workout':
                try:
                    energy_burned_elem = elem.find('TotalEnergyBurned')
                    if energy_burned_elem is not None:
                        value = float(energy_burned_elem.get('value'))
                        unit = energy_burned_elem.get('unit')
                        start_date = datetime.strptime(elem.get('startDate'), '%Y-%m-%d %H:%M:%S %z')
                        records_batch.append(('HKQuantityTypeIdentifierActiveEnergyBurned', unit, value, start_date.isoformat()))
                        count += 1
                except (ValueError, TypeError, AttributeError): pass
            if len(records_batch) >= batch_size:
                cursor.executemany('INSERT INTO health_data (record_type, unit, record_value, start_date) VALUES (?, ?, ?, ?)', records_batch)
                conn.commit()
                import_status["message"] = f"Importing... Processed {count:,} records."
                records_batch = []
            if tag in ['Record', 'Workout', 'ActivitySummary']: elem.clear()
        if records_batch:
            cursor.executemany('INSERT INTO health_data (record_type, unit, record_value, start_date) VALUES (?, ?, ?, ?)', records_batch)
            conn.commit()
    import_status["message"] = f"Finishing import... Processed a total of {count:,} records."
    return count

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT, record_type TEXT NOT NULL, unit TEXT,
                record_value REAL NOT NULL, start_date TEXT NOT NULL)''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_type_date ON health_data (record_type, start_date)')

# --- FLASK ROUTES ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files: return redirect(request.url)
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename): return redirect(request.url)
        if import_status["status"] == "running": return "An import is already in progress. Please wait.", 409
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        thread = threading.Thread(target=run_full_import, args=(save_path,))
        thread.start()
        return redirect(url_for('dashboard'))
    return render_template('upload.html')

@app.route('/api/import-status')
def get_import_status():
    return jsonify(import_status)

@app.route('/api/ack-status', methods=['POST'])
def acknowledge_status():
    global import_status
    if import_status['status'] in ['complete', 'error']:
        import_status['status'] = 'idle'
        import_status['message'] = 'Awaiting new data upload.'
    return jsonify({"success": True})

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    if not os.path.exists(DB_FILE): return jsonify([])
    data_type = request.args.get('type')
    days = int(request.args.get('days', 30))
    aggregate = request.args.get('aggregate')
    if not data_type: return jsonify({"error": "Missing 'type' parameter"}), 400
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    params = [data_type, start_date.isoformat()]
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if aggregate == 'sum':
            query = """SELECT date(start_date) as start_date, SUM(record_value) as record_value FROM health_data WHERE record_type = ? AND start_date >= ? GROUP BY date(start_date) ORDER BY start_date;"""
        elif aggregate == 'avg':
            query = """SELECT date(start_date) as start_date, AVG(record_value) as record_value FROM health_data WHERE record_type = ? AND start_date >= ? GROUP BY date(start_date) ORDER BY start_date;"""
        else:
            query = """SELECT start_date, record_value FROM health_data WHERE record_type = ? AND start_date >= ? ORDER BY start_date;"""
        cursor.execute(query, params)
        data = [dict(row) for row in cursor.fetchall()]
        return jsonify(data)

@app.route('/api/sleep')
def get_sleep_data():
    if not os.path.exists(DB_FILE): return jsonify({'labels': [], 'stages': {}})
    days = int(request.args.get('days', 30))
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    query = """
        SELECT date(start_date) as sleep_date, record_type, SUM(record_value) as total_minutes
        FROM health_data WHERE record_type IN ('HKCategoryValueSleepAnalysisAsleepDeep', 'HKCategoryValueSleepAnalysisAsleepCore', 'HKCategoryValueSleepAnalysisAsleepREM', 'HKCategoryValueSleepAnalysisAwake')
        AND start_date >= ? GROUP BY sleep_date, record_type ORDER BY sleep_date;"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, [start_date.isoformat()])
        sleep_stages = { 'HKCategoryValueSleepAnalysisAwake': {}, 'HKCategoryValueSleepAnalysisAsleepREM': {}, 'HKCategoryValueSleepAnalysisAsleepCore': {}, 'HKCategoryValueSleepAnalysisAsleepDeep': {},}
        dates = set()
        for row in cursor.fetchall():
            row_dict = dict(row)
            date, record_type, total_minutes = row_dict['sleep_date'], row_dict['record_type'], row_dict['total_minutes']
            if record_type in sleep_stages:
                sleep_stages[record_type][date] = total_minutes
                dates.add(date)
        sorted_dates = sorted(list(dates))
        return jsonify({'labels': sorted_dates, 'stages': sleep_stages})

@app.route('/api/summary')
def get_summary_data():
    if not os.path.exists(DB_FILE): return jsonify({})
    days = int(request.args.get('days', 90))
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    summary = {}
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT MIN(record_value) FROM health_data WHERE record_type = 'HKQuantityTypeIdentifierRestingHeartRate' AND start_date >= ?", [start_date.isoformat()])
        summary['lowest_rhr'] = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(record_value) FROM health_data WHERE record_type = 'HKQuantityTypeIdentifierRestingHeartRate' AND start_date >= ?", [start_date.isoformat()])
        summary['highest_rhr'] = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(daily_total) FROM (SELECT SUM(record_value) as daily_total FROM health_data WHERE record_type = 'HKQuantityTypeIdentifierStepCount' AND start_date >= ? GROUP BY date(start_date))", [start_date.isoformat()])
        summary['avg_steps'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT MAX(record_value) FROM health_data WHERE record_type = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN' AND start_date >= ?", [start_date.isoformat()])
        summary['highest_hrv'] = cursor.fetchone()[0]

        sleep_types = ['HKCategoryValueSleepAnalysisAsleepDeep', 'HKCategoryValueSleepAnalysisAsleepCore', 'HKCategoryValueSleepAnalysisAsleepREM']
        placeholders = ','.join('?' for _ in sleep_types)
        cursor.execute(f"SELECT AVG(daily_total) FROM (SELECT SUM(record_value) as daily_total FROM health_data WHERE record_type IN ({placeholders}) AND start_date >= ? GROUP BY date(start_date))", sleep_types + [start_date.isoformat()])
        summary['avg_sleep_minutes'] = cursor.fetchone()[0]
        
    return jsonify(summary)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    try:
        from waitress import serve
        print("Starting production server on http://0.0.0.0:8080")
        serve(app, host='0.0.0.0', port=8080)
    except ImportError:
        print("---\n[WARNING] 'waitress' is not installed. Falling back to the basic Flask server.")
        print("For better performance, please run: pip install waitress\n---")
        print("Starting development server on http://0.0.0.0:8080")
        app.run(host='0.0.0.0', port=8080, debug=True)
