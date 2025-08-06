from flask import Flask, render_template, request, redirect, url_for, send_file, get_flashed_messages, flash
from datetime import date
import os
import io
import uuid
import json
import pandas as pd


# 🔄 Import des fonctions dédiées
from utils.processing import get_filtered_resampled_data, sanitize_number
from utils.pivot import generate_pivot_summary
from utils.plotting import generate_plot_image 
from db.schema import init_db
from db.crud import get_all_entries, upsert_entry, export_table_to_csv, delete_entry

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
with open(CONFIG_PATH, encoding='utf-8') as f:
    CONFIG = json.load(f)


# 🔄 Configuration
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data") 
FIELDS = CONFIG['fields']
FIELD_NAMES = [f["name"] for f in FIELDS]
DB_PATH = os.path.join(DATA_DIR, "energy.db")
CSV_PATH = os.path.join(DATA_DIR, "energy.csv")

app = Flask(__name__)
app.secret_key = os.urandom(24)
data_cache = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    messages = get_flashed_messages()
    message = messages[0] if messages else None

    if request.method == 'POST':
        today = request.form.get('record_date')
        if not today or today.strip() == '':
            today = date.today().isoformat()

        values = {}
        for field in FIELDS:
            name = field['name']
            value = request.form.get(name)
            if value and value.strip():
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
    df_diff, df_non_numeric, error = get_filtered_resampled_data()
    if error:
        flash(error)
        return redirect(url_for('index'))

    min_date = df_diff.index.min().date().isoformat()  # 'YYYY-MM-DD'
    max_date = df_diff.index.max().date().isoformat()


    view = request.args.get('view', 'weekly').lower()
    data_type = request.args.get('data_type', 'all')

    # 🔄 Résumé et KPIs
    pivot_df, kpis = generate_pivot_summary(df_diff, view)

    # 🔄 Stockage temporaire pour téléchargement
    token = str(uuid.uuid4())
    data_cache[token] = df_diff.copy()

    # 🔄 Graphique avec helper
    plot_url = generate_plot_image(df_diff, data_type, view)

    # 🔄 Fusion des données numériques différenciées et non numériques
    df_numeric_diff = df_diff.reset_index()
    df_non_numeric_reset = df_non_numeric.reset_index()

    pd.set_option('future.no_silent_downcasting', True)
    non_numeric_cols = df_non_numeric_reset.columns.difference(['record_date'])

    df_merged = pd.merge(df_numeric_diff, df_non_numeric_reset, on='record_date', how='left')
    df_merged[non_numeric_cols] = df_merged[non_numeric_cols].bfill().infer_objects()

    return render_template(
        'data.html', content_type='text/html; charset=utf-8',
        tables=[df_merged.to_html(classes='data', index=False)],
        pivot_table=pivot_df.to_html(classes='pivot-table', index=False),
        plot_url=plot_url,
        fields=FIELDS,
        download_token=token,
        kpis=kpis,
        min_date=min_date,
        max_date=max_date,
    )

@app.route('/download_xlsx')
def download_xlsx():
    token = request.args.get('token')
    if not token or token not in data_cache:
        return "Invalid or expired download token", 400

    df = data_cache.get(token)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Données')
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
            for row in updated_rows:
                record_date = row.get('record_date')
                if not record_date:
                    continue
                if row.get('_delete'):
                    delete_entry(record_date)
                else:
                    data = {k: v for k, v in row.items() if k not in ('record_date', '_delete')}
                    upsert_entry(record_date, data)
            export_table_to_csv()
        except Exception as e:
            return f"Failed to save: {e}"

        return redirect(url_for('edit_db'))

    rows, columns = get_all_entries()
    dict_rows = [dict(zip(columns, row)) for row in rows]
    headers = ['record_date'] + [f['name'] for f in FIELDS if f['name'] in columns]
    return render_template('edit.html', headers=headers, rows=dict_rows, fields=FIELDS)

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=8080)
