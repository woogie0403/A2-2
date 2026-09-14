import argparse
import sys
import os

# Windows 콘솔 한글/이모지 UnicodeEncodeError 방지
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 상위 경로 모듈 인식
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json

from utils.logger import setup_logger
from storage.db import init_db, insert_raw_news, fetch_clean_news, count_clean_news
from collectors.collector import collect_from_rss, collect_by_crawling
from processors.cleaner import clean_news_pipeline
from analyzers.summarizer import run_summarize
from analyzers.insights_analyzer import analyze_insights, print_insights
from analyzers.visualizer import generate_charts
from analyzers.reporter import generate_report
from processors.exporter import export_news

logger = setup_logger()

def load_policy_dedup() -> str:
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("policy", {}).get("deduplication", "skip")
    except Exception:
        return "skip"

def main():
    parser = argparse.ArgumentParser(
        description="🚀 AI 뉴스 트렌드 수집 및 종합 분석 파이프라인 CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 명령어 목록")

    # 1. fetch (수집)
    parser_fetch = subparsers.add_parser("fetch", help="외부 뉴스(RSS/크롤링)를 수집하여 Raw 저장소에 저장")
    parser_fetch.add_argument("--source", choices=["all", "rss", "crawl"], default="all", help="수집 소스 선택 (기본: all)")
    parser_fetch.add_argument("--limit", type=int, default=5, help="소스별 수집 기사 수 (기본: 5)")
    parser_fetch.add_argument("--query", type=str, default="AI 인공지능", help="RSS 검색 키워드")

    # 2. clean (정제)
    parser_clean = subparsers.add_parser("clean", help="Raw 뉴스를 정제하여 Clean 저장소에 분리 저장")
    parser_clean.add_argument("--limit", type=int, default=None, help="정제할 최대 기사 수")

    # 3. summarize (AI 요약)
    parser_sum = subparsers.add_parser("summarize", help="AI를 활용하여 뉴스 본문 요약")
    parser_sum.add_argument("--all", action="store_true", help="모든 기사 요약")
    parser_sum.add_argument("--unsummarized", action="store_true", default=False, help="미요약 기사만 요약")
    parser_sum.add_argument("--id", type=int, help="특정 ID 기사만 단건 요약")
    parser_sum.add_argument("--limit", type=int, default=10, help="최대 요약 건수")

    # 4. analyze (인사이트 분석)
    parser_ana = subparsers.add_parser("analyze", help="기간 및 카테고리별 AI 종합 트렌드/인사이트 분석")
    parser_ana.add_argument("--category", type=str, help="분석 대상 카테고리 (예: AI, IT)")
    parser_ana.add_argument("--date-from", type=str, help="시작 일자 (YYYY-MM-DD)")
    parser_ana.add_argument("--date-to", type=str, help="종료 일자 (YYYY-MM-DD)")

    # 5. report (시각화 및 리포트 생성)
    subparsers.add_parser("report", help="차트 2종 생성 및 종합 마크다운 분석 리포트 발행")

    # 6. export (내보내기)
    parser_exp = subparsers.add_parser("export", help="정제 및 요약 데이터를 파일로 내보내기")
    parser_exp.add_argument("--format", choices=["all", "csv", "excel", "jsonl"], default="all", help="파일 포맷")
    parser_exp.add_argument("--status", choices=["cleaned", "summarized"], default="summarized", help="기사 상태 필터")

    # [올인원 원클릭 자동화] pipeline (run-all)
    parser_pipe = subparsers.add_parser("pipeline", aliases=["run-all"], help="수집→정제→요약→분석→리포트→내보내기 전 과정 원클릭 일괄 실행")
    parser_pipe.add_argument("--limit", type=int, default=10, help="수집 및 요약 대상 수 (기본: 10)")
    parser_pipe.add_argument("--category", type=str, default="AI", help="인사이트 분석 카테고리 (기본: AI)")
    parser_pipe.add_argument("--query", type=str, default="AI 인공지능", help="RSS 검색 키워드")

    # [보너스 과제 1] list & show (데이터 조회 및 조건 필터링 / 페이지네이션)
    parser_list = subparsers.add_parser("list", help="저장된 뉴스 목록 조건별 조회 및 페이지네이션")
    parser_list.add_argument("--category", type=str, help="카테고리 필터 (예: AI, IT)")
    parser_list.add_argument("--date", type=str, help="발행 일자 필터 (YYYY-MM-DD)")
    parser_list.add_argument("--keyword", type=str, help="제목 및 본문 검색 키워드")
    parser_list.add_argument("--page", type=int, default=1, help="페이지 번호 (기본: 1)")
    parser_list.add_argument("--limit", type=int, default=10, help="페이지당 기사 수 (기본: 10)")

    parser_show = subparsers.add_parser("show", help="특정 ID 기사의 상세 정보 및 요약문 조회")
    parser_show.add_argument("--id", type=int, required=True, help="조회할 기사 ID")

    args = parser.parse_args()

    # 인자 없이 실행 시 도움말 출력
    if not args.command:
        parser.print_help()
        return

    # DB 초기화 보장
    init_db()

    # 서브커맨드 분기 처리
    dedup_policy = load_policy_dedup()

    if args.command == "fetch":
        logger.info(f"뉴스 수집 시작: source={args.source}, limit={args.limit} (중복 정책: {dedup_policy})")
        total_collected = 0
        
        if args.source in ["rss", "all"]:
            rss_items = collect_from_rss(query=args.query, limit=args.limit)
            total_collected += insert_raw_news(rss_items, deduplication=dedup_policy)
            
        if args.source in ["crawl", "all"]:
            crawl_items = collect_by_crawling(limit=args.limit)
            total_collected += insert_raw_news(crawl_items, deduplication=dedup_policy)
            
        logger.info(f"수집 완료: {total_collected}건 신규 raw 저장소에 저장 완료")

    elif args.command == "clean":
        clean_news_pipeline(limit=args.limit)

    elif args.command == "summarize":
        target = "all" if args.all else "unsummarized"
        run_summarize(target=target, target_id=args.id, limit=args.limit)

    elif args.command == "analyze":
        result = analyze_insights(category=args.category, date_from=args.date_from, date_to=args.date_to)
        print_insights(result)

    elif args.command == "report":
        logger.info("시각화 차트 생성 중...")
        generate_charts()
        logger.info("종합 리포트 생성 중...")
        generate_report()

    elif args.command == "export":
        export_news(file_format=args.format, status=args.status)

    elif args.command == "list":
        page = max(1, args.page)
        limit = max(1, args.limit)
        offset = (page - 1) * limit
        total_count = count_clean_news(target="all", category=args.category, date=args.date, keyword=args.keyword)
        total_pages = max(1, (total_count + limit - 1) // limit) if total_count > 0 else 1
        items = fetch_clean_news(target="all", category=args.category, date=args.date, keyword=args.keyword, limit=limit, offset=offset)

        filter_desc = []
        if args.category:
            filter_desc.append(f"카테고리='{args.category}'")
        if args.date:
            filter_desc.append(f"일자='{args.date}'")
        if args.keyword:
            filter_desc.append(f"키워드='{args.keyword}'")
        filter_str = f" [필터: {', '.join(filter_desc)}]" if filter_desc else ""

        print(f"\n📑 [뉴스 목록 조회]{filter_str} | 총 {total_count}건 (페이지 {page}/{total_pages})")
        print(f"{'ID':<5} | {'카테고리':<6} | {'발행일자':<10} | {'상태':<10} | {'기사 제목'}")
        print("-" * 75)
        if not items:
            print("  조건에 일치하는 기사가 없습니다.")
        else:
            for it in items:
                title_short = it['title'][:40] + ("..." if len(it['title']) > 40 else "")
                print(f"{it['id']:<5} | {it['category']:<6} | {it['published_at']:<10} | {it['status']:<10} | {title_short}")
        if page < total_pages:
            print(f"\n💡 다음 페이지: python main.py list --page {page + 1} (페이지당 {limit}건)")
        print()

    elif args.command == "show":
        items = fetch_clean_news(target_id=args.id)
        if not items:
            print(f"ID={args.id}에 해당하는 기사를 찾을 수 없습니다.")
            return
        item = items[0]
        print("\n" + "=" * 60)
        print(f"📌 [기사 상세 조회] ID: {item['id']}")
        print(f"제목: {item['title']}")
        print(f"카테고리: {item['category']} | 발행일자: {item['published_at']} | 상태: {item['status']}")
        print(f"링크: {item['url']}")
        print("-" * 60)
        print(f"🤖 [AI 요약문]:\n{item.get('summary', '(요약 없음)')}")
        print("=" * 60 + "\n")

if __name__ == "__main__":
    main()