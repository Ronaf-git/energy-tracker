from flask import Flask, render_template, request, redirect, url_for, send_file
import sqlite3
from datetime import date
import os
import csv
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import json
import uuid


# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
with open(CONFIG_PATH, encoding='utf-8') as f:
    CONFIG = json.load(f)


# Extract constants and fields
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data") 
FIELDS = CONFIG['fields']
FIELD_NAMES = [f["name"] for f in FIELDS]
DB_PATH = os.path.join(DATA_DIR, "energy.db")
CSV_PATH = os.path.join(DATA_DIR, "energy.csv")

app = Flask(__name__)
data_cache = {}  # simple in-memory cache (can be replaced with Redis or Flask-Caching)

def get_filtered_resampled_data():
    if not os.path.exists(CSV_PATH):
        return None, "No data available."

    # Load CSV
    with open(CSV_PATH, 'r', newline='') as f:
        sample = f.read(1024)
        f.seek(0)
        delimiter = csv.Sniffer().sniff(sample).delimiter
    df = pd.read_csv(CSV_PATH, delimiter=delimiter)

    if 'record_date' not in df.columns:
        return None, "CSV missing 'record_date' column."

    df['record_date'] = pd.to_datetime(df['record_date'], errors='coerce')
    df = df.dropna(subset=['record_date'])
    df = df.sort_values('record_date')
    df.set_index('record_date', inplace=True)

    # Filter numeric fields
    numeric_fields = [f['name'] for f in FIELDS if f.get('type', 'number') == 'number']
    df_numeric = df[numeric_fields].copy()
    df_daily = df_numeric.resample('D').interpolate(method='linear')

    # Apply filters
    start_date = pd.to_datetime(request.args.get('start_date'), errors='coerce')
    end_date = pd.to_datetime(request.args.get('end_date'), errors='coerce')
    if pd.isna(start_date):
        start_date = df_daily.index.min()
    if pd.isna(end_date):
        end_date = df_daily.index.max()
    df_filtered = df_daily.loc[start_date:end_date]

    # Resample
    view = request.args.get('view', 'daily').lower()
    resample_rule = {'daily': 'D', 'weekly': 'W', 'monthly': 'ME', 'yearly': 'YE'}.get(view, 'D')
    df_resampled = df_filtered.resample(resample_rule).mean()

    # Diff logic
    data_type = request.args.get('data_type', 'all')
    if data_type == 'all':
        df_diff = df_resampled.diff()
    else:
        if data_type not in df_resampled.columns:
            return None, f"Data type '{data_type}' not found."
        df_diff = df_resampled[[data_type]].diff()

    if len(df_resampled) < 2:
        df_diff = df_diff.fillna(df_resampled)

    return df_diff, None

def sanitize_number(value):
    if value:
        return float(value.replace(',', '.'))
    return None
"""
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

        # Define base columns that always exist (e.g. record_date)
        base_columns = {
            'record_date': 'TEXT PRIMARY KEY',
        }

        # Map your JSON field types to SQL types:
        type_map = {
            'number': 'REAL',
            'text': 'TEXT',
            # add more if needed
        }

        # Combine base + fields from JSON for creating the table
        all_columns = dict(base_columns)  # start with base
        for f in FIELDS:
            col_name = f['name']
            sql_type = type_map.get(f.get('type', 'number'), 'TEXT')
            # comment fields are probably text, options likely numbers, etc
            all_columns[col_name] = sql_type

        # Build CREATE TABLE statement dynamically
        cols_sql = ',\n    '.join(f"{col} {typ}" for col, typ in all_columns.items())
        create_table_sql = f"CREATE TABLE IF NOT EXISTS energy_usage (\n    {cols_sql}\n)"

        c.execute(create_table_sql)
        conn.commit()

        # Now, check if any columns are missing (in case table existed before)
        c.execute("PRAGMA table_info(energy_usage)")
        existing_cols = {row[1] for row in c.fetchall()}

        # Add missing columns
        for col, typ in all_columns.items():
            if col not in existing_cols:
                alter_sql = f"ALTER TABLE energy_usage ADD COLUMN {col} {typ}"
                c.execute(alter_sql)
                print(f"Added missing column '{col}' to energy_usage table.")

        conn.commit()
"""
def update_csv(today, **data):
    rows = []
    found = False
    data['record_date'] = today
    original_fieldnames = set(data.keys())  # Will be updated with full field list

    # Read existing CSV if it exists
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            original_fieldnames.update(reader.fieldnames or [])
            for row in reader:
                if row['record_date'] == today:
                    # Only update fields in FIELD_NAMES
                    for field in FIELD_NAMES:
                        if field in data:
                            row[field] = data[field]
                    found = True
                rows.append(row)

    if not found:
        # If new row, fill all known fields (others will remain empty)
        row = {key: '' for key in original_fieldnames}
        row.update(data)
        rows.append(row)

    # Ensure consistent field order
    fieldnames = list(dict.fromkeys(['record_date'] + FIELD_NAMES + list(original_fieldnames)))

    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Get 'record_date' from form, default to today if missing or empty
        today = request.form.get('record_date')
        if not today or today.strip() == '':
            today = date.today().isoformat()

        values = {}
        for field in FIELDS:
            name = field['name']
            value = request.form.get(name)
            if value is not None and value.strip() != '':
                if field.get("type") == "text":
                    values[name] = value
                else:
                    values[name] = sanitize_number(value)
            else:
                values[name] = None
            """
            with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            placeholders = ", ".join(["?"] * len(FIELD_NAMES))
            columns = ", ".join(FIELD_NAMES)
            updates = ", ".join([f"{name}=excluded.{name}" for name in FIELD_NAMES])
            sql = f'''
                INSERT INTO energy_usage (record_date, {columns})
                VALUES (?, {placeholders})
                ON CONFLICT(record_date) DO UPDATE SET {updates}
            '''
            c.execute(sql, (today, *[values[name] for name in FIELD_NAMES]))
            conn.commit()
            """

        update_csv(today, **values)

    return render_template('form.html', success=True, fields=FIELDS)

