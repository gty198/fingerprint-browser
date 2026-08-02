"""Profile 数据模型 + SQLite 存储。

设计要点:指纹必须稳定 —— 每个 profile 的指纹参数生成一次后持久化,
每次启动复用同一套参数(同一身份每次启动指纹变了反而会被识别)。
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent.parent / "profiles" / "profiles.sqlite3"


@dataclass
class Profile:
    """一份浏览器 profile。None 字段表示「尚未生成,启动前由 fingerprinter 补齐」。"""

    id: str
    name: str
    user_data_dir: str  # 相对 profiles/ 的目录名
    user_agent: str | None = None
    platform: str | None = None
    timezone: str | None = None
    locale: str | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    color_scheme: str | None = None
    hardware_concurrency: int | None = None
    humanize: bool = False
    proxy_server: str | None = None
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_fingerprint_ready(self) -> bool:
        return all(
            x is not None
            for x in (self.user_agent, self.platform, self.timezone, self.locale,
                      self.viewport_width, self.viewport_height, self.hardware_concurrency)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "user_data_dir": self.user_data_dir,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "timezone": self.timezone,
            "locale": self.locale,
            "viewport_width": self.viewport_width,
            "viewport_height": self.viewport_height,
            "color_scheme": self.color_scheme,
            "hardware_concurrency": self.hardware_concurrency,
            "humanize": self.humanize,
            "proxy_server": self.proxy_server,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "fingerprint_ready": self.is_fingerprint_ready,
        }

    @staticmethod
    def from_row(row: sqlite3.Row) -> "Profile":
        return Profile(
            id=row["id"],
            name=row["name"],
            user_data_dir=row["user_data_dir"],
            user_agent=row["user_agent"],
            platform=row["platform"],
            timezone=row["timezone"],
            locale=row["locale"],
            viewport_width=row["viewport_width"],
            viewport_height=row["viewport_height"],
            color_scheme=row["color_scheme"],
            hardware_concurrency=row["hardware_concurrency"],
            humanize=bool(row["humanize"]),
            proxy_server=row["proxy_server"],
            notes=row["notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ProfileStore:
    def __init__(self, db_path: Path = DEFAULT_DB, profiles_root: Path | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_root = Path(profiles_root) if profiles_root else self.db_path.parent
        # FastAPI 同步端点在线程池执行,跨线程访问需要 check_same_thread=False + 锁
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                user_data_dir TEXT NOT NULL,
                user_agent TEXT,
                platform TEXT,
                timezone TEXT,
                locale TEXT,
                viewport_width INTEGER,
                viewport_height INTEGER,
                color_scheme TEXT,
                hardware_concurrency INTEGER,
                humanize INTEGER DEFAULT 0,
                proxy_server TEXT,
                notes TEXT DEFAULT '',
                created_at REAL,
                updated_at REAL
            )
            """
        )
        self._conn.commit()

    # ---- CRUD ----

    def create(self, name: str, **fields: Any) -> Profile:
        pid = uuid.uuid4().hex[:12]
        user_data_dir = f"profile-{pid}"
        p = Profile(
            id=pid,
            name=name,
            user_data_dir=user_data_dir,
            created_at=time.time(),
            updated_at=time.time(),
        )
        for k, v in fields.items():
            if v is not None and hasattr(p, k):
                setattr(p, k, v)
        self._upsert(p)
        return p

    def get(self, pid: str) -> Profile | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM profiles WHERE id = ?", (pid,)).fetchone()
            return Profile.from_row(row) if row else None

    def list(self) -> list[Profile]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
            return [Profile.from_row(r) for r in rows]

    def update(self, pid: str, **fields: Any) -> Profile | None:
        p = self.get(pid)
        if p is None:
            return None
        for k, v in fields.items():
            if hasattr(p, k) and k not in ("id", "created_at"):
                setattr(p, k, v)
        p.updated_at = time.time()
        self._upsert(p)
        return p

    def delete(self, pid: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM profiles WHERE id = ?", (pid,))
            self._conn.commit()
            return cur.rowcount > 0

    def data_dir(self, p: Profile) -> Path:
        """该 profile 的浏览器 user-data-dir(独立隔离目录)。"""
        return self.profiles_root / p.user_data_dir

    def _upsert(self, p: Profile) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO profiles (
                    id, name, user_data_dir, user_agent, platform, timezone, locale,
                    viewport_width, viewport_height, color_scheme, hardware_concurrency,
                    humanize, proxy_server, notes, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, user_data_dir=excluded.user_data_dir,
                    user_agent=excluded.user_agent, platform=excluded.platform,
                    timezone=excluded.timezone, locale=excluded.locale,
                    viewport_width=excluded.viewport_width, viewport_height=excluded.viewport_height,
                    color_scheme=excluded.color_scheme, hardware_concurrency=excluded.hardware_concurrency,
                    humanize=excluded.humanize, proxy_server=excluded.proxy_server,
                    notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (
                    p.id, p.name, p.user_data_dir, p.user_agent, p.platform, p.timezone,
                    p.locale, p.viewport_width, p.viewport_height, p.color_scheme,
                    p.hardware_concurrency, int(p.humanize), p.proxy_server, p.notes,
                    p.created_at, p.updated_at,
                ),
            )
            self._conn.commit()
