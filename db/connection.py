"""MySQL 连接管理。"""

from __future__ import annotations

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from config import (
    MYSQL_CHARSET,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)


def _connect(host: str, database: str | None) -> Connection:
    return pymysql.connect(
        host=host,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=database,
        charset=MYSQL_CHARSET,
        cursorclass=DictCursor,
        autocommit=False,
    )


def ensure_database() -> None:
    """确保 meddesk 库存在（utf8mb4）。"""
    conn = _connect(MYSQL_HOST, None)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def get_connection() -> Connection:
    """获取业务库连接。首次调用会确保库存在。"""
    ensure_database()
    return _connect(MYSQL_HOST, MYSQL_DATABASE)
