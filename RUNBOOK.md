# VideoConviction 실행 가이드

> 수정 이력은 `CHANGES.md` 참고.

---

## 프로젝트 개요

미국 핀튜버(금융 유튜버) 신뢰도 분석 시스템.  
유튜버가 추천한 주식을 실제로 샀으면 수익이 났는지 검증하는 파이프라인.

```
1. youtube_data_pipeline   YouTube 영상 수집 → 메타데이터, 댓글, 트랜스크립트 생성
        ↓ preliminary_dataset.csv
2. prompting               영상을 Gemini에 업로드 → 주식 추천 여부, 종목, 확신도(1~3) 자동 라벨링
        ↓ gemini_output.csv
3. data_analysis           페니스톡($5 이하) 제거 필터링
        ↓ non_penny_recommendations.csv
4. back_testing            yfinance로 실제 주가 데이터 → 수익성 백테스팅
        ↓ backtest_results.csv
```

> **참고**: 원본 코드에는 `process_annotations_pipeline` (사람 라벨링 단계)이 있었지만 우리 프로젝트는 건너뜀. Gemini 결과를 바로 신뢰하고 back_testing으로 진행.

---

## 0. 사전 준비

### 필요한 계정 및 API 키

| 항목 | 발급 위치 | 용도 |
|---|---|---|
| YouTube Data API 키 | Google Cloud Console → YouTube Data API v3 활성화 | 유튜브 영상 수집 |
| Google AI API 키 | [aistudio.google.com](https://aistudio.google.com) → Get API key | Gemini 영상 분석 |

> **Google AI API 키 주의**: 결제 활성화 필요 (Google Cloud Console → 결제 계정 연결).

### .env 파일 생성

`VideoConviction/.env` 파일을 직접 생성:

```
YOUTUBE_API_KEY="발급받은_유튜브_키"
GOOGLE_API_KEY="발급받은_구글_AI_키"
```

> **절대 git에 커밋하지 말 것** — `.gitignore`에 등록되어 있음.

---

## 1. 환경 설정

### conda 환경 생성

```bash
cd VideoConviction
conda env create -f environment.yml
conda activate finfluencer-credibility
pip install backtrader    # back_testing용 (conda 미포함)
```

> **Apple Silicon Mac 주의**: `back_testing/environment.yml` (구버전)은 `libgfortran.5.dylib` 충돌로 사용 불가 — 이미 삭제됨. `finfluencer-credibility` 환경 하나로 전 단계 통합.

---

## 2. 단계별 실행

### 1단계: youtube_data_pipeline

```bash
conda activate finfluencer-credibility
cd VideoConviction/youtube_data_pipeline
python run_pipeline.py
```

**현재 설정값 (테스트용)**
- `total_videos_to_sample = 1`
- `past_years_to_consider = 1`
- `channels/channel_ids.txt`: 채널 1개 (`UCAHr-sT0AjrD3sBwr1eRUNg`)
- Whisper 모델: `large-v2` — 느리면 `transcripts/transcript_generator.py`에서 `tiny` / `base` / `small` / `medium`으로 변경

**결과물**
```
youtube_data_pipeline/
├── dataset/
│   ├── preliminary_dataset.csv   ← 2단계 입력
│   └── transcript_files/
├── videos/                        ← 다운로드된 영상 (.mp4)
└── audios/                        ← 추출된 오디오 (.mp3)
```

---

### 2단계: prompting (Gemini 멀티모달)

```bash
conda activate finfluencer-credibility
cd VideoConviction/prompting/inference
python run_gemini.py
```

**동작 방식**
- `videos/{video_id}.mp4`를 Gemini에 직접 업로드 (멀티모달 VLM)
- 영상 + 트랜스크립트 텍스트를 함께 넘겨 분석
- 표정, 어조, 발언 내용을 종합해 종목/확신도 추출
- **중단 후 재실행 시 이미 처리된 영상 자동 스킵** (영상마다 즉시 저장)
- 영상 파일 없는 항목은 자동 스킵

**결과물**: `prompting/inference/outputs/gemini_output.csv`

```json
{
  "Stock Recommendations Present": "Yes",
  "Recommendations": [{
    "Action": "Buy",
    "Justification": "...",
    "Conviction Score": "3",
    "Ticker Name": "ABR"
  }]
}
```

---

### 3단계: data_analysis

```bash
conda activate finfluencer-credibility
cd VideoConviction/data_analysis/notebooks
python run_data_analysis.py
```

- `gemini_response` JSON 파싱 → 종목별 행 분리
- yfinance로 현재가 조회 → $5 이하(페니스톡) 제거

**결과물**: `data_analysis/notebooks/non_penny_recommendations.csv`

---

### 4단계: back_testing

```bash
conda activate finfluencer-credibility
cd VideoConviction/back_testing
python run_backtest.py
```

- yfinance로 과거 주가 다운로드 (`auto_adjust=True`)
- 전략 비교: HoldQQQ, HoldSP500, BuyAndHold_6M, BuyAndHold_1Y, BuyAndHoldWeighted, YouTuberInverse, UnclearAsBuy

**결과물**: `back_testing/computed_data/backtest_results.csv`

---

## 3. 자주 발생하는 오류

### `ModuleNotFoundError: No module named 'whisper'`
```bash
pip install openai-whisper
```
PyPI의 `whisper` 패키지는 별개임. 반드시 `openai-whisper` 설치.

---

### `API key not valid` (Gemini)
- `.env`의 `GOOGLE_API_KEY` 확인
- Google AI Studio에서 새 키 발급
- Google Cloud Console에서 결제 활성화 여부 확인

---

### `Files.upload() got an unexpected keyword argument 'path'`
`google-genai` 신규 SDK에서는 `path=` 대신 `file=` 사용:
```python
client.files.upload(file=video_path)  # 올바른 방식
```

---

### `google.generativeai` FutureWarning
구버전 SDK deprecated 경고. `run_gemini.py`는 이미 신규 SDK(`google-genai`)로 교체됨. 다른 파일에서 `import google.generativeai`를 쓰고 있다면 무시해도 되지만, 장기적으로 신규 SDK로 전환 권장.

---

### `libgfortran.5.dylib` 오류 (Apple Silicon Mac)
구버전 `back_testing_env` 환경에서 발생하는 오류. 이미 삭제됨. `finfluencer-credibility` 환경 사용.

---


### Gemini 2단계가 중간에 끊겼을 때
그냥 다시 실행하면 됨. 이미 처리된 영상은 자동 스킵하고 이어서 진행.

---

## 4. Gemini API 비용 참고

Gemini 2.5 Flash 기준 (입력 $0.15/1M 토큰, 출력 $0.60/1M 토큰).  
영상은 약 **263 토큰/초**로 환산되며, 비용의 대부분이 여기서 발생.

| 영상 수 | 평균 길이 | 예상 비용 |
|---|---|---|
| 10개 | ~10분 | ~$0.26 |
| 50개 | ~10분 | ~$1.30 |
| 100개 | ~10분 | ~$2.60 |

> 텍스트 전용 방식 대비 멀티모달(영상 업로드)이 약 **50배 비쌈**.  
> thinking 모드는 `thinking_budget=0`으로 비활성화되어 있음 (기본 출력 요금 적용).

---

## 5. Git 설정

- 레포: `https://github.com/Graduation-Project-Fintech/Notebook`
- 브랜치: `setup/init`
- remote: `graduation`
- 푸시: `git push graduation setup/init`
- **현재 상태**: 조직 push 권한 대기 중 (`Jae-ah` 계정 Collaborator 추가 필요)

---

## 6. 보안 주의

- `data_analysis/install.sh`에 하드코딩됐던 구 YouTube API 키(`AIzaSyC_yH2-4h3GPbCMmTczuv-tJCUmgE0J9rw`)가 git 이력에 남아 있음 → Google Cloud Console에서 폐기(revoke) 필요
