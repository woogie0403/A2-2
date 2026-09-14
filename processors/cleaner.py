import re
from datetime import datetime
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger
from storage.db import fetch_raw_news, insert_clean_news

logger = setup_logger()
AI_KEYWORDS = ["ai", "인공지능", "생성형", "llm", "챗봇", "gpt", "반도체", "딥러닝", "클라우드", "엔비디아", "오픈ai", "머신러닝"]

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def limit_content_800(text: str) -> str:
    """
    본문을 최대 800자로 제한하되, 
    중간에 단어가 뚝 끊기지 않도록 800자 이내의 마지막 마침표(.)에서 완결합니다.
    """
    if not text:
        return ""
    text = clean_text(text)
    
    if len(text) > 800:
        sliced = text[:800]
        last_dot = max(sliced.rfind("."), sliced.rfind("!"), sliced.rfind("?"))
        if last_dot > 100:
            return sliced[:last_dot + 1].strip()
        return sliced.strip() + "."
        
    # 800자 이하인 경우에도 맨 끝 미완성 단어 찌꺼기 제거
    last_dot = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    if last_dot != -1 and last_dot > 40:
        return text[:last_dot + 1].strip()
    return text

def normalize_date(date_str: str) -> str:
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    if "T" in date_str:
        return date_str.split("T")[0]
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", date_str)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return datetime.now().strftime("%Y-%m-%d")

def classify_category(title: str, content: str) -> str:
    combined = f"{title} {content}".lower()
    for kw in AI_KEYWORDS:
        if kw in combined:
            return "AI"
    return "IT"

def clean_news_pipeline(limit: int = None) -> int:
    logger.info("=== [데이터 정제 파이프라인 시작] ===")
    raw_items = fetch_raw_news()
    if limit is not None and limit > 0:
        raw_items = raw_items[:limit]
        logger.info(f"Raw 저장소 조회: 총 {len(raw_items)}건으로 제한 정제 진행")
    else:
        logger.info(f"Raw 저장소 조회: 총 {len(raw_items)}건 발견")
    
    cleaned_items = []
    for item in raw_items:
        title = clean_text(item.get("title", ""))
        url = item.get("url", "").strip()
        
        if not title or not url or len(title) < 5:
            continue
            
        raw_content = item.get("content", "")
        # 본문 800자 이내 마침표 완결 정제 적용! (최소 150자 이상인 알찬 본문만 승인)
        content = limit_content_800(raw_content)
        if not content or len(content) < 150:
            continue
            
        published_at = normalize_date(item.get("collected_at", ""))
        category = classify_category(title, content)
        
        cleaned_items.append({
            "raw_id": item["id"],
            "title": title,
            "content": content,
            "url": url,
            "published_at": published_at,
            "category": category,
            "status": "cleaned",
            "created_at": datetime.now().isoformat()
        })
        
    saved_count = insert_clean_news(cleaned_items)
    logger.info(f"-> 정제 대상 {len(cleaned_items)}건 중 {saved_count}건 Clean 저장소에 신규 저장 완료")
    logger.info("=== [데이터 정제 파이프라인 완료] ===")
    return saved_count

if __name__ == "__main__":
    clean_news_pipeline()