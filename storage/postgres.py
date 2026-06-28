from typing import List, Dict, Any, Optional, Sequence

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from .base import DatabaseConnector
from .config import PostgreConfig


class PostgreSQLConnector(DatabaseConnector):
    def __init__(self, config: PostgreConfig):
        super().__init__(config)
        self._pool = None
        self._conninfo = (
            f"host={config.host} port={config.port} "
            f"user={config.user} password={config.password} "
            f"dbname={config.database}"
        )

    def connect(self):
        """initialize connection pool"""
        if self._pool is None:
            try:
                self._pool = ConnectionPool(
                    conninfo=self._conninfo,
                    min_size=self.config.min_size,
                    max_size=self.config.max_size,
                    timeout=self.config.timeout,
                    max_idle=self.config.max_idle,
                    open=True,
                )
            except Exception as e:
                print(f"[Postgres Error] fail to create connection pool: {e}")
                raise

    def execute(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        if self._pool is None:
            self.connect()

        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, params)

                    if cur.description:
                        return cur.fetchall()

                    return []

        except Exception as e:
            print(f"[Postgres Error] fail to execute SQL : {query} | error: {e}")
            raise

    def executemany(self, query: str, params_seq: Sequence[tuple]) -> int:
        """
        批次執行同一個 SQL。

        這會讓 pipeline 不再逐筆呼叫 execute()，
        而是同一批資料共用同一個 connection / cursor。
        """
        if self._pool is None:
            self.connect()

        if not params_seq:
            return 0

        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, params_seq)
                    return cur.rowcount

        except Exception as e:
            print(f"[Postgres Error] fail to executemany SQL : {query} | error: {e}")
            raise

    def close(self):
        if self._pool:
            self._pool.close()
            self._pool = None

    def is_healthy(self) -> bool:
        """check if database alive"""
        if self._pool is None:
            return False

        try:
            self.execute("SELECT 1")
            return True
        except Exception:
            return False