import json
import os
import sys
import re
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger
from storage.db import fetch_clean_news, update_news_summary

logger = setup_logger()
CACHED_MODEL = None

def load_api_key() -> str:
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("api_key", {}).get("gemini", "").strip()
        except Exception:
            pass
    return os.environ.get("GEMINI_API_KEY", "").strip()

def limit_summary_300(text: str) -> str:
    """대괄호 제거 및 최대 300자 이내 마침표 완결 요약문 생성"""
    if not text:
        return ""
    # 대괄호 및 리스트 잔여물 제거
    text = re.sub(r"\[\s*['\"]", "", text)
    text = re.sub(r"['\"]\s*,\s*['\"]", " ", text)
    text = re.sub(r"['\"]\s*\]", "", text)
    text = text.replace("[", "").replace("]", "").strip()
    text = re.sub(r"\s+", " ", text).strip()
    
    # 300자 제한 및 마지막 마침표(.)에서 완결
    if len(text) > 300:
        sliced = text[:300]
        last_dot = max(sliced.rfind("."), sliced.rfind("!"), sliced.rfind("?"))
        if last_dot > 50:
            return sliced[:last_dot + 1].strip()
        return sliced.strip() + "."
    if not text.endswith((".", "!", "?")):
        text += "."
    return text

def summarize_with_ai(title: str, content: str, api_key: str = "") -> str:
    global CACHED_MODEL
    clean_title = re.sub(r"\[.*?\]", "", title).strip()

    prompt = f"""당신은 IT 전문 뉴스 에디터입니다. 아래 제공된 기사 본문을 읽고 핵심 내용을 최대 300자 이내의 완성된 한국어로 요약하세요.
규칙:
1. 대괄호([])나 리스트 기호 없이 오직 줄글 형태의 완성된 문장만 출력하세요.
2. 문장 끝은 반드시 온전한 마침표(.)로 맺으세요.

제목: {clean_title}
본문: {content}"""

    if api_key:
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 450}
        }
        models_to_try = [CACHED_MODEL] if CACHED_MODEL else ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        for model_name in models_to_try:
            if not model_name:
                continue
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=20)
                if res.status_code == 200:
                    CACHED_MODEL = model_name
                    result_json = res.json()
                    summary_text = result_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    summary_text = re.sub(r"\(?Draft\s*\d*\)?[:*]*", "", summary_text).strip()
                    summary_text = summary_text.replace("Draft Summaries (Iterative Process):**", "").strip()
                    cleaned = limit_summary_300(summary_text)
                    if len(cleaned) >= 20:
                        return cleaned
            except Exception:
                continue

    # Fallback 로직 (대괄호 완전 차단 + 앞 2문장 완결 추출)
    raw_sentences = [s.strip() for s in content.split(".") if len(s.strip()) >= 15]
    valid_sentences = []
    for s in raw_sentences:
        clean_s = re.sub(r"[\[\]'\"`]", "", s).strip()
        if len(clean_s) >= 15:
            valid_sentences.append(clean_s)
        if len(valid_sentences) == 2:
            break
            
    if len(valid_sentences) >= 2:
        return limit_summary_300(f"{valid_sentences[0]}. {valid_sentences[1]}.")
    elif len(valid_sentences) == 1:
        return limit_summary_300(f"{valid_sentences[0]}.")
    return limit_summary_300(f"{clean_title} 관련 최신 IT 및 인공지능 산업 동향 소식입니다.")

def run_summarize(target: str = "unsummarized", target_id: int = None, limit: int = 10) -> int:
    api_key = load_api_key()
    news_list = fetch_clean_news(target=target, target_id=target_id, limit=limit)
    total_count = len(news_list)
    logger.info(f"요약 대상: {total_count}건")

    if total_count == 0:
        logger.info("요약할 대상 뉴스가 없습니다.")
        return 0

    success_count = 0
    fail_count = 0

    for idx, item in enumerate(news_list, 1):
        try:
            news_id = item["id"]
            title = item["title"]
            content = item["content"]

            summary = summarize_with_ai(title, content, api_key)
            update_news_summary(news_id, summary)
            success_count += 1
            
            logger.info(f"[{idx}/{total_count}] ID={news_id} 요약 완료 (본문 {len(content)}자 → 요약 {len(summary)}자)")
        except Exception as e:
            fail_count += 1
            logger.error(f"[{idx}/{total_count}] ID={item.get('id')} 요약 실패: {e}")

    logger.info(f"요약 완료: {success_count}건 성공, {fail_count}건 실패")
    return success_count

if __name__ == "__main__":
    run_summarize(target="all", limit=10)