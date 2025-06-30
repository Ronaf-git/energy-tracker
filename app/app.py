from flask import Flask, render_template, request, redirect , url_for
import sqlite3
from datetime import date
import os
import csv
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

def sanitize_number(value):
    if value:
        return float(value.replace(',', '.'))
    return None

app = Flask(__name__)

DATA_DIR = "/data"
DB_PATH = os.path.join(DATA_DIR, "energy.db")
CSV_PATH = os.path.join(DATA_DIR, "energy.csv")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS energy_usage (
                record_date TEXT PRIMARY KEY,
                gaz REAL,
                elect_jour REAL,
                elect_nuit REAL,
                eau REAL,
                option1 REAL,
                option2 REAL,
                comment TEXT
            )
        ''')
        conn.commit()

def update_csv(today, gaz, elect_jour, elect_nuit, eau, option1=None, option2=None, comment=None):
    rows = []
    found = False

    # Read existing CSV if exists
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['record_date'] == today:
                    row.update({
                        'gaz': gaz,
                        'elect_jour': elect_jour,
                        'elect_nuit': elect_nuit,
                        'eau': eau,
                        'option1': option1,
                        'option2': option2,
                        'comment': comment
                    })
                    found = True
                rows.append(row)

    if not found:
        rows.append({
            'record_date': today,
            'gaz': gaz,
            'elect_jour': elect_jour,
            'elect_nuit': elect_nuit,
            'eau': eau,
            'option1': option1,
            'option2': option2,
            'comment': comment
        })

    # Write updated CSV
    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames = ['record_date', 'gaz', 'elect_jour', 'elect_nuit', 'eau', 'option1', 'option2', 'comment'])
        writer.writeheader()
        writer.writerows(rows)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        today = date.today().isoformat()
        gaz = sanitize_number(request.form['gaz'])
        elect_jour = sanitize_number(request.form['elect_jour'])
        elect_nuit = sanitize_number(request.form['elect_nuit'])
        eau = sanitize_number(request.form['eau'])
        option1 = request.form.get('option1') or None
        option2 = request.form.get('option2') or None
        comment = request.form.get('comment') or None

        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO energy_usage (record_date, gaz, elect_jour, elect_nuit, eau, option1, option2, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_date) DO UPDATE SET
                    gaz=excluded.gaz,
                    elect_jour=excluded.elect_jour,
                    elect_nuit=excluded.elect_nuit,
                    eau=excluded.eau,
                    option1=excluded.option1,
                    option2=excluded.option2,
                    comment=excluded.comment
            ''', (today, gaz, elect_jour, elect_nuit, eau, option1, option2, comment))
            conn.commit()

        update_csv(today, gaz, elect_jour, elect_nuit, eau, option1, option2, comment)

    return render_template('form.html')

@app.route('/data')
def show_data():
    if not os.path.exists(CSV_PATH):
        return "No data available yet."

    # Read CSV with automatic delimiter detection if needed
    with open(CSV_PATH, 'r', newline='') as f:
        sample = f.read(1024)  # read a bit of the file for sniffing
        f.seek(0)  # rewind after reading sample
        dialect = csv.Sniffer().sniff(sample)
        delimiter = dialect.delimiter

    df = pd.read_csv(CSV_PATH, delimiter=delimiter)

    # Ensure 'record_date' exists
    if 'record_date' not in df.columns:
        return "CSV missing 'record_date' column."

    # Convert to datetime and sort
    df['record_date'] = pd.to_datetime(df['record_date'])
    df = df.sort_values('record_date')

    # Get user inputs with defaults
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    view = request.args.get('view', 'daily')
    data_type = request.args.get('data_type', 'all')

    if data_type == 'all':
        # Select all relevant columns for diff calculation
        columns_to_plot = ['gaz', 'elect_jour', 'elect_nuit', 'eau']
        df_diff = df[columns_to_plot].diff()
    else:
        # Make sure the selected column exists in the DataFrame
        if data_type not in df.columns:
            return f"Data type '{data_type}' not found in data."
        df_diff = df[[data_type]].diff()

    # Set index to date for resampling and interpolation
    df.set_index('record_date', inplace=True)


    # Only keep numeric columns for aggregation
    df_numeric = df.select_dtypes(include='number')

    # Resample daily with linear interpolation to fill missing dates
    df_daily = df_numeric.resample('D').interpolate(method='linear')

    # Filter by date range if given
    if start_date:
        start_date = pd.to_datetime(start_date)
    else:
        start_date = df_daily.index.min()

    if end_date:
        end_date = pd.to_datetime(end_date)
    else:
        end_date = df_daily.index.max()

    df_filtered = df_daily.loc[start_date:end_date]

    # Resample according to user view selection
    if view == 'weekly':
        df_resampled = df_filtered.resample('W').mean()
    elif view == 'monthly':
        df_resampled = df_filtered.resample('M').mean()
    elif view == 'yearly':
        df_resampled = df_filtered.resample('Y').mean()
    else:
        df_resampled = df_filtered  # daily

    df_resampled = df_resampled.reset_index()

    plt.figure(figsize=(10, 6))

    if data_type == 'all':
        columns_to_plot = ['gaz', 'elect_jour', 'elect_nuit', 'eau']
        for col in columns_to_plot:
            if col not in df_resampled.columns:
                continue
            df_diff = df_resampled[[col]].diff()
            plt.plot(df_resampled['record_date'], df_diff[col], marker='o', label=f'Δ {col}')
    else:
        if data_type not in df_resampled.columns:
            return f"Data type '{data_type}' not found in data."
        df_diff = df_resampled[[data_type]].diff()
        plt.plot(df_resampled['record_date'], df_diff[data_type], marker='o', label=f'Δ {data_type}')

    plt.xticks(rotation=45)
    plt.xlabel('Date')
    plt.ylabel('Change in Usage')
    plt.title(f'Change in {data_type} Usage ({view.capitalize()})')
    plt.legend()
    plt.tight_layout()

    # Save plot to PNG in memory
    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)

    plot_url = base64.b64encode(img.getvalue()).decode()

    # Render template with table and plot
    return render_template(
        'data.html',
        tables=[df_resampled.to_html(classes='data', index=False)],
        plot_url=plot_url
    )


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=5000)
