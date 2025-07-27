from db.connection import get_db
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.json")

with open(CONFIG_PATH, encoding='utf-8') as f:
    CONFIG = json.load(f)

FIELDS = CONFIG['fields']

def init_db(table_name = "energy_usage"):
    base_columns = {
        'record_date': 'TEXT PRIMARY KEY',
    }

    type_map = {
        'number': 'REAL',
        'text': 'TEXT',
    }

    for field in FIELDS:
        name = field['name']
        col_type = type_map.get(field.get("type", "number"), "TEXT")
        base_columns[name] = col_type

    cols_sql = ',\n    '.join(f"{col} {typ}" for col, typ in base_columns.items())
    create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {cols_sql}\n)"

    with get_db() as conn:
        c = conn.cursor()
        c.execute(create_table_sql)

        # Add any missing columns
        c.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in c.fetchall()}

        for col, col_type in base_columns.items():
            if col not in existing_cols:
                c.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")
