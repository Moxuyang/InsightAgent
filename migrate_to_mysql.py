"""
SQLite → MySQL 数据迁移脚本
=============================
用法:
  1. 确保 pymysql 已安装:  pip install pymysql
  2. 确保 MySQL 中已创建目标数据库（默认: insight_agent）
  3. 修改下方 MYSQL_CONFIG 中的连接参数
  4. 运行:  python migrate_to_mysql.py

功能:
  - 读取 SQLite (database/app.db) 中的所有表结构
  - 在 MySQL 中创建对应的表（自动翻译 SQLite 语法）
  - 将 SQLite 数据逐表导入 MySQL
  - 导入完成后重置自增序号
"""
import os
import sys
import sqlite3
import re

# ===== MySQL 连接配置（请按实际情况修改）=====
MYSQL_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': '',          # 填写你的 MySQL 密码
    'database': 'insight_agent',
    'charset': 'utf8mb4',
}

# ===== 路径配置 =====
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB = os.path.join(PROJECT_ROOT, 'database', 'app.db')


def translate_sql(sql: str) -> str:
    """将 SQLite CREATE TABLE 语句转换为 MySQL 语法"""
    s = sql
    # AUTOINCREMENT -> AUTO_INCREMENT
    s = re.sub(r'\bAUTOINCREMENT\b', 'AUTO_INCREMENT', s, flags=re.IGNORECASE)
    # datetime('now') -> CURRENT_TIMESTAMP
    s = re.sub(r"datetime\('now'\)", 'CURRENT_TIMESTAMP', s, flags=re.IGNORECASE)
    # TEXT NOT NULL UNIQUE -> VARCHAR(255) NOT NULL UNIQUE
    s = re.sub(r'(\w+)\s+TEXT\s+NOT\s+NULL\s+UNIQUE', r'\1 VARCHAR(255) NOT NULL UNIQUE', s, flags=re.IGNORECASE)
    # TEXT -> LONGTEXT for TEXT columns that are not VARCHAR
    # (MySQL handles TEXT fine, keep TEXT for long content)
    return s


