from flask import Flask, render_template, request, redirect, url_for, send_file , get_flashed_messages ,flash
from datetime import date
import os
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import json
import uuid
from db.schema import init_db
from db.crud import get_all_entries, upsert_entry,export_table_to_csv,delete_entry

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
app.secret_key = os.urandom(24)
data_cache = {}  

def get_filtered_resampled_data():
    rows, columns = get_all_entries()
    df = pd.DataFrame(rows, columns=columns)

    if df.empty:
        return None,"No data available. Please enter at least one row."

    df['record_date'] = pd.to_datetime(df['record_date'], errors='coerce')
    df = df.dropna(subset=['record_date'])
    df = df.sort_values('record_date').reset_index(drop=True)
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


@app.route('/', methods=['GET', 'POST'])
def index():
    messages = get_flashed_messages()
    message = messages[0] if messages else None

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

        upsert_entry(today, values)
        export_table_to_csv()
        return render_template('form.html', success=True, fields=FIELDS, message="Données envoyées avec succès!")

    return render_template('form.html', success=False, fields=FIELDS, message=message, default_date=date.today().isoformat())

@app.route('/data')
def show_data():
    df_diff, error = get_filtered_resampled_data()
    if error:
        flash(error)
        return redirect(url_for('index'))

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
def edit_db():
    if request.method == 'POST':
        updated_data = request.form.get('table_data')
        if not updated_data:
            return "No data submitted."

        try:
            updated_rows = json.loads(updated_data)
            print("Parsed JSON data:", updated_rows)

            for row in updated_rows:
                record_date = row.get('record_date')
                if not record_date:
                    continue  # skip if no date

                if row.get('_delete'):
                    # Perform deletion
                    delete_entry(record_date)
                else:
                    # Perform insert/update
                    data = {k: v for k, v in row.items() if k not in ('record_date', '_delete')}
                    upsert_entry(record_date, data)

            # Export after all operations
            export_table_to_csv()
            print("Database updated (with delete support).")

        except Exception as e:
            return f"Failed to save: {e}"

        return redirect(url_for('edit_db'))

    # GET request:
    rows, columns = get_all_entries()
    dict_rows = [dict(zip(columns, row)) for row in rows]

    headers = ['record_date'] + FIELD_NAMES
    headers = [h for h in headers if h in columns]

    return render_template('edit.html', headers=headers, rows=dict_rows, fields=FIELDS)

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=8080)
