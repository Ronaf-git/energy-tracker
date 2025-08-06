# utils/processing.py
import os
import json
import pandas as pd
from flask import request
from db.crud import get_all_entries

# 🔽 Charger config.json directement
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json'))
with open(CONFIG_PATH, encoding='utf-8') as f:
    CONFIG = json.load(f)

FIELDS = CONFIG['fields']

def sanitize_number(value):
    if value:
        return float(value.replace(',', '.'))
    return None

def get_filtered_resampled_data():
    rows, columns = get_all_entries()
    df = pd.DataFrame(rows, columns=columns)

    if df.empty:
        return None, None, "No data available. Please enter at least one row."

    df['record_date'] = pd.to_datetime(df['record_date'], errors='coerce')
    df = df.dropna(subset=['record_date']).sort_values('record_date').reset_index(drop=True)
    df.set_index('record_date', inplace=True)

    numeric_fields = [f['name'] for f in FIELDS if f.get('type', 'number') == 'number']
    non_numeric_fields = [col for col in df.columns if col not in numeric_fields]

    # Parse user input
    start_date_input = request.args.get('start_date')
    end_date_input = request.args.get('end_date')

    # Convert to datetime safely
    start_date = pd.to_datetime(start_date_input, errors='coerce')
    end_date = pd.to_datetime(end_date_input, errors='coerce')

    # Get available date bounds from the DataFrame
    min_date = df.index.min()
    max_date = df.index.max()

    # Fallback if input is missing or invalid
    if pd.isna(start_date) or start_date < min_date:
        start_date = min_date

    if pd.isna(end_date) or end_date > max_date:
        end_date = max_date

    # Final safety check — ensure start_date <= end_date
    if start_date > end_date:
        return None, None, f"Invalid date range: start_date {start_date.date()} is after end_date {end_date.date()}."

    # Filter the DataFrame safely
    df_filtered = df.loc[start_date:end_date]

    df_numeric = df_filtered[numeric_fields].copy()
    df_daily = df_numeric.resample('D').interpolate(method='linear')

    view = request.args.get('view', 'weekly').lower()
    resample_rule = {'daily': 'D', 'weekly': 'W', 'monthly': 'ME', 'yearly': 'YE'}.get(view, 'D')
    df_resampled = df_daily.resample(resample_rule).mean()

    data_type = request.args.get('data_type', 'all')
    if data_type == 'all':
        df_diff = df_resampled.diff()
    elif data_type in df_resampled.columns:
        df_diff = df_resampled[[data_type]].diff()
    else:
        return None, None, f"Data type '{data_type}' not found."

    if len(df_resampled) < 2:
        df_diff = df_diff.fillna(df_resampled)

    df_non_numeric_filtered = df_filtered[non_numeric_fields]

    return df_diff, df_non_numeric_filtered, None
