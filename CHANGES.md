# 수정 이력

---

## 1. 환경 통합

원래 단계별로 분리되어 있던 conda 환경을 `finfluencer-credibility` 하나로 통합.

- `VideoConviction/environment.yml`이 통합 환경 파일 (youtube_data_pipeline, prompting, data_analysis, back_testing 전부 포함)
- `backtrader`는 conda 미포함 → `pip install backtrader`로 별도 설치
- `back_testing_env`는 Apple Silicon Mac에서 `libgfortran.5.dylib` 충돌로 사용 불가 → 폐기

**삭제된 파일**

| 파일 | 이유 |
|---|---|
| `youtube_data_pipeline/environment.yaml` | 구버전. `whisper` 패키지명 버그 포함 |
| `youtube_data_pipeline/install.sh` | 구버전 환경 생성 스크립트. 불필요 |
| `data_analysis/install.sh` | 동일 이유 |
| `back_testing/environment.yml` | Apple Silicon Mac 호환 불가 |
| `data/` (폴더 전체) | agentmemory 실행 중 생성된 임시 폴더. 프로젝트 무관 |
| `LICENSE.md` | 프로젝트 무관 |

**수정된 파일**

- `youtube_data_pipeline/run_pipeline.py`: `--generate_segment_wise_transcripts` 인자 추가, `total_videos_to_sample` 기본값 → 1, `past_years_to_consider` 기본값 → 1 (테스트용)
- `youtube_data_pipeline/transcripts/transcript_generator.py`: `get_device()` 추가 (CUDA → MPS → CPU 자동 선택), `whisper.load_model("large-v2", device=get_device())`로 변경
- `youtube_data_pipeline/channels/channel_ids.txt`: 테스트용으로 채널 1개만 남김 (`UCAHr-sT0AjrD3sBwr1eRUNg`)

---

## 2. Colab → 로컬 Python 스크립트 전환 + Polygon.io → yfinance 교체

원본 `.ipynb` 파일들을 로컬 실행 가능한 `.py` 스크립트로 새로 작성. Polygon.io(유료)를 yfinance(무료)로 교체.

### `prompting/inference/run_gemini.py` (신규)

원본 `GeminiPrompt.ipynb` 기반.

| 항목 | 원본 | 변경 후 |
|---|---|---|
| 실행 환경 | Google Colab | 로컬 |
| 데이터 경로 | `./complete_dataset.csv` | `../../youtube_data_pipeline/dataset/preliminary_dataset.csv` |
| API 키 | 코드에 직접 입력 | `.env`에서 `load_dotenv()` 로드 |
| 컬럼명 | `videoId`, `videoTitle` | `video_id`, `video_title` |
| 필터링 | 사람 라벨(`is_rec_present`) 기반 | `transcript` 비어있지 않은 행 기반 |
| 분석 모드 | VLM (세그먼트 영상 + 텍스트, 사람 라벨 필요) | VLM (전체 영상, `client.files.upload()`) |
| SDK | `google-generativeai==0.8.*` (deprecated) | `google-genai` (신규 공식 SDK) |
| 사용 모델 | `gemini-1.5-pro-002` | `gemini-2.5-flash` |
| thinking 모드 | 기본값 | `thinking_budget=0`으로 비활성화 (비용 절감) |
| 중단 재실행 | 처음부터 다시 | 기존 결과 로드 후 처리된 영상 자동 스킵 |
| 저장 방식 | 없음 | 영상마다 즉시 저장 (중간에 꺼져도 결과 보존) |
| 결과 저장 | 없음 | `prompting/inference/outputs/gemini_output.csv` |

### `data_analysis/notebooks/run_data_analysis.py` (신규)

원본 `keep_non_penny_only.ipynb` 기반.

| 항목 | 원본 | 변경 후 |
|---|---|---|
| 주가 조회 | Polygon.io | yfinance (`Ticker.fast_info['lastPrice']`) |
| 입력 파일 | `complete_dataset.csv` | `prompting/inference/outputs/gemini_output.csv` |
| 데이터 파싱 | `ticker_name` 컬럼 바로 사용 | `gemini_response` JSON 파싱 후 추출 |

### `back_testing/run_backtest.py` (신규)

원본 `main.ipynb` 기반.

| 항목 | 원본 | 변경 후 |
|---|---|---|
| 주가 데이터 | Polygon.io | yfinance (`yf.download()`, `auto_adjust=True`) |
| 입력 파일 | `non_penny_recommendations_only.csv` | `non_penny_recommendations.csv` |
| 날짜 컬럼 | `publishedAt` | `published_at` (snake_case 통일) |
| timezone | 없음 | yfinance tz-aware → `.tz_localize(None)` 처리 |

**테스트 결과 (2026-06-06, ABR 1개 영상 기준)**

| 전략 | 수익률 | 샤프지수 |
|---|---|---|
| HoldQQQ | +210.45% | 0.72 |
| HoldSP500 | +127.82% | 0.75 |
| BuyAndHold_6M (ABR) | +0.34% | -7.95 |
| YouTuberInverse | -0.64% | -6.91 |

---

## 3. 보안 & 파일 정리

### API 키 하드코딩 제거

`data_analysis/install.sh`에 하드코딩된 YouTube API 키 제거.  
**주의**: git 이력에 해당 키(`AIzaSyC_yH2-4h3GPbCMmTczuv-tJCUmgE0J9rw`)가 남아 있음 → Google Cloud Console에서 폐기(revoke) 필요.

### `.env` 위치 통합

`GOOGLE_API_KEY`(prompting 단계)와 `YOUTUBE_API_KEY`(youtube_data_pipeline 단계)를 동일 `.env`에서 관리.

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 위치 | `youtube_data_pipeline/.env` | `VideoConviction/.env` (루트) |
| `run_pipeline.py` | `load_dotenv('.env')` | `load_dotenv()` |
| `run_gemini.py` | `load_dotenv('../../youtube_data_pipeline/.env')` | `load_dotenv()` |

`load_dotenv()` (인자 없음)는 현재 디렉토리에서 상위로 자동 탐색하므로 어느 하위 폴더에서 실행해도 루트 `.env`를 자동으로 로드.

### `.gitignore` 통합

`VideoConviction/.gitignore` 신규 생성, 기존 하위 폴더 `.gitignore` 7개 전부 삭제.  
`youtube_data_pipeline`의 고유 항목(`videos/`, `audios/`, `dataset/`, `channels/UC*/`)은 루트 `.gitignore`에 경로 명시하여 병합.

---
