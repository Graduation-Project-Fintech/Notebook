# 미국 핀튜버 신뢰도 분석 시스템

졸업프로젝트 — **영상/음성 데이터의 특징 추출을 통한 종목별 투자 신호 식별 및 분석 리포팅 시스템**

영어로 된 미국 주식 분석 유튜브 영상을 AI가 시청하고, 종목별 추천 액션(Buy/Hold/Sell)과 확신도를 추출한 뒤, 실제 주가 데이터로 사후 검증해 **유튜버별 신뢰도를 정량화**합니다.

---

## 시스템 구조

DB 없이 CLI 기반 파이썬 스크립트 + 파일시스템만으로 동작하는 경량 파이프라인.

```
[채널 ID 리스트]
      ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 01_collect/                                                          │
│   YouTube Data API → 영상 메타데이터 → 키워드 필터 → yt-dlp 다운로드  │
│   → data/videos/*.mp4, data/raw/video_metadata.csv                   │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 02_transcribe/                                                       │
│   Whisper → 자막 + 타임스탬프 → 추천 동사 키워드 매칭                  │
│   → data/transcripts/*.json (full transcript + 후보 segment 리스트)   │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 03_analyze/  ⭐ 프로젝트 핵심                                          │
│   Gemini API (멀티모달) ← 비디오 segment + 자막 segment 동시 입력       │
│   → JSON 라벨: {ticker, action, conviction_score, timestamp, ...}    │
│   → data/analysis/*.csv (영상별 종목 추천 + 확신도)                    │
│   분석 직후 mp4 즉시 삭제 (디스크 관리)                                  │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 04_backtest/                                                         │
│   yfinance → 각 추천의 추천일 기준 +1주 / +1개월 / +3개월 수익률 계산    │
│   → data/reports/credibility_by_channel.csv (유튜버별 신뢰도 지표)     │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
                       [신뢰도 리포트 + 시각화]
```

---

## 셋업

```bash
# 1. 환경 생성 (5분)
conda env create -f environment.yml
conda activate finfluencer-credibility

# 2. 환경변수 작성
cp .env
# .env 열어서 YOUTUBE_API_KEY, GOOGLE_API_KEY 작성

# 3. 채널 리스트 작성 (논의 사항 #1 참조)
nano 01_collect/channels.txt

# 4. 파이프라인 실행
python run_pipeline.py --stage all                # 전체 실행
# 또는 단계별:
python run_pipeline.py --stage collect
python run_pipeline.py --stage transcribe
python run_pipeline.py --stage analyze
python run_pipeline.py --stage backtest
```

---

## 디렉토리 구조

