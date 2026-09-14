import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger
from storage.db import insert_raw_news, init_db, get_existing_urls

logger = setup_logger()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
}

KEYWORDS_SUBSTRING = [
    "인공지능", "머신러닝", "딥러닝", "생성형", "챗봇", "반도체", "클라우드",
    "알고리즘", "자율주행", "소프트웨어", "오픈소스", "스타트업", "파이썬",
    "오픈ai", "openai", "엔비디아", "nvidia", "구글", "google"
]
KEYWORDS_REGEX = re.compile(r"\b(ai|llm|gpt|gpu|api)\b", re.IGNORECASE)

# 순수 게임 및 무관 분야 제외 키워드 (블랙리스트)
EXCLUDE_KEYWORDS = [
    "mmorpg", "신작 게임", "인게임", "과금", "퀘스트", "게임동아",
    "게임탐구", "플레이 후기", "모바일 게임", "콘솔 게임", "사전예약",
    "아이템", "던전", "길드", "레이드", "게임성", "신작 rpg"
]

# 본문 영역 후보 셀렉터 (위→아래 순서로 탐색)
ARTICLE_BODY_SELECTORS = [
    "#article-view-content-div",   # AI타임스 본문 영역
    ".article_view",               # 다음 뉴스 본문 영역
    "section[dmcf-sid]",
    "article",
    ".article-body",
    ".news-content",
    "#content",
]

# 제목 영역 후보 셀렉터
ARTICLE_TITLE_SELECTORS = [
    "h3.tit_view",                 # 다음 뉴스 공식 제목
    ".tit_view",
    "h3.heading",
    "#article-view-header h3",     # AI타임스 제목
    ".article-head-title",
    "h3",
    "h2"
]


def is_relevant(title: str, content: str, query: str = None) -> bool:
    """
    제목/본문이 진짜 AI·IT 분야인지 엄격하게 판별:
    1) 게임 전용 키워드(MMORPG, 과금, 퀘스트 등) 포함 시 즉시 제외
    2) 제목에 핵심 키워드가 있거나, 본문에 핵심 키워드가 최소 2회 이상 출현해야 통과
    """
    target_text = f"{title} {content}".lower()

    # 1. 게임/무관 제외 키워드 필터링
    if any(ex in target_text for ex in EXCLUDE_KEYWORDS):
        return False

    # 사용자 지정 query 우선 검사
    if query and query.strip():
        q = query.strip().lower()
        if q not in ["ai", "all", "it"] and q in target_text:
            return True

    # 2. 제목에 AI/IT 전문 키워드가 포함되어 있는지 검사
    title_lower = title.lower()
    if KEYWORDS_REGEX.search(title_lower) or any(kw in title_lower for kw in KEYWORDS_SUBSTRING):
        return True
    if re.search(r"\bIT\b", title):
        return True

    # 3. 본문 내 키워드 출현 빈도 검사 (우연히 1번 스친 경우 배제, 최소 2회 이상)
    kw_hits = len(KEYWORDS_REGEX.findall(target_text))
    for kw in KEYWORDS_SUBSTRING:
        kw_hits += target_text.count(kw)

    return kw_hits >= 2


def is_korean_enough(text: str, min_ratio: float = 0.3) -> bool:
    """
    한글 비율이 min_ratio 이상인지 확인.
    긱뉴스 등에서 영문 원문이 통째로 들어오는 것을 방지.
    """
    if not text:
        return False
    korean_chars = len(re.findall(r"[가-힣]", text))
    return (korean_chars / len(text)) >= min_ratio


def clean_body_text(text: str, max_len: int = 800) -> str:
    """본문 공백 정제 및 최대 길이 초과 시 문장 단위로 절삭"""
    if not text:
        return ""

    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= max_len:
        return cleaned

    sliced = cleaned[:max_len]
    last_punct = max(sliced.rfind("."), sliced.rfind("!"), sliced.rfind("?"))
    if last_punct > (max_len * 0.5):
        return sliced[:last_punct + 1].strip()
    return sliced.strip() + "..."


def fetch_article_detail(url: str) -> tuple:
    """
    [기사 상세 크롤링] 원문 URL에 접속해 진짜 기사 제목과 본문을 분리 추출.
    반환값: (clean_title, clean_body)
    """
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        res.encoding = res.apparent_encoding  # 인코딩 자동 감지 (한글 깨짐 방지)
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. 정식 기사 제목 추출
        real_title = ""
        for t_sel in ARTICLE_TITLE_SELECTORS:
            t_node = soup.select_one(t_sel)
            if t_node and len(t_node.get_text().strip()) >= 5:
                real_title = " ".join(t_node.get_text().split()).strip()
                break

        if not real_title and soup.title:
            raw_t = soup.title.get_text().strip()
            # "다음 뉴스", "AI타임스" 등 접미사 제거
            real_title = raw_t.split("|")[0].split("-")[0].strip()

        # 2. 기사 본문 추출
        body_node = None
        for sel in ARTICLE_BODY_SELECTORS:
            node = soup.select_one(sel)
            if node:
                body_node = node
                break

        target = body_node if body_node else soup
        paragraphs = [p.get_text().strip() for p in target.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p) > 10)  # 짧은 조각 제거
        return real_title, text.strip()
    except Exception as e:
        logger.warning(f"기사 상세 추출 실패 ({url}): {e}")
        return "", ""


