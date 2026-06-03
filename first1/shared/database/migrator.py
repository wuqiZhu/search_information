# -*- coding: utf-8 -*-
"""
数据库迁移工具

支持 SQLite → PostgreSQL 数据迁移。

使用方式:
    from shared.database.migrator import DatabaseMigrator

    migrator = DatabaseMigrator(
        sqlite_path="/app/data/invest/fund_data.db",
        pg_url="postgresql://user:pass@localhost/invest"
    )
    migrator.migrate()
"""

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """数据库迁移器"""

    def __init__(
        self,
        sqlite_path: str,
        pg_url: str = None,
        batch_size: int = 1000,
    ):
        """
        初始化迁移器

        Args:
            sqlite_path: SQLite 数据库路径
            pg_url: PostgreSQL 连接 URL
            batch_size: 批量插入大小
        """
        self.sqlite_path = sqlite_path
        self.pg_url = pg_url or os.environ.get("DATABASE_URL", "")
        self.batch_size = batch_size
        self.pg_conn = None

    def connect_postgres(self):
        """连接 PostgreSQL"""
        if not self.pg_url:
            raise ValueError("PostgreSQL URL not configured")

        try:
            import psycopg2
            self.pg_conn = psycopg2.connect(self.pg_url)
            logger.info(f"Connected to PostgreSQL: {self.pg_url.split('@')[1] if '@' in self.pg_url else '...'}")
        except ImportError:
            logger.error("psycopg2 not installed: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def close(self):
        """关闭连接"""
        if self.pg_conn:
            self.pg_conn.close()

    def get_sqlite_tables(self) -> List[str]:
        """获取 SQLite 所有表"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    def get_table_schema(self, table: str) -> List[Tuple[str, str]]:
        """获取表结构"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        schema = [(row[1], row[2]) for row in cursor.fetchall()]
        conn.close()
        return schema

    def get_table_data(self, table: str, offset: int = 0, limit: int = None) -> List[Dict]:
        """获取表数据"""
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = f"SELECT * FROM {table}"
        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        cursor.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_table_count(self, table: str) -> int:
        """获取表记录数"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def create_postgres_table(self, table: str, schema: List[Tuple[str, str]]):
        """在 PostgreSQL 创建表"""
        # SQLite → PostgreSQL 类型映射
        type_mapping = {
            "INTEGER": "INTEGER",
            "REAL": "DOUBLE PRECISION",
            "TEXT": "TEXT",
            "BLOB": "BYTEA",
            "BOOLEAN": "BOOLEAN",
            "TIMESTAMP": "TIMESTAMP",
            "DATETIME": "TIMESTAMP",
            "DATE": "DATE",
            "JSON": "JSONB",
        }

        columns = []
        for col_name, col_type in schema:
            pg_type = type_mapping.get(col_type.upper(), "TEXT")
            columns.append(f'"{col_name}" {pg_type}')

        create_sql = f'''
            CREATE TABLE IF NOT EXISTS "{table}" (
                {", ".join(columns)}
            )
        '''

        cursor = self.pg_conn.cursor()
        cursor.execute(create_sql)
        self.pg_conn.commit()
        logger.info(f"Created table: {table}")

    def insert_batch(self, table: str, rows: List[Dict]):
        """批量插入数据"""
        if not rows:
            return

        cursor = self.pg_conn.cursor()

        # 构建 INSERT 语句
        columns = list(rows[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        col_names = ", ".join([f'"{c}"' for c in columns])

        insert_sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'

        # 批量插入
        values = [tuple(row.values()) for row in rows]
        cursor.executemany(insert_sql, values)
        self.pg_conn.commit()

    def migrate_table(self, table: str, dry_run: bool = False) -> Dict[str, Any]:
        """迁移单个表"""
        logger.info(f"Migrating table: {table}")

        # 获取表结构
        schema = self.get_table_schema(table)
        logger.info(f"  Schema: {len(schema)} columns")

        # 获取记录数
        total_count = self.get_table_count(table)
        logger.info(f"  Records: {total_count}")

        if dry_run:
            return {
                "table": table,
                "columns": len(schema),
                "records": total_count,
                "status": "dry_run",
            }

        # 创建 PostgreSQL 表
        self.create_postgres_table(table, schema)

        # 批量迁移数据
        migrated = 0
        offset = 0

        while offset < total_count:
            rows = self.get_table_data(table, offset, self.batch_size)
            if not rows:
                break

            self.insert_batch(table, rows)
            migrated += len(rows)
            offset += self.batch_size

            if migrated % 10000 == 0:
                logger.info(f"  Progress: {migrated}/{total_count}")

        logger.info(f"  Completed: {migrated} records migrated")

        return {
            "table": table,
            "columns": len(schema),
            "records": total_count,
            "migrated": migrated,
            "status": "completed",
        }

    def migrate(
        self,
        tables: List[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        迁移整个数据库

        Args:
            tables: 要迁移的表，None 表示所有表
            dry_run: 试运行，不实际迁移

        Returns:
            迁移结果
        """
        # 获取所有表
        all_tables = self.get_sqlite_tables()
        if tables:
            tables = [t for t in tables if t in all_tables]
        else:
            tables = all_tables

        logger.info(f"Tables to migrate: {tables}")

        # 连接 PostgreSQL
        if not dry_run:
            self.connect_postgres()

        results = []
        for table in tables:
            try:
                result = self.migrate_table(table, dry_run)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to migrate {table}: {e}")
                results.append({
                    "table": table,
                    "status": "failed",
                    "error": str(e),
                })

        # 关闭连接
        if not dry_run:
            self.close()

        return {
            "sqlite_path": self.sqlite_path,
            "tables": len(tables),
            "results": results,
        }


def migrate_sqlite_to_postgres(
    sqlite_path: str,
    pg_url: str = None,
    tables: List[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    便捷函数：SQLite → PostgreSQL 迁移

    Args:
        sqlite_path: SQLite 数据库路径
        pg_url: PostgreSQL 连接 URL
        tables: 要迁移的表
        dry_run: 试运行

    Returns:
        迁移结果
    """
    migrator = DatabaseMigrator(sqlite_path, pg_url)
    return migrator.migrate(tables, dry_run)


# CLI 入口
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="SQLite to PostgreSQL migrator")
    parser.add_argument("sqlite_path", help="SQLite database path")
    parser.add_argument("--pg-url", help="PostgreSQL URL", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--tables", nargs="+", help="Tables to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    migrator = DatabaseMigrator(
        sqlite_path=args.sqlite_path,
        pg_url=args.pg_url,
        batch_size=args.batch_size,
    )

    result = migrator.migrate(
        tables=args.tables,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
