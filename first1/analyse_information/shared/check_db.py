#!/usr/bin/env python3
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'analyzer.db')

print(f"Checking database: {DB_PATH}")
print(f"File exists: {os.path.exists(DB_PATH)}")

if os.path.exists(DB_PATH):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        print(f"\nTables in database:")
        for table in tables:
            print(f"  - {table[0]}")

            cursor.execute(f"PRAGMA table_info({table[0]})")
            columns = cursor.fetchall()
            for col in columns:
                print(f"    - {col[1]} ({col[2]})")

        conn.close()
        print("\nDatabase check completed!")

    except Exception as e:
        print(f"Error: {e}")
else:
    print("Database file not found!")
