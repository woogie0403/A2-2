import os
import sys
import platform
import matplotlib.pyplot as plt
import pandas as pd

# 상위 폴더 모듈 참조
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import setup_logger
from storage.db import fetch_clean_news

logger = setup_logger()

def set_korean_font():
    """OS에 맞게 한글 폰트 및 마이너스 부호 깨짐을 방지합니다."""
    system_name = platform.system()
    if system_name == "Windows":
        plt.rc("font", family="Malgun Gothic")
    elif system_name == "Darwin":  # Mac
        plt.rc("font", family="AppleGothic")
    else:  # Linux
        plt.rc("font", family="NanumGothic")
    plt.rcParams["axes.unicode_minus"] = False

def generate_charts(output_dir: str = "output") -> list:
    """PDF 요구사항에 맞춘 최소 2종 차트 생성 파이프라인"""
    os.makedirs(output_dir, exist_ok=True)
    set_korean_font()

    # DB에서 정제된 뉴스 전체 데이터 조회
    news_list = fetch_clean_news(target="all")
    if not news_list:
        logger.warning("차트를 그릴 뉴스 데이터가 DB에 없습니다.")
        return []

    # Pandas 데이터프레임으로 변환
    df = pd.DataFrame(news_list)
    logger.info(f"시각화 데이터 로드 완료: 총 {len(df)}건")

    saved_files = []

    # ----------------------------------------------------
    # [차트 1] 카테고리별 뉴스 수 (막대 그래프)
    # ----------------------------------------------------
    cat_counts = df["category"].value_counts()
    plt.figure(figsize=(7, 5))
    bars = plt.bar(cat_counts.index, cat_counts.values, color=["#4A90E2", "#50E3C2", "#F5A623"])
    plt.title("IT/AI 뉴스 카테고리별 분포", fontsize=14, fontweight="bold", pad=15)
    plt.xlabel("카테고리", fontsize=11)
    plt.ylabel("기사 수 (건)", fontsize=11)
    plt.grid(axis="y", linestyle="--", alpha=0.5)

    # 막대 위에 숫자 표시
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2., height, f"{int(height)}건", ha="center", va="bottom", fontsize=10)

    plt.tight_layout()
    chart1_path = os.path.join(output_dir, "category_distribution.png")
    plt.savefig(chart1_path, dpi=300)
    plt.close()
    logger.info(f"차트 1 생성 완료: {chart1_path}")
    saved_files.append(chart1_path)

    # ----------------------------------------------------
    # [차트 2] 일자별 수집 추이 (꺾은선 그래프)
    # ----------------------------------------------------
    daily_counts = df["published_at"].value_counts().sort_index()
    plt.figure(figsize=(8, 5))
    plt.plot(daily_counts.index, daily_counts.values, marker="o", color="#E94E77", linewidth=2, markersize=8)
    plt.title("일자별 뉴스 수집 추이", fontsize=14, fontweight="bold", pad=15)
    plt.xlabel("발행 일자", fontsize=11)
    plt.ylabel("기사 수 (건)", fontsize=11)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.xticks(rotation=15)

    # 데이터 포인트 위에 숫자 표시
    for x, y in zip(daily_counts.index, daily_counts.values):
        plt.text(x, y + 0.1, f"{y}건", ha="center", va="bottom", fontsize=10)

    plt.tight_layout()
    chart2_path = os.path.join(output_dir, "daily_trend.png")
    plt.savefig(chart2_path, dpi=300)
    plt.close()
    logger.info(f"차트 2 생성 완료: {chart2_path}")
    saved_files.append(chart2_path)

    return saved_files

if __name__ == "__main__":
    generate_charts()