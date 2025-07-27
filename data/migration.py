# migration mandatory to go from v0.3 or below to v0.4 or above
# must run from the data folder where the csv is and the db should be
import sqlite3
import csv

csv_file_path = 'energy.csv'  
table_name = 'energy_usage'

# Open CSV file
with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    headers = reader.fieldnames

    # Collect first few rows to infer types
    sample_rows = []
    for _ in range(5):
        try:
            sample_rows.append(next(reader))
        except StopIteration:
            break

    # Reset reader to read from start again
    csvfile.seek(0)
    reader = csv.DictReader(csvfile)

    # Infer column types 
    col_types = {}
    for header in headers:
        col_type = 'TEXT'  
        for row in sample_rows:
            val = row.get(header, "").strip()
            if val == "":
                continue
            try:
                float(val)
                col_type = 'REAL'
                break
            except ValueError:
                col_type = 'TEXT'
        col_types[header] = col_type

    # Connect to SQLite
    conn = sqlite3.connect('energy.db')
    cur = conn.cursor()

    # Create table with dynamic schema
    columns_def_parts = []
    for col in headers:
        col_def = f'"{col}" {col_types[col]}'
        if col == 'record_date':
            col_def += ' PRIMARY KEY'
        columns_def_parts.append(col_def)

    columns_def = ',\n  '.join(columns_def_parts)
    create_stmt = f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n  {columns_def}\n);'
    cur.execute(create_stmt)

    # Insert data
    insert_stmt = f'''
    INSERT INTO "{table_name}" ({", ".join(headers)})
    VALUES ({", ".join(["?" for _ in headers])})
    '''
    for row in reader:
        values = []
        for col in headers:
            val = row[col].strip()
            try:
                values.append(float(val) if col_types[col] == 'REAL' and val != '' else val)
            except ValueError:
                values.append(None)
        try:
            cur.execute(insert_stmt, values)
        except Exception as e:
            print(f"Error inserting row: {row} -> {e}")

    conn.commit()
    conn.close()

    print(f"Data imported into table '{table_name}' successfully.")