def migrate():
    # 检查 SQLite 文件
    if not os.path.exists(SQLITE_DB):
        print(f"[错误] SQLite 数据库文件不存在: {SQLITE_DB}")
        sys.exit(1)

    # 检查 pymysql
    try:
        import pymysql
    except ImportError:
        print("[错误] pymysql 未安装，请执行: pip install pymysql")
        sys.exit(1)

    # ===== 步骤 1: 连接 SQLite，获取所有表名 =====
    print("=" * 60)
    print("  InsightAgent - SQLite → MySQL 数据迁移")
    print("=" * 60)

    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row

    tables = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    table_names = [t['name'] for t in tables]

    print(f"\n[SQLite] 数据库: {SQLITE_DB}")
    print(f"[SQLite] 发现 {len(table_names)} 张表: {', '.join(table_names)}")

    # ===== 步骤 2: 连接 MySQL =====
    print(f"\n[MySQL] 连接中... {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")
    try:
        mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        mysql_cur = mysql_conn.cursor()
    except pymysql.err.OperationalError as e:
        code = e.args[0] if e.args else 0
        if code == 1049:
            print(f"[错误] 数据库 '{MYSQL_CONFIG['database']}' 不存在")
            print(f"  请先在 MySQL 中执行: CREATE DATABASE {MYSQL_CONFIG['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        elif code == 1045:
            print("[错误] MySQL 用户名或密码错误，请检查 MYSQL_CONFIG")
        elif code == 2003:
            print("[错误] 无法连接 MySQL 服务器，请确认 MySQL 已启动且主机/端口正确")
        else:
            print(f"[错误] MySQL 连接失败: {e}")
        sqlite_conn.close()
        sys.exit(1)

    print("[MySQL] 连接成功")

    # ===== 步骤 3: 获取每张表的建表 SQL =====
    print("\n" + "=" * 60)
    print("  步骤 1/3: 创建 MySQL 表结构")
    print("=" * 60)

    for table_name in table_names:
        # 获取 SQLite 建表语句
        create_sql_row = sqlite_conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        ).fetchone()

        if not create_sql_row or not create_sql_row['sql']:
            print(f"  [跳过] {table_name}: 无法获取建表语句")
            continue

        create_sql = create_sql_row['sql']
        mysql_create = translate_sql(create_sql)

        # DROP + CREATE (幂等)
        mysql_cur.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        try:
            mysql_cur.execute(mysql_create)
            print(f"  [OK] {table_name}")
        except pymysql.err.OperationalError as e:
            print(f"  [失败] {table_name}: {e}")
            print(f"         SQL: {mysql_create[:120]}...")
            # 询问是否继续
            choice = input("  是否继续迁移其他表？(y/n): ").strip().lower()
            if choice != 'y':
                mysql_conn.close()
                sqlite_conn.close()
                sys.exit(1)

    mysql_conn.commit()

    # ===== 步骤 4: 迁移数据 =====
    print("\n" + "=" * 60)
    print("  步骤 2/3: 迁移数据")
    print("=" * 60)

    # 外键约束的表需要按依赖顺序导入
    # 无外键依赖的表先导入
    priority_order = [
        'users', 'roles', 'menus', 'ai_models', 'spy_sources',
        'api_configs', 'system_configs', 'skills', 'digital_employees',
        'collab_groups', 'chat_sessions', 'deep_collects',
        'business_data',
    ]
    # 然后是有外键/关联的表
    remaining = [t for t in table_names if t not in priority_order]
    ordered_tables = priority_order + remaining

    total_rows = 0
    failed_tables = []

    for table_name in ordered_tables:
        if table_name not in table_names:
            continue

        # 获取列名
        cols_info = sqlite_conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        col_names = [c['name'] for c in cols_info]

        # 读取所有数据
        rows = sqlite_conn.execute(f"SELECT * FROM `{table_name}`").fetchall()
        row_count = len(rows)

        if row_count == 0:
            print(f"  [空] {table_name} (0 行)")
            continue

        # 构建 INSERT 语句
        placeholders = ', '.join(['%s'] * len(col_names))
        col_list = ', '.join([f'`{c}`' for c in col_names])
        insert_sql = f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders})"

        try:
            # 转为 tuple list
            data_tuples = [tuple(r[c] for c in col_names) for r in rows]

            # 批量插入（每批 500 条）
            batch_size = 500
            for i in range(0, len(data_tuples), batch_size):
                batch = data_tuples[i:i + batch_size]
                mysql_cur.executemany(insert_sql, batch)
                mysql_conn.commit()

            total_rows += row_count
            print(f"  [OK] {table_name}: {row_count} 行")
        except pymysql.err.IntegrityError as e:
            print(f"  [部分] {table_name}: 主键/唯一键冲突，尝试逐行插入...")
            # 逐行插入，忽略冲突
            success = 0
            for row_data in data_tuples:
                try:
                    mysql_cur.execute(insert_sql, row_data)
                    success += 1
                except:
                    pass
            mysql_conn.commit()
            total_rows += success
            print(f"  [OK] {table_name}: {success}/{row_count} 行")
        except Exception as e:
            print(f"  [失败] {table_name}: {e}")
            failed_tables.append(table_name)

    # ===== 步骤 5: 重置自增序号 =====
    print("\n" + "=" * 60)
    print("  步骤 3/3: 重置 MySQL 自增序号")
    print("=" * 60)

    for table_name in table_names:
        try:
            mysql_cur.execute(f"SELECT MAX(id) as m FROM `{table_name}`")
            result = mysql_cur.fetchone()
            if result and result[0] is not None:
                next_id = result[0] + 1
                mysql_cur.execute(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = {next_id}")
                print(f"  [OK] {table_name}: AUTO_INCREMENT = {next_id}")
            else:
                mysql_cur.execute(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = 1")
                print(f"  [OK] {table_name}: 空表，AUTO_INCREMENT = 1")
        except Exception as e:
            # 表可能没有 id 列
            pass

    mysql_conn.commit()

    # ===== 清理 =====
    mysql_cur.close()
    mysql_conn.close()
    sqlite_conn.close()

    # ===== 结果 =====
    print("\n" + "=" * 60)
    print("  迁移完成")
    print("=" * 60)
    print(f"  总导入行数: {total_rows}")
    print(f"  成功表数:   {len(table_names) - len(failed_tables)}")
    if failed_tables:
        print(f"  失败表:     {', '.join(failed_tables)}")

    print(f"\n下一步:")
    print(f"  1. 在系统设置中将 db_type 改为 'mysql'")
    print(f"  2. 配置 MySQL 连接参数")
    print(f"  3. 重启服务即可使用 MySQL")
    print(f"\n  MySQL 配置界面: 系统设置 → 数据库配置")


if __name__ == '__main__':
    migrate()