```
finfluencer-credibility/
├── environment.yml              # conda 환경
├── .env                         # API 키 템플릿
├── .gitignore
├── README.md                    # 이 파일
├── run_pipeline.py              # CLI 진입점 (Click 기반)
│
├── 01_collect/                 
│   ├── channels.txt             # 분석 대상 채널 ID (논의사항 #1)
│   ├── keywords.json            # 영상 제목 필터링 키워드
│   ├── fetch_channel_videos.py  # YouTube API로 채널 영상 메타 수집
│   ├── video_filter.py          # 추천 키워드 기반 영상 필터링
│   └── video_downloader.py      # yt-dlp + multiprocessing 병렬 다운로드
│
├── 02_transcribe/               
│   ├── transcribe.py            # Whisper 자막 생성 (large-v2)
│   ├── segment_finder.py        # 자막에서 추천 동사 매칭 → 후보 timestamp
│   └── recommendation_keywords.json  # "buy", "sell", "bullish", "I'm long" 등
│
├── 03_analyze/                  
│   ├── gemini_analyzer.py       # Gemini API 호출 + JSON 파싱
│   ├── cleanup.py               # 분석 후 mp4 즉시 삭제 (논의사항 #2)
│   ├── prompts/
│   │   ├── action_extraction.txt    # 종목/액션 추출 프롬프트
│   │   └── conviction_scoring.txt   # 확신도 1~3 평가 프롬프트
│   └── schemas/
│       └── recommendation.json      # Gemini JSON 응답 스키마 (Pydantic)
│
├── 04_backtest/                 
│   ├── price_fetcher.py         # yfinance로 과거 시세 수집 (캐싱)
│   ├── backtest_engine.py       # 추천일+N일 수익률 계산
│   ├── credibility_scorer.py    # 채널별 신뢰도 집계 (승률, 평균 수익률, 샤프지수)
│   └── windows.json             # 평가 윈도우 정의 (1주/1개월/3개월)
│
├── validation/                  # 졸프 평가용 — Gemini 라벨 정확도 검증
│   ├── manual_labels.csv        # 팀이 직접 라벨링한 ~30개 골드셋
│   ├── compare_with_gemini.ipynb # 사람 vs Gemini 비교
│   └── README.md                # "왜 검증이 필요한가" 설명
│
├── shared/                      # 모듈 간 공용 코드
│   ├── csv_schemas.py           # 파일시스템 의존성을 정의하는 단일 진실
│   ├── llm_clients.py           # Gemini/Whisper 클라이언트 래퍼
│   └── utils.py
│
└── data/                        # gitignored
    ├── videos/                  # mp4 (분석 후 삭제됨)
    ├── raw/
    │   ├── video_metadata.csv
    │   └── channel_metadata.csv
    ├── transcripts/             # *.json (Whisper 자막)
    ├── analysis/                # *.csv (Gemini 추출 결과 — 영원히 보관)
    └── reports/
        ├── credibility_by_channel.csv  # ⭐ 최종 산출물
        └── figures/
```

---

## 단계별 산출물 (파일시스템 = DB 역할)

DB 없이 운영되므로 각 단계의 입출력 파일이 모듈 간 인터페이스. `shared/csv_schemas.py`에 모든 스키마를 한 곳에서 정의.

| 단계 | 입력 | 출력 | 비고 |
|----|---|---|---|
| 01 | `channels.txt`, `keywords.json` | `data/raw/video_metadata.csv`, `data/videos/*.mp4` | mp4는 임시 |
| 02 | `data/videos/*.mp4` | `data/transcripts/{video_id}.json` | full transcript + 후보 segments |
| 03 | `data/transcripts/*.json` + `data/videos/*.mp4` | `data/analysis/{video_id}.csv` | mp4는 분석 후 삭제 |
| 04 | `data/analysis/*.csv` | `data/reports/credibility_by_channel.csv` | yfinance 시세는 캐싱 |

---

## 졸업 프로젝트 일정 매핑

### 졸프1 (5~6월) — 데이터 공급망 + AI 분석 엔진

| 시기 | 작업 | 디렉토리 |
|---|---|---|
| 5월 1주차 | 환경 셋업, 채널 리스트 확정 | `01_collect/channels.txt` |
| 5월 2~3주차 | 01_collect 구현, 50개 영상 다운로드 테스트 | `01_collect/` |
| 5월 4주차 | 02_transcribe 구현, Whisper 자막 추출 검증 | `02_transcribe/` |
| 6월 1~2주차 | 03_analyze 프롬프트 설계 + Gemini 연동 | `03_analyze/prompts/` |
| 6월 3주차 | 샘플 10개 영상 분석 → 정확도 검증 | `validation/` |
| 6월 4주차 | 졸프1 데모용 데이터셋 ("유튜브 영상 → 종목별 확신도") 완성 | `data/analysis/` |

### 졸프2 (9~12월) — 백테스팅 + 신뢰도 시각화

| 시기 | 작업 | 디렉토리 |
|---|---|---|
| 9월 | yfinance 연동, 백테스팅 엔진 설계 | `04_backtest/` |
| 10월 | 전체 백테스팅 + 통계 분석 (확신도 vs 실제 수익률 상관관계) | `04_backtest/credibility_scorer.py` |
| 11~12월 | 시각화 대시보드 + 최종 보고서 | `data/reports/figures/` |

---

