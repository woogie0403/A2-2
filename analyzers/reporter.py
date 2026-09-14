import os
import sys
from datetime import datetime
import pandas as pd

# 상위 폴더 모듈 참조
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger
from storage.db import fetch_raw_news, fetch_clean_news, fetch_latest_insight

logger = setup_logger()

def generate_report(output_dir: str = "output") -> str:
    """PDF 요구사항에 맞춘 품질 지표, TOP N 집계, AI 인사이트가 포함된 종합 리포트 생성"""
    os.makedirs(output_dir, exist_ok=True)
    
    raw_news = fetch_raw_news()
    clean_news = fetch_clean_news(target="all")
    insight = fetch_latest_insight()
    
    raw_count = len(raw_news)
    clean_count = len(clean_news)
    summarized_count = sum(1 for item in clean_news if item.get("status") == "summarized")
    
    # 1. 품질 지표 계산 (2개 이상)
    clean_rate = (clean_count / raw_count * 100) if raw_count > 0 else 0.0
    summary_rate = (summarized_count / clean_count * 100) if clean_count > 0 else 0.0
    missing_content_count = sum(1 for item in clean_news if not item.get("content"))
    
    # 2. TOP N 집계 (카테고리별, 수집 소스별)
    df = pd.DataFrame(clean_news) if clean_news else pd.DataFrame()
    cat_summary = df["category"].value_counts().to_dict() if not df.empty else {}
    
    df_raw = pd.DataFrame(raw_news) if raw_news else pd.DataFrame()
    source_summary = df_raw["source"].value_counts().to_dict() if not df_raw.empty else {}
    
    # 3. 리포트 본문 작성 (마크다운)
    report_content = f"""# 📊 AI 뉴스 트렌드 및 종합 분석 최종 리포트

* **보고서 생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
* **대상 도메인**: IT / 인공지능(AI) 트렌드 뉴스

---

## 1. 📈 데이터 파이프라인 품질 지표 (Quality Metrics)
* **총 수집된 원본(Raw) 기사**: {raw_count}건
* **정제 완료(Clean) 기사**: {clean_count}건 (**정제 성공률: {clean_rate:.1f}%**)
* **AI 요약 완료 기사**: {summarized_count}건 (**요약 완료율: {summary_rate:.1f}%**)
* **결측치(내용 누락) 건수**: {missing_content_count}건 (0%)

---

## 2. 🏆 데이터 TOP N 집계 현황
### [카테고리별 기사 분포]
"""
    for cat, count in cat_summary.items():
        report_content += f"- **{cat}**: {count}건 ({count/clean_count*100:.1f}%)\n"

    report_content += "\n### [수집 출처(Source)별 기사 분포]\n"
    for src, count in source_summary.items():
        report_content += f"- **{src}**: {count}건\n"

    report_content += """
---

## 3. 🤖 AI 인사이트 종합 분석 결과
"""
    if insight:
        report_content += f"""### [주요 트렌드]
{insight.get('trends', '-')}

### [핵심 키워드 TOP 5]
`{insight.get('keywords', '-')}`

### [시사점 및 향후 전망]
{insight.get('implications', '-')}
"""
    else:
        report_content += "*(인사이트 분석 결과가 아직 생성되지 않았습니다.)*\n"

    report_content += """
---

## 4. 🖼️ 시각화 산출물 안내
* 카테고리별 뉴스 수 차트: `output/category_distribution.png`
* 일자별 뉴스 수집 추이 차트: `output/daily_trend.png`

---
*본 보고서는 자동화된 CLI 기반 AI 뉴스 수집·정제·분석 파이프라인에 의해 생성되었습니다.*
"""

    # 파일 저장 (MD & TXT)
    md_path = os.path.join(output_dir, "report.md")
    txt_path = os.path.join(output_dir, "report.txt")
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    logger.info(f"종합 리포트 파일 저장 완료: {md_path}")

    # 콘솔(터미널)에도 출력
    print("\n" + "="*50)
    print(report_content)
    print("="*50 + "\n")

    return md_path

if __name__ == "__main__":
    generate_report()