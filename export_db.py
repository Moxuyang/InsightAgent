"""数据库导出工具 - 导出 SQLite 中所有表到 CSV"""
import sqlite3, os, csv

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "database", "app.db")
OUT_DIR = os.path.join(BASE, "exports")
os.makedirs(OUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 列出所有表及行数
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print(f"数据库: {DB_PATH}")
print(f"大小: {os.path.getsize(DB_PATH)} bytes")
print(f"\n{'表名':<35} {'行数':>6}")
print("-" * 43)

for t in tables:
    name = t["name"]
    count = conn.execute(f"SELECT count(1) AS n FROM [{name}]").fetchone()["n"]
    print(f"{name:<35} {count:>6}")

# 导出所有表到 CSV
print(f"\n导出 CSV 到: {OUT_DIR}")
for t in tables:
    name = t["name"]
    rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()
    if not rows:
        continue
    csv_path = os.path.join(OUT_DIR, f"{name}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(rows[0].keys())  # header
        for r in rows:
            writer.writerow(list(r))
    print(f"  -> {name}.csv ({len(rows)} rows)")

conn.close()
print("\n导出完成! 文件在 exports/ 目录下")