def fetch_article_body(url: str) -> str:
    """기존 호환성을 위한 본문 추출 래퍼"""
    _, body = fetch_article_detail(url)
    return body


def collect_from_rss(query: str = "AI", limit: int = 10) -> list:
    """[방법 1] AI타임스 RSS 수집 + 원문 재접속으로 본문 확보"""
    feed_url = "https://www.aitimes.com/rss/allArticle.xml"
    logger.info(f"[RSS 수집 시작] AI타임스 (목표: 최대 {limit}건, 쿼리: '{query}')")
    collected = []

    try:
        existing_urls = get_existing_urls()
        res = requests.get(feed_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        res.encoding = "utf-8"

        root = ET.fromstring(res.content)
        items = root.findall(".//item")
        skipped_dup = skipped_irrel = 0

        for item in items:
            if len(collected) >= limit:
                break

            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")

            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
            url = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

            if not url or len(title) < 5:
                continue

            # 중복 검사 (원문 접속 전에 먼저 걸러 불필요한 요청 방지)
            if url in existing_urls:
                skipped_dup += 1
                continue

            # 본문 확보: ① 원문 전체 추출 → ② 실패 시 RSS 요약
            full_body = fetch_article_body(url)
            if len(full_body) >= 100:
                content = clean_body_text(full_body, max_len=800)
            else:
                content = ""
                if desc_elem is not None and desc_elem.text:
                    desc_soup = BeautifulSoup(desc_elem.text, "html.parser")
                    content = clean_body_text(desc_soup.get_text().strip(), max_len=800)

            if len(content) < 20:
                continue

            if not is_relevant(title, content, query=query):
                skipped_irrel += 1
                continue

            collected.append({
                "title": title, "content": content, "url": url,
                "source": "AI타임스 (RSS)", "method": "rss",
                "collected_at": datetime.now().isoformat(),
            })
            time.sleep(0.5)  # 매너 크롤링

        logger.info(
            f"[RSS 수집 완료] 신규 {len(collected)}건 "
            f"(중복 {skipped_dup}건, 무관 {skipped_irrel}건)"
        )
    except Exception as e:
        logger.error(f"RSS 수집 오류: {e}")

    return collected


def collect_by_crawling(limit: int = 10) -> list:
    """[방법 2] 다음 IT 뉴스 크롤링 + 원문 기사 본문 심층 추출 (최소 150자 ~ 최대 800자)"""
    target_url = "https://news.daum.net/digital"
    logger.info(f"[크롤링 수집 시작] 다음 IT 뉴스 (목표: 최대 {limit}건)")
    collected = []

    try:
        existing_urls = get_existing_urls()
        res = requests.get(target_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        res.encoding = "utf-8"

        soup = BeautifulSoup(res.text, "html.parser")
        candidate_links = soup.find_all("a", href=True)
        visited_urls = set()
        skipped_dup = skipped_irrel = skipped_empty = 0

        for a_tag in candidate_links:
            if len(collected) >= limit:
                break

            href = a_tag["href"].strip()
            title = a_tag.get_text().strip()

            # 다음 뉴스 본문 기사 패턴 (/v/) 검증
            if "/v/" not in href or len(title) < 8 or href in visited_urls:
                continue
            visited_urls.add(href)

            url = href if href.startswith("http") else urljoin("https://news.daum.net/", href)

            if url in existing_urls:
                skipped_dup += 1
                continue

            # 원문 기사 접속 및 정식 제목 & 본문 추출 (최소 150자 이상 필수)
            detail_title, full_body = fetch_article_detail(url)
            if len(full_body) < 150 or not is_korean_enough(full_body):
                skipped_empty += 1
                continue

            # 상세 페이지의 공식 제목 우선 사용 (메인 카드의 긴 잡음 텍스트 원천 차단)
            final_title = detail_title if detail_title and len(detail_title) >= 5 else title
            final_title = " ".join(final_title.split()).strip()

            content = clean_body_text(full_body, max_len=800)

            if not is_relevant(final_title, content):
                skipped_irrel += 1
                continue

            collected.append({
                "title": final_title,
                "content": content,
                "url": url,
                "source": "다음 IT 뉴스 (Daum)",
                "method": "crawl",
                "collected_at": datetime.now().isoformat(),
            })
            time.sleep(0.5)  # 매너 크롤링

        logger.info(
            f"[크롤링 수집 완료] 신규 {len(collected)}건 "
            f"(중복 {skipped_dup}건, 무관 {skipped_irrel}건, 150자 미만 제외 {skipped_empty}건)"
        )
    except Exception as e:
        logger.error(f"크롤링 수집 오류: {e}")

    return collected


if __name__ == "__main__":
    init_db()
    rss = collect_from_rss(limit=3)
    crawl = collect_by_crawling(limit=3)

    # 본문 길이 확인용 (검증 후 삭제 가능)
    for item in rss + crawl:
        print(f"[{len(item['content'])}자] {item['title'][:35]}")

    insert_raw_news(rss + crawl)