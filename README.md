# 기업마당 → Notion 지원사업 공고 자동 수집기

bizinfo.go.kr(기업마당)에서 당일 등록된 서울·경기 지역 지원사업 공고를 Notion 데이터베이스에 자동으로 저장합니다.

---

## 준비물

- Python 3.8 이상
- bizinfo.go.kr API 키
- Notion Integration Token
- Notion 데이터베이스

---

## 1단계: bizinfo API 키 발급

1. [bizinfo.go.kr](https://www.bizinfo.go.kr) 접속 후 회원가입 및 로그인
2. 상단 메뉴 **활용정보 → 정책정보 개방** 클릭
3. **지원사업정보 API** 의 사용신청 버튼 클릭
4. 양식 작성 후 제출 (승인까지 소요시간 있을 수 있음)
5. 승인 완료 후 마이페이지에서 **API 키** 복사

---

## 2단계: Notion Integration 생성

1. [notion.so/my-integrations](https://www.notion.so/my-integrations) 접속
2. **New integration** 클릭
3. 이름 입력 후 저장
4. **Internal Integration Token** 복사 (`secret_xxx...` 형태 or `ntn_xxx...`)

---

## 3단계: Notion 데이터베이스 준비

### 3-1. 데이터베이스 속성 추가

Notion에서 사용할 데이터베이스에 아래 속성을 추가합니다.

| 속성명 | 타입 |
|---|---|
| 제목 | 제목 (기본값) |
| 지역 | 선택 |
| 공고기관 | 텍스트 |
| 공고ID | 텍스트 |
| 등록일 | 날짜 |
| 접수마감일 | 텍스트 (날짜·문자 혼합: "2026-03-19", "예산 소진시까지", "상시 접수" 등) |
| 공고URL | URL |
| 지원분야 | 다중 선택 |

### 3-2. Integration 연결

1. Notion 데이터베이스 페이지 우측 상단 **`···`** 클릭
2. **연결(Connections)** → 2단계에서 만든 Integration 검색 후 연결

### 3-3. 데이터베이스 ID 확인

데이터베이스 URL에서 ID를 복사합니다.

```
https://www.notion.so/3148d1f64171805f85b1da16d13bafcc?v=xxx
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                       이 부분이 DB ID
```

---

## 4단계: 프로젝트 설정

### 4-1. 가상환경 생성 및 활성화

```bash
# 프로젝트 폴더로 이동
cd 프로젝트_폴더_경로

# 가상환경 생성
python -m venv venv

# 가상환경 활성화
# Mac / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

활성화되면 터미널 앞에 `(venv)` 가 붙습니다.

### 4-2. 라이브러리 설치

```bash
pip install -r requirements.txt
```

### 4-3. .env 파일 작성

`.env` 파일을 열고 아래 세 가지 값을 채웁니다.

```
BIZINFO_API_KEY=발급받은_API_키
NOTION_TOKEN=secret_xxx...
NOTION_DB_ID=3148d1f64171805f85b1da16d13bafcc
```

---

## 5단계: API 응답 필드 확인 (최초 1회)

`main.py` 안의 아래 주석을 **일시적으로 해제**하고 실행합니다.

```python
# import json; print(json.dumps(data, ensure_ascii=False, indent=2))
```

출력된 JSON을 보고 실제 필드명(`title`, `pblancNm` 등)을 확인한 뒤,
`main.py`의 필드명 매핑 부분을 실제 응답에 맞게 수정합니다.

확인이 끝나면 다시 주석 처리합니다.

---

## 6단계: 실행

```bash
python main.py
```

정상 실행 시 아래와 같이 출력됩니다.

```
[2026-02-27] 지원사업 공고 수집 시작
당일 공고 총 12건 발견
  [OK] 20260227_서울 청년창업 지원사업
  [OK] 20260227_경기 소상공인 특별지원
  [SKIP] 중복: 이미 등록된 공고
  ...
완료 — 생성: 11건 / 중복 건너뜀: 1건
```

---

## 7단계: 자동화 (매일 자동 실행)

### 방법 A: 로컬 cron (Mac/Linux)

```bash
crontab -e
```

아래 내용 추가 (매일 오전 9시 실행):

```
0 9 * * * /프로젝트경로/venv/bin/python /프로젝트경로/main.py >> /프로젝트경로/run.log 2>&1
```

### 방법 B: GitHub Actions (무료, 서버 불필요 — 추천)

1. GitHub에 이 프로젝트를 private 레포지토리로 업로드
2. 레포 **Settings → Secrets and variables → Actions → Repository secrets → New repository secret ** 에서 아래 3개 등록

| Secret 이름 | 값 |
|---|---|
| `BIZINFO_API_KEY` | API 키 |
| `NOTION_TOKEN` | Integration Token |
| `NOTION_DB_ID` | 데이터베이스 ID |

3. `.github/workflows/daily.yml` 파일 생성

```yaml
name: 매일 공고 수집

on:
  schedule:
    - cron: '0 0 * * *'  # UTC 00:00 = KST 09:00
  workflow_dispatch:       # 수동 실행 버튼도 활성화

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          BIZINFO_API_KEY: ${{ secrets.BIZINFO_API_KEY }}
          NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
          NOTION_DB_ID: ${{ secrets.NOTION_DB_ID }}
```

---

## 파일 구성

```
project/
├── main.py       # 전체 실행 코드
├── .env          # API 키 (절대 GitHub에 올리지 말 것)
├── .gitignore    # .env 제외 설정
└── README.md     # 이 파일
```

> ⚠️ `.env` 파일은 반드시 `.gitignore`에 추가해서 GitHub에 올라가지 않도록 주의하세요.
> ```
> # .gitignore
> .env
> ```
