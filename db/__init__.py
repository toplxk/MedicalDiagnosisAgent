"""MySQL 数据访问层。"""

from db.connection import get_connection, ensure_database
from db.schema import init_schema, seed_if_empty

__all__ = ["get_connection", "ensure_database", "init_schema", "seed_if_empty"]
