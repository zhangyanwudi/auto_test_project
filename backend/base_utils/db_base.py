"""
数据库操作基础工具模块。

提供 Database（单库连接）和 DButils（多库管理）两个类，
支持 MySQL、PostgreSQL、Trino（Metabase）三种数据库类型。
"""
from typing import Any, Optional

from base_utils.config_base import get_config


class Database:
    """数据库连接与操作封装，支持 MySQL / PostgreSQL / Trino。"""

    # 支持的数据库类型及其连接方法映射
    _DB_TYPE_MAP: dict[str, str] = {
        "mysql": "_open_mysql",
        "postgre": "_open_postgre",
        "metabase": "_open_metabase",
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        username: str = "root",
        port: int = 3306,
        password: str = "123456",
        database: str = "080-test",
        db_type: str = "mysql",
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.db_type = db_type
        self.db: Any = None
        self.conn: Any = None
        self._connected = False

        self._connect()

    def _connect(self) -> None:
        """根据 db_type 选择对应的连接方法。"""
        method_name = self._DB_TYPE_MAP.get(self.db_type.lower())
        if method_name is None:
            raise ValueError(f"不支持的数据库类型: 【{self.db_type}】")
        try:
            getattr(self, method_name)()
            self._connected = True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"数据库连接失败: {e}") from e

    @property
    def connected(self) -> bool:
        """返回数据库是否连接成功。"""
        return self._connected

    # ------------------------------------------------------------------
    # 各数据库连接实现
    # ------------------------------------------------------------------

    def _open_mysql(self) -> None:
        import pymysql
        self.db = pymysql.connect(
            host=self.host,
            user=self.username,
            port=self.port,
            password=self.password,
            database=self.database,
            charset="utf8",
        )
        self.conn = self.db.cursor()

    def _open_postgre(self) -> None:
        import psycopg2
        self.db = psycopg2.connect(
            host=self.host,
            user=self.username,
            port=self.port,
            password=self.password,
            database=self.database,
        )
        self.conn = self.db.cursor()

    def _open_metabase(self) -> None:
        from trino.dbapi import connect
        from trino.auth import BasicAuthentication
        self.db = connect(
            host=self.host,
            port=self.port,
            http_scheme="https",
            catalog="iceberg",
            schema=self.database,
            auth=BasicAuthentication(self.username, self.password),
        )
        self.conn = self.db.cursor()

    # ------------------------------------------------------------------
    # 查询方法
    # ------------------------------------------------------------------

    def fetch_all(self, sql: str, params: Optional[tuple] = None, map_result: bool = False) -> Any:
        """执行查询，返回全部结果。

        Args:
            sql: SQL 语句。
            params: 查询参数。
            map_result: 为 True 时返回 {列名: [值列表]} 格式的字典。
        """
        self.conn.execute(sql, params or ())
        ret = self.conn.fetchall()
        if map_result:
            return self._format_map(ret)
        return ret

    def fetch_one(self, sql: str, params: Optional[tuple] = None, map_result: bool = False) -> Any:
        """执行查询，返回第一条结果。

        Args:
            sql: SQL 语句。
            params: 查询参数。
            map_result: 为 True 时返回 {列名: 值} 格式的字典。
        """
        self.conn.execute(sql, params or ())
        ret = self.conn.fetchone()
        if map_result:
            return self._format_map([ret]) if ret else {}
        return ret

    def execute(self, sql: str, params: Optional[tuple] = None, get_lastrowid: bool = False) -> Any:
        """执行写操作（INSERT / UPDATE / DELETE），自动提交。

        Args:
            sql: SQL 语句。
            params: 执行参数。
            get_lastrowid: 是否返回最后插入的行 ID（仅 MySQL / PostgreSQL 有效）。
        """
        self.conn.execute(sql, params or ())
        self.commit()
        if get_lastrowid:
            return self.conn.lastrowid
        return None

    # 保留旧方法名作为别名，确保向后兼容
    def Runchall(self, sql, params=None, title=None, filename=None, map=False):  # noqa: N802
        return self.fetch_all(sql, params, map)

    def Runchone(self, sql, params=None, title=None, filename=None, map=False):  # noqa: N802
        return self.fetch_one(sql, params, map)

    def Runsql(self, sql, params=None, title=None, filename=None, get_id=False):  # noqa: N802
        return self.execute(sql, params, get_id)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def commit(self) -> None:
        """提交事务。"""
        self.db.commit()

    def close(self) -> None:
        """关闭数据库连接（游标 → 连接）。"""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self.db is not None:
            self.db.close()
            self.db = None
        self._connected = False

    def _format_map(self, ret: list) -> dict:
        """将查询结果转为 {列名: [值列表]} 的列式字典。"""
        if not ret or self.conn.description is None:
            return {}
        columns = [col[0] for col in self.conn.description]
        return {col: [row[i] for row in ret] for i, col in enumerate(columns)}

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
        return False

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        state = "connected" if self._connected else "disconnected"
        return f"<Database {self.db_type}://{self.host}:{self.port}/{self.database} ({state})>"


class DButils:
    """多数据库连接管理器。

    用法::

        config = {
            "mysql_db": {"db_type": "mysql", "host": "...", "port": 3306, ...},
            "pg_db":    {"db_type": "postgre", "host": "...", "port": 5432, ...},
        }
        dbs = DButils(config)
        dbs.mysql_db.fetch_all("SELECT 1")
    """

    def __init__(self, db_config: dict):
        self._db_map: dict[str, Database] = {}
        for db_key, cfg in db_config.items():
            self._db_map[db_key] = Database(**cfg)

    def __getattr__(self, name: str) -> Database:
        """支持通过属性名直接获取数据库实例。"""
        if name.startswith("_"):
            raise AttributeError(name)
        db = self._db_map.get(name)
        if db is None:
            raise AttributeError(f"未找到数据库配置: {name}")
        return db

    def get(self, name: str) -> Optional[Database]:
        """根据名称获取数据库实例，不存在时返回 None。"""
        return self._db_map.get(name)

    def close_all(self) -> None:
        """关闭所有数据库连接。"""
        for db in self._db_map.values():
            db.close()

    def __repr__(self) -> str:
        names = ", ".join(self._db_map.keys())
        return f"<DButils ({len(self._db_map)} dbs: {names})>"


if __name__ == "__main__":
    _pg = get_config('database', 'postgres') or {}
    db_client = Database(
        host=_pg.get('host', ''),
        username=_pg.get('username', ''),
        password=_pg.get('password', ''),
        port=_pg.get('port', 5432),
        database=_pg.get('database', 'postgres'),
        db_type="postgre",
    )
    try:
        sql = "SELECT * FROM withdraw_record"
        print(db_client.fetch_all(sql))
    finally:
        db_client.close()
