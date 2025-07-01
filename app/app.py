from flask import Flask, render_template, request, redirect , url_for
import sqlite3
from datetime import date
import os
import csv
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import json

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, encoding='utf-8') as f:
    CONFIG = json.load(f)

# Extract constants and fields
DATA_DIR = CONFIG['constants']['DATA_DIR']
FIELDS = CONFIG['fields']
FIELD_NAMES = [f["name"] for f in FIELDS]
DB_PATH = os.path.join(DATA_DIR, "energy.db")
CSV_PATH = os.path.join(DATA_DIR, "energy.csv")

app = Flask(__name__)

def sanitize_number(value):
    if value:
        return float(value.replace(',', '.'))
    return None

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

        # Define base columns that always exist (e.g. record_date)
        base_columns = {
            'record_date': 'TEXT PRIMARY KEY',
        }

        # Get fields from your JSON config (assuming FIELDS is a list of dicts)
        # FIELDS example:
        # FIELDS = [
        #   {'name': 'gaz', 'type': 'number', 'required': True},
        #   {'name': 'elect_jour', 'type': 'number', 'required': True},
        #   ... etc ...
        # ]

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

def update_csv(today, **data):
    rows = []
    found = False

    # Ensure record_date is added
    data['record_date'] = today

    # Define all fieldnames including 'record_date'
    fieldnames = ['record_date'] + FIELD_NAMES

    # Read existing CSV if it exists
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['record_date'] == today:
                    row.update({k: data.get(k) for k in FIELD_NAMES})
                    found = True
                rows.append(row)

    # If today's entry wasn't found, append a new one
    if not found:
        rows.append(data)

    # Write the updated rows back to the CSV
    with open(CSV_PATH, 'w', newline='') as f:
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

        update_csv(today, **values)

    return render_template('form.html', fields=FIELDS)

@app.route('/data')
def show_data():
    if not os.path.exists(CSV_PATH):
        return "No data available yet."

    # --- Load and parse CSV ---
    with open(CSV_PATH, 'r', newline='') as f:
        sample = f.read(1024)
        f.seek(0)
        delimiter = csv.Sniffer().sniff(sample).delimiter
    df = pd.read_csv(CSV_PATH, delimiter=delimiter)

    if 'record_date' not in df.columns:
        return "CSV missing 'record_date' column."

    df['record_date'] = pd.to_datetime(df['record_date'], format="%Y-%m-%d", errors='coerce')
    df = df.dropna(subset=['record_date'])
    df = df.sort_values('record_date')
    df.set_index('record_date', inplace=True)

    # --- Filter columns based on config ---
    numeric_fields = [f['name'] for f in FIELDS if f.get('type', 'number') == 'number']
    df_numeric = df[numeric_fields].copy()

    # --- Fill in missing dates and interpolate ---
    df_daily = df_numeric.resample('D').interpolate(method='linear')

    # --- Get filters from query params ---
    start_date_raw = request.args.get('start_date')
    end_date_raw = request.args.get('end_date')

    start_date = pd.to_datetime(start_date_raw, errors='coerce')
    end_date = pd.to_datetime(end_date_raw, errors='coerce')

    if pd.isna(start_date):
        start_date = df_daily.index.min()
    if pd.isna(end_date):
        end_date = df_daily.index.max()

    if pd.isna(start_date) or pd.isna(end_date):
        return "No valid date range available."

    view = request.args.get('view', 'daily').lower()
    data_type = request.args.get('data_type', 'all')

    df_filtered = df_daily.loc[start_date:end_date]
    # --- Resampling ---
    resample_rule = {'daily': 'D', 'weekly': 'W', 'monthly': 'ME', 'yearly': 'YE'}.get(view, 'D')
    df_resampled = df_filtered.resample(resample_rule).mean()

    # --- Plotting ---
    plt.figure(figsize=(10, 6))

    if data_type == 'all':
        for col in numeric_fields:
            if col in df_resampled:
                df_diff = df_resampled[[col]].diff()
                # Fill NaN (first row) with original values if less than 2 points
                if len(df_resampled) < 2:
                    df_diff[col] = df_diff[col].fillna(df_resampled[col])
                plt.plot(df_resampled.index, df_diff[col], marker='o', label=f'Δ {col}')
    else:
        if data_type not in df_resampled.columns:
            return f"Data type '{data_type}' not found in data."
        df_diff = df_resampled[[data_type]].diff()
        if len(df_resampled) < 2:
            df_diff[data_type] = df_diff[data_type].fillna(df_resampled[data_type])
        plt.plot(df_resampled.index, df_diff[data_type], marker='o', label=f'Δ {data_type}')

    plt.xticks(rotation=45)
    plt.xlabel('Date')
    plt.ylabel('Unité d''oeuvre')
    plt.title(f'Variation en {data_type} - ({view.capitalize()})')
    plt.legend()
    plt.tight_layout()

    # --- Convert plot to base64 ---
    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    # --- Render ---
    return render_template(
        'data.html'
        ,tables=[df_resampled.reset_index().to_html(classes='data', index=False)]
        ,plot_url=plot_url
        ,fields=FIELDS
    )


if __name__ == '__main__':
    
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=5000)
