import sqlite3
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger

logger = setup_logger()


def get_connection(db_path: str = "data/news_database.db") -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = "data/news_database.db"):
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT,
        url TEXT UNIQUE NOT NULL,
        source TEXT NOT NULL,
        method TEXT NOT NULL,
        collected_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clean_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_id INTEGER,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        published_at TEXT,
        category TEXT DEFAULT 'IT',
        summary TEXT,
        status TEXT DEFAULT 'cleaned',
        created_at TEXT NOT NULL,
        FOREIGN KEY (raw_id) REFERENCES raw_news (id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        date_from TEXT,
        date_to TEXT,
        trends TEXT,
        keywords TEXT,
        implications TEXT,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()


def insert_raw_news(news_list: list, db_path: str = "data/news_database.db", deduplication: str = "skip") -> int:
    if not news_list:
        return 0
    conn = get_connection(db_path)
    cursor = conn.cursor()
    saved_count = 0

    for item in news_list:
        try:
            if deduplication == "upsert":
                cursor.execute("""
                INSERT INTO raw_news (title, content, url, source, method, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    collected_at=excluded.collected_at
                """, (item["title"], item.get("content", ""), item["url"], item["source"], item["method"], item["collected_at"]))
                saved_count += 1
            else:
                cursor.execute("""
                INSERT OR IGNORE INTO raw_news (title, content, url, source, method, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (item["title"], item.get("content", ""), item["url"], item["source"], item["method"], item["collected_at"]))
                if cursor.rowcount > 0:
                    saved_count += 1
        except Exception as e:
            logger.warning(f"기사 저장 중 오류: {e}")

    conn.commit()
    conn.close()
    return saved_count


def fetch_raw_news(db_path: str = "data/news_database.db") -> list:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM raw_news ORDER BY id ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# ── [신규 추가] 중복 수집 방지용 URL 조회 함수 ──────────────────────────
def get_existing_urls(db_path: str = "data/news_database.db") -> set:
    """raw_news 테이블에 이미 저장된 URL 집합을 반환합니다 (중복 수집 스킵용)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url FROM raw_news")
        return {row["url"] for row in cursor.fetchall()}
    except Exception as e:
        logger.warning(f"기존 URL 목록 조회 중 오류: {e}")
        return set()
    finally:
        conn.close()


def insert_clean_news(clean_list: list, db_path: str = "data/news_database.db", deduplication: str = "skip") -> int:
    if not clean_list:
        return 0
    conn = get_connection(db_path)
    cursor = conn.cursor()
    saved_count = 0

    for item in clean_list:
        try:
            if deduplication == "upsert":
                cursor.execute("""
                INSERT INTO clean_news (raw_id, title, content, url, published_at, category, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    published_at=excluded.published_at,
                    category=excluded.category
                """, (item["raw_id"], item["title"], item["content"], item["url"], item["published_at"], item["category"], item["status"], item["created_at"]))
                saved_count += 1
            else:
                cursor.execute("""
                INSERT OR IGNORE INTO clean_news (raw_id, title, content, url, published_at, category, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (item["raw_id"], item["title"], item["content"], item["url"], item["published_at"], item["category"], item["status"], item["created_at"]))
                if cursor.rowcount > 0:
                    saved_count += 1
        except Exception as e:
            logger.warning(f"Clean 기사 저장 중 오류: {e}")

    conn.commit()
    conn.close()
    return saved_count


def count_clean_news(target: str = "all", category: str = None, date: str = None, keyword: str = None, date_from: str = None, date_to: str = None, db_path: str = "data/news_database.db") -> int:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    conditions = []
    params = []

    if target == "unsummarized":
        conditions.append("(summary IS NULL OR summary = '')")
    if category:
        conditions.append("category = ?")
        params.append(category)
    if date:
        conditions.append("published_at = ?")
        params.append(date)
    if date_from:
        conditions.append("published_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("published_at <= ?")
        params.append(date_to)
    if keyword:
        conditions.append("(title LIKE ? OR content LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    query = "SELECT COUNT(*) FROM clean_news"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    cursor.execute(query, params)
    total = cursor.fetchone()[0]
    conn.close()
    return total


def fetch_clean_news(target: str = "unsummarized", target_id: int = None, limit: int = None, offset: int = None, category: str = None, date: str = None, keyword: str = None, date_from: str = None, date_to: str = None, db_path: str = "data/news_database.db") -> list:
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    conditions = []
    params = []

    if target_id is not None:
        conditions.append("id = ?")
        params.append(target_id)
    elif target == "unsummarized":
        conditions.append("(summary IS NULL OR summary = '')")
    
    if category:
        conditions.append("category = ?")
        params.append(category)
    if date:
        conditions.append("published_at = ?")
        params.append(date)
    if date_from:
        conditions.append("published_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("published_at <= ?")
        params.append(date_to)
    if keyword:
        conditions.append("(title LIKE ? OR content LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])

    query = "SELECT * FROM clean_news"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id ASC"
    if limit is not None:
        query += f" LIMIT {limit}"
    if offset is not None:
        query += f" OFFSET {offset}"

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def update_news_summary(news_id: int, summary_text: str, db_path: str = "data/news_database.db"):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE clean_news SET summary = ?, status = 'summarized' WHERE id = ?", (summary_text, news_id))
    conn.commit()
    conn.close()


def insert_insight(category: str, date_from: str, date_to: str, trends: str, keywords: str, implications: str, db_path: str = "data/news_database.db"):
    """인사이트 분석 결과를 DB에 저장합니다."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO insights (category, date_from, date_to, trends, keywords, implications, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (category, date_from, date_to, trends, keywords, implications, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def fetch_latest_insight(db_path: str = "data/news_database.db") -> dict:
    """가장 최근에 생성된 인사이트 분석 결과를 가져옵니다."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM insights ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None