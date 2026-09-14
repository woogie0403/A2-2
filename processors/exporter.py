import os
import sys
import pandas as pd

# 상위 폴더 모듈 참조
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger
from storage.db import fetch_clean_news

logger = setup_logger()

def export_news(output_dir: str = "output", file_format: str = "all", status: str = None, category: str = None) -> list:
    """
    clean_news 데이터를 CSV, Excel, JSONL 포맷으로 내보냅니다.
    - file_format: 'csv', 'excel', 'jsonl', 'all'
    - status: 'cleaned', 'summarized' 등 필터링
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # DB에서 데이터 조회
    items = fetch_clean_news(target="all", category=category)
    
    # 상태 필터링
    if status:
        items = [it for it in items if it.get("status") == status]
        
    if not items:
        logger.warning("내보낼 데이터가 없습니다.")
        return []

    df = pd.DataFrame(items)
    exported_files = []

    # 1. CSV 내보내기 (한글 깨짐 방지 utf-8-sig)
    if file_format in ["csv", "all"]:
        csv_path = os.path.join(output_dir, "news_export.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(f"CSV 내보내기 완료: {csv_path} ({len(df)}건)")
        exported_files.append(csv_path)

    # 2. Excel (.xlsx) 내보내기
    if file_format in ["excel", "xlsx", "all"]:
        excel_path = os.path.join(output_dir, "news_export.xlsx")
        df.to_excel(excel_path, index=False)
        logger.info(f"Excel 내보내기 완료: {excel_path} ({len(df)}건)")
        exported_files.append(excel_path)

    # 3. JSONL 내보내기
    if file_format in ["jsonl", "all"]:
        jsonl_path = os.path.join(output_dir, "news_export.jsonl")
        df.to_json(jsonl_path, orient="records", lines=True, force_ascii=False)
        logger.info(f"JSONL 내보내기 완료: {jsonl_path} ({len(df)}건)")
        exported_files.append(jsonl_path)

    return exported_files

if __name__ == "__main__":
    logger.info("=== [데이터 내보내기 테스트 시작] ===")
    export_news(file_format="all", status="summarized")
    logger.info("=== [데이터 내보내기 테스트 완료] ===")