## ⚠ 기획서에 짚어야 할 3가지 설계 결정

### 1. Whisper와 Gemini 역할 — 보완 관계로 설계

기획서엔 Whisper와 Gemini 둘 다 사용한다고 적혀있는데, Gemini는 영상만 줘도 자체 ASR을 합니다. 중복 방지를 위해 다음과 같이 역할 분담:

- **Whisper**: 전체 자막 + 추천 동사 키워드 매칭으로 **추천 구간 후보 timestamp**만 추출 (싸고 빠름)
- **Gemini**: Whisper가 찾은 후보 segment **만** 영상+자막 동시 입력 (비싸지만 정확)

→ 영상 전체를 Gemini에 보내지 않고 추천 발화 구간(보통 1~3분)만 보냄 → API 비용 ~70% 절감, 분석 품질 유지

### 2. mp4 삭제 시점 (논의사항 #2 결정안)

`03_analyze/cleanup.py`에서 다음 정책 권장:
- Gemini 분석 성공 + JSON 스키마 검증 통과 → 즉시 삭제
- 실패 시 (네트워크 에러, JSON 파싱 실패) → 보관, retry 큐에 등록
- `.env`의 `VIDEOS_RETENTION=keep`로 설정하면 삭제 비활성 (디버깅 모드)

### 3. Gemini 라벨의 정확도 검증

- `validation/manual_labels.csv`에 팀 라벨링 결과 저장
- `validation/compare_with_gemini.ipynb`에서 일치율 측정
- 정확도 80% 미만 시 → 프롬프트 보완 또는 Gemini 2.5-pro로 모델 업그레이드

발표 시 "AI 라벨의 정확도는 어떻게 보장했냐"에 대한 답변용.

---

### 1. 채널 리스트업 (`01_collect/channels.txt`)

후보 (영어 미국 주식 분석 채널, 활동 활발):
- Joseph Carlson (`UCbpZflYE6r5dILEnSpEAm0g`)
- Meet Kevin (`UCUvvj5lwue7PspotMDjk5UA`)
- Graham Stephan (`UCV6KDgJskWaEckne5aPA0aQ`)
- Stock Moe (`UCCmEnRGE3qsAhwHNTAycHJg`)
- Felix & Friends (Goat Academy)
- Tom Nash
- Couch Investor
- ...

### 2. mp4 즉시 삭제 정책


### 3. 수익률 평가 윈도우

`04_backtest/windows.json` 기본값:
```json
{
  "windows": [
    {"name": "1week",  "days": 7},
    {"name": "1month", "days": 30},
    {"name": "3month", "days": 90}
  ]
}
```

장기 윈도우 추가 시 (6개월/1년) yfinance 데이터 충분성 확인 필요 (분석 영상이 2024년 이후라면 1년 윈도우는 최근 영상에 적용 불가).

대안으로 Polygon.io 주가 데이터 사용할 수 있는 여지도 존재.

---

## 비용 견적 (졸프1 기준)

| 항목 | 단가 | 50개 영상 분석 시 |
|---|---|---|
| YouTube Data API | 무료 (10K units/일) | 0원 (쿼터 내) |
| Whisper (로컬) | 무료 | 0원 (전기료 ~) |
| Gemini API (2.5-flash, 후보 segment만 입력) | $0.075 / 1M input tokens | ~$3 |
| yfinance | 무료 | 0원 |
| **합계** | | **~$5 (졸프1 전체)** |

본격 백테스팅 단계(영상 500개+)로 가면 Gemini 비용이 ~$30-50 수준으로 증가

---

## 팀원별 담당 모듈

| 이름 | 담당 디렉토리 |
|---|---|
| **하재아** (시스템 통합) | `run_pipeline.py`, `04_backtest/`, `shared/csv_schemas.py` |
| **정수혁** (AI/Prompt) | `02_transcribe/`, `03_analyze/` (특히 `prompts/`), `validation/` |
| **오세찬** (데이터/Infra) | `01_collect/`, `shared/utils.py`, `04_backtest/price_fetcher.py` |