@app.route('/data')
def show_data():
    df_diff, error = get_filtered_resampled_data()
    if error:
        return error

    #return dataset as token for download
    token = str(uuid.uuid4())
    data_cache[token] = df_diff.copy()

    # Plotting logic...
    plt.figure(figsize=(10, 6))
    data_type = request.args.get('data_type', 'all')
    if data_type == 'all':
        for col in df_diff.columns:
            plt.plot(df_diff.index, df_diff[col], label=f'Δ {col}')
    else:
        plt.plot(df_diff.index, df_diff[data_type], label=f'Δ {data_type}')

    plt.xticks(rotation=45)
    plt.xlabel('Date')
    plt.ylabel('Unité d\'œuvre')
    plt.title(f'Variation ({request.args.get("view", "daily").capitalize()})')
    plt.legend()
    plt.tight_layout()

    # Encode plot
    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    # Render
    return render_template(
        'data.html',
        tables=[df_diff.reset_index().to_html(classes='data', index=False)],
        plot_url=plot_url,
        fields=FIELDS,
        download_token=token
    )

@app.route('/download_xlsx')
def download_xlsx():
    token = request.args.get('token')

    if not token or token not in data_cache:
        return "Invalid or expired download token", 400
    
    df = data_cache.get(token)  # pop method if i want to delete my token after download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Données') #I keep my index to keep the date
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='reporting_energie.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/edit', methods=['GET', 'POST'])
def edit_csv():
    if not os.path.exists(CSV_PATH):
        return "CSV file not found."

    import json

    if request.method == 'POST':
        updated_data = request.form.get('table_data')
        if not updated_data:
            return "No data submitted."

        try:
            updated_rows = json.loads(updated_data)
            print("Données JSON parsées :", updated_rows)

            # Load original full data (to preserve untouched fields)
            with open(CSV_PATH, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                original_rows = list(reader)
                original_headers = reader.fieldnames or []

            merged_rows = []
            for i, updated_row in enumerate(updated_rows):
                original_row = original_rows[i] if i < len(original_rows) else {}
                merged_row = original_row.copy()
                merged_row.update(updated_row)  # Overwrite only the updated fields
                merged_rows.append(merged_row)

            with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=original_headers)
                writer.writeheader()
                writer.writerows(merged_rows)

            print("CSV mis à jour avec conservation des champs supprimés.")
        except Exception as e:
            return f"Failed to save: {e}"

        return redirect(url_for('edit_csv'))

    # GET request
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        original_headers = reader.fieldnames or []

        # Only show fields you want to edit
        headers = ['record_date'] + FIELD_NAMES
        headers = [h for h in headers if h in original_headers]

    return render_template("edit.html", headers=headers, rows=rows, fields=FIELDS)


if __name__ == '__main__':
    
    os.makedirs(DATA_DIR, exist_ok=True)
    # init_db()
    app.run(host='0.0.0.0', port=5000)
