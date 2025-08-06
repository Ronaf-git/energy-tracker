from db.connection import get_db
import csv

def upsert_entry(date_str, data: dict,table_name = "energy_usage",key_field = "record_date"):
    fields = list(data.keys())
    placeholders = ', '.join(['?'] * len(fields))
    columns = ', '.join(fields)
    updates = ', '.join([f"{f}=excluded.{f}" for f in fields])

    query = f'''
        INSERT INTO {table_name} (record_date, {columns})
        VALUES (?, {placeholders})
        ON CONFLICT({key_field}) DO UPDATE SET {updates}
    '''

    with get_db() as conn:
        conn.execute(query, [date_str] + [data[f] for f in fields])

def get_all_entries(table_name = "energy_usage", order_by = "record_date"):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table_name} ORDER BY {order_by} ASC")
        return cur.fetchall(), [desc[0] for desc in cur.description]

def export_table_to_csv(table_name = "energy_usage", csv_file_path = "../data/energy.csv"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        column_names = [desc[0] for desc in cursor.description]

        with open(csv_file_path, 'w', newline='') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(column_names)
            csv_writer.writerows(rows)

def delete_entry(record_date, table_name="energy_usage", key_field="record_date"):
    query = f"DELETE FROM {table_name} WHERE {key_field} = ?"
    with get_db() as conn:
        conn.execute(query, (record_date,))