import os
import re
import requests
from datetime import date, timedelta
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

BIZINFO_API_KEY = os.getenv("BIZINFO_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

BASE_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

notion = Client(auth=NOTION_TOKEN)


def fetch_today_announcements(collect_days=2):
    """서울·경기 지역의 최근 N일 등록 공고 수집
    - collect_days=1: 어제·오늘 (2일치, 기본값)
    - collect_days=2: 그저께·어제·오늘 (3일치), 6은 일주일치 데이터 수집
    - API는 areaCd와 무관하게 전국 데이터 반환 → jrsdInsttNm으로 서울/경기만 필터
    """
    valid_dates = tuple(
        (date.today() - timedelta(days=i)).strftime("%Y%m%d")
        for i in range(collect_days + 1)
    )
    seen_ids = set()
    results = []

    for area_cd, _ in [("11", "서울"), ("41", "경기")]:
        params = {
            "crtfcKey": BIZINFO_API_KEY,
            "dataType": "json",
            "areaCd": area_cd,
            "pageIndex": 1,
            "pageUnit": 100,
        }
        try:
            res = requests.get(BASE_URL, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            # 응답 구조 확인용 (처음 실행 시 주석 해제해서 확인)
            # import json; print(json.dumps(data, ensure_ascii=False, indent=2))

            items = data.get("jsonArray", data.get("items", []))
            if isinstance(items, dict):
                items = [items]

            for item in items:
                # creatPnttm(등록일) 기준: valid_dates 범위 내만
                reg_date = item.get("creatPnttm", "").replace("-", "").replace(" ", "")[:8]
                if reg_date not in valid_dates:
                    continue

                # 서울·경기만: jrsdInsttNm(공고기관)으로 지역 판별 (경상남도 등 제외)
                agency = item.get("jrsdInsttNm") or ""
                if "서울" in agency:
                    area_name = "서울"
                elif "경기도" in agency:
                    area_name = "경기"
                else:
                    continue

                pblanc_id = item.get("pblancId") or ""
                if pblanc_id and pblanc_id in seen_ids:
                    continue
                seen_ids.add(pblanc_id)
                item["area_name"] = area_name
                results.append(item)

        except Exception as e:
            print(f"[ERROR] API 호출 실패: {e}")

    return results


def is_duplicate(pblanc_id):
    """이미 Notion에 등록된 공고인지 확인"""
    try:
        res = notion.databases.query(
            database_id=NOTION_DB_ID,
            filter={
                "property": "공고ID",
                "rich_text": {"equals": pblanc_id}
            }
        )
        return len(res["results"]) > 0
    except Exception as e:
        print(f"[ERROR] 중복 확인 실패: {e}")
        return False


def create_notion_page(item):
    """Notion 데이터베이스에 공고 페이지 생성"""
    today = date.today().strftime("%Y%m%d")

    pblanc_id  = item.get("pblancId") or ""
    title_text = item.get("pblancNm") or "제목없음"
    agency     = item.get("jrsdInsttNm") or ""
    category   = item.get("pldirSportRealmLclasCodeNm") or ""

    # 등록일: creatPnttm "2026-02-26 15:21:29" → "2026-02-26"
    creat_pnttm = item.get("creatPnttm") or ""
    reg_date_iso = creat_pnttm[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", creat_pnttm) else ""

    # 접수마감: "2026-02-13 ~ 2026-03-19" → 종료일만, "예산 소진시까지"/"상시 접수"/"선착순 접수" 등 → 문자 그대로
    req_period = item.get("reqstBeginEndDe") or ""
    req_period = req_period.strip()
    if "~" in req_period:
        end_part = req_period.split("~")[-1].strip()
        # YYYY-MM-DD 형식이면 종료일만, 아니면 전체 문자열 사용
        deadline_value = end_part if re.match(r"^\d{4}-\d{2}-\d{2}$", end_part) else req_period
    else:
        deadline_value = req_period
    # 빈 문자열이면 저장하지 않음
    if not deadline_value:
        deadline_value = ""

    # 공고 URL: 상대경로에 도메인 붙이기
    pblanc_url = item.get("pblancUrl") or ""
    if pblanc_url.startswith("/"):
        pblanc_url = "https://www.bizinfo.go.kr" + pblanc_url

    page_title = f"{today}_{title_text}"

    properties = {
        "제목":    {"title": [{"text": {"content": page_title}}]},
        "지역":    {"select": {"name": item["area_name"]}},
        "공고기관": {"rich_text": [{"text": {"content": agency}}]},
        "공고ID":  {"rich_text": [{"text": {"content": pblanc_id}}]},
    }

    if reg_date_iso:
        properties["등록일"] = {"date": {"start": reg_date_iso}}

    # 접수마감: 날짜·문자 모두 저장 (Notion 속성은 텍스트로 설정)
    if deadline_value:
        properties["접수마감일"] = {"rich_text": [{"text": {"content": deadline_value}}]}

    if pblanc_url:
        properties["공고URL"] = {"url": pblanc_url}

    if category:
        # Notion DB에서 지원분야가 multi_select 타입인 경우
        properties["지원분야"] = {"multi_select": [{"name": category}]}

    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties=properties,
    )
    return page_title


def main():
    print(f"[{date.today()}] 지원사업 공고 수집 시작")

    announcements = fetch_today_announcements()
    print(f"당일 공고 총 {len(announcements)}건 발견")

    created, skipped = 0, 0
    for item in announcements:
        pblanc_id = item.get("pblancId") or ""

        if pblanc_id and is_duplicate(pblanc_id):
            print(f"  [SKIP] 중복: {item.get('pblancNm')}")
            skipped += 1
            continue

        try:
            page_title = create_notion_page(item)
            print(f"  [OK] {page_title}")
            created += 1
        except Exception as e:
            print(f"  [ERROR] Notion 페이지 생성 실패: {e}")

    print(f"\n완료 - 생성: {created}건 / 중복 건너뜀: {skipped}건")


if __name__ == "__main__":
    main()