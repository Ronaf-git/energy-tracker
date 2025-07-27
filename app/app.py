from flask import Flask, render_template, request, redirect, url_for, send_file , get_flashed_messages ,flash
from datetime import date
import os
import pandas as pd
from pandas.tseries.offsets import DateOffset
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

def generate_pivot_summary(df_resampled, view):
    """
    df_resampled : DataFrame avec valeurs brutes resamplées (ex : moyennes journalières, hebdo, mensuelles)
    view : 'daily', 'weekly', 'monthly', 'yearly'
    
    Retourne un DataFrame résumé avec colonnes :
    - Consommation courante (diff entre dernière et avant-dernière période)
    - Consommation précédente (diff entre avant-dernière et avant-avant-dernière)
    - Différence entre ces 2 consommations (valeur et %)
    - Moyenne mobile annuelle adaptée à la vue
    - Différence vs moyenne mobile (valeur et %)
    - Consommation même période année précédente
    - Différence vs même période année précédente (valeur et %)
    """

    if len(df_resampled) < 2:
        return pd.DataFrame(), []    # Pas assez de données

    # Index des périodes courante et précédente
    current_idx = df_resampled.index[-1]
    previous_idx = df_resampled.index[-2]

    # Date équivalente année précédente (ajustement selon la vue)
    last_year_idx = current_idx - DateOffset(years=1)

    # Trouver la consommation à la même période l'année précédente
    if last_year_idx in df_resampled.index:
        last_year_value = df_resampled.loc[last_year_idx]
    else:
        # Trouve la date la plus proche
        pos = df_resampled.index.get_indexer([last_year_idx], method='nearest')[0]
        last_year_value = df_resampled.iloc[pos]

    # Format des dates pour affichage
    if view == 'daily':
        fmt = "%d/%m/%Y"
    elif view == 'weekly':
        fmt = "Semaine du %d/%m/%Y"
    elif view == 'monthly':
        fmt = "%B %Y"
    elif view == 'yearly':
        fmt = "%Y"
    else:
        fmt = "%Y-%m-%d"

    label_current = current_idx.strftime(fmt)
    label_previous = previous_idx.strftime(fmt)
    label_last_year = last_year_idx.strftime(fmt)

    # Moyenne mobile annuelle (fenêtre adaptée)
    window = {'daily': 365, 'weekly': 52, 'monthly': 12, 'yearly': 1}.get(view, 52)
    moving_avg = df_resampled.rolling(window=window, min_periods=1).mean().iloc[-1]

    current = df_resampled.loc[current_idx]
    previous = df_resampled.loc[previous_idx]

    kpis = []
    rows = []
    for col in df_resampled.columns:
        val_current = current[col]
        val_previous = previous[col]
        val_diff = val_current - val_previous
        val_diff_pct = (val_diff / val_previous * 100) if val_previous != 0 else None

        val_diff_vs_avg = val_current - moving_avg[col]
        val_diff_vs_avg_pct = (val_diff_vs_avg / moving_avg[col] * 100) if moving_avg[col] != 0 else None

        val_last_year = last_year_value[col]
        val_diff_vs_last_year = val_current - val_last_year
        val_diff_vs_last_year_pct = (val_diff_vs_last_year / val_last_year * 100) if val_last_year != 0 else None

        row = {
            'typeNRJ': col.replace('_', ' ').capitalize(),
            f'{label_current}': f"{val_current:.2f}",
            f'{label_previous}': f"{val_previous:.2f}",
            f'{label_current} ./. {label_previous}': f"{val_diff:+.2f} ({val_diff_pct:+.1f}%)" if val_diff_pct is not None else f"{val_diff:+.2f}",
            f'{label_last_year}': f"{val_last_year:.2f}",
            f'{label_current} ./. {label_last_year}': f"{val_diff_vs_last_year:+.2f} ({val_diff_vs_last_year_pct:+.1f}%)" if val_diff_vs_last_year_pct is not None else f"{val_diff_vs_last_year:+.2f}",
            'Moyenne mobile annuelle': f"{moving_avg[col]:.2f}",
            f'{label_current} ./. Moyenne': f"{val_diff_vs_avg:+.2f} ({val_diff_vs_avg_pct:+.1f}%)" if val_diff_vs_avg_pct is not None else f"{val_diff_vs_avg:+.2f}",
        }
        rows.append(row)

        # Génération des KPIs
        kpis.append({
                'typeNRJ': col.replace('_', ' ').capitalize(),
                'current': val_current,
                'avg': moving_avg[col],
                'delta_vs_avg': val_diff_vs_avg,
                'delta_vs_avg_pct': val_diff_vs_avg_pct,
            })
    pivot_table = pd.DataFrame(rows)

    return pivot_table, kpis




def get_filtered_resampled_data():
    rows, columns = get_all_entries()
    df = pd.DataFrame(rows, columns=columns)

    if df.empty:
        return None, None, "No data available. Please enter at least one row."

    df['record_date'] = pd.to_datetime(df['record_date'], errors='coerce')
    df = df.dropna(subset=['record_date'])
    df = df.sort_values('record_date').reset_index(drop=True)
    df.set_index('record_date', inplace=True)

    # Identify numeric and non-numeric columns
    numeric_fields = [f['name'] for f in FIELDS if f.get('type', 'number') == 'number']
    non_numeric_fields = [col for col in df.columns if col not in numeric_fields]

    # Filter by date from request args
    start_date = pd.to_datetime(request.args.get('start_date'), errors='coerce')
    end_date = pd.to_datetime(request.args.get('end_date'), errors='coerce')

    if pd.isna(start_date):
        start_date = df.index.min()
    if pd.isna(end_date):
        end_date = df.index.max()

    # Filter original df by date range
    df_filtered = df.loc[start_date:end_date]

    # Numeric data handling
    df_numeric = df_filtered[numeric_fields].copy()
    df_daily = df_numeric.resample('D').interpolate(method='linear')

    view = request.args.get('view', 'weekly').lower()
    resample_rule = {'daily': 'D', 'weekly': 'W', 'monthly': 'ME', 'yearly': 'YE'}.get(view, 'D')
    df_resampled = df_daily.resample(resample_rule).mean()

    data_type = request.args.get('data_type', 'all')
    if data_type == 'all':
        df_diff = df_resampled.diff()
    else:
        if data_type not in df_resampled.columns:
            return None, None, f"Data type '{data_type}' not found."
        df_diff = df_resampled[[data_type]].diff()

    if len(df_resampled) < 2:
        df_diff = df_diff.fillna(df_resampled)

    # Non-numeric data filtered by date, no resampling
    df_non_numeric_filtered = df_filtered[non_numeric_fields]

    return df_diff, df_non_numeric_filtered, None


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
    df_diff, df_non_numeric, error = get_filtered_resampled_data()
    if error:
        flash(error)
        return redirect(url_for('index'))
    
    # pivot summary & KPIs
    view = request.args.get('view', 'weekly').lower()
    pivot_df, kpis = generate_pivot_summary(df_diff, view)

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
    plt.title(f'Variation ({request.args.get("view", "weekly").capitalize()})')
    plt.legend()
    plt.tight_layout()

    # Encode plot
    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    # table logic
    # df_diff.reset_index() contient les données numériques différenciées, index = date
    df_numeric_diff = df_diff.reset_index()

    # df_non_numeric contient les colonnes non numériques filtrées (index = date)
    # On veut faire un merge en left join sur 'record_date'
    # Reset index de df_non_numeric pour que la date soit une colonne
    df_non_numeric_reset = df_non_numeric.reset_index()

    # Merge avec left join sur 'record_date' (ou index en reset)
    df_merged = pd.merge(df_numeric_diff, df_non_numeric_reset, on='record_date', how='left')

    # Interpolation descendante (forward fill) des colonnes non numériques
    # Attention: seules les colonnes non numériques doivent être forward fill ici
    # Option pour activer le nouveau comportement de downcasting et ne plus avoir le warning
    pd.set_option('future.no_silent_downcasting', True)
    non_numeric_cols = df_non_numeric_reset.columns.difference(['record_date'])
    df_merged[non_numeric_cols] = df_merged[non_numeric_cols].bfill().infer_objects()

    # Render
    return render_template(
        'data.html',
        tables=[df_merged.to_html(classes='data', index=False)],
        pivot_table=pivot_df.to_html(classes='pivot-table', index=False),
        plot_url=plot_url,
        fields=FIELDS,
        download_token=token,
        kpis=kpis
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
