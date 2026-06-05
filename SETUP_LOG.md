# 프로젝트 셋업 로그

## 프로젝트 개요
미국 핀튜버(금융 유튜버) 신뢰도 분석 시스템.  
유튜버가 추천한 주식을 실제로 샀으면 수익이 났는지 검증하는 파이프라인.

---

## 전체 파이프라인 흐름

```
1. youtube_data_pipeline      YouTube 영상 수집 → 메타데이터, 댓글, 트랜스크립트 생성
        ↓ preliminary_dataset.csv
2. prompting (Gemini API)     트랜스크립트 분석 → 주식 추천 여부, 종목, 확신도(1~3) 자동 라벨링
        ↓ gemini_output.csv
3. data_analysis              페니스톡($5 이하) 제거 필터링
        ↓ non_penny_recommendations.csv
4. back_testing               yfinance로 실제 주가 데이터 → 수익성 검증
```

> **참고**: 원래 코드는 `process_annotations_pipeline`(사람이 직접 라벨링한 정답지와 합치는 단계)이 있었지만, **우리 프로젝트는 이 단계를 건너뜀**. Gemini 결과를 바로 신뢰하고 back_testing으로 진행.

---

## 환경 설정

### conda 환경
- 환경 이름: `finfluencer-credibility`
- 환경 파일 위치: `VideoConviction/environment.yml`
- 설치 명령:
  ```bash
  cd VideoConviction
  conda env create -f environment.yml
  conda activate finfluencer-credibility
  ```

### 환경 구조
- `VideoConviction/environment.yml` → 통합 환경 (youtube_data_pipeline, prompting, data_analysis 전부 포함)
- `VideoConviction/back_testing/environment.yml` → back_testing 전용 별도 환경 (충돌 위험으로 분리)

### 주요 패키지
| 패키지 | 용도 |
|---|---|
| `openai-whisper` | 음성→텍스트 (주의: PyPI의 `whisper`는 다른 패키지임) |
| `yt-dlp` | YouTube 영상 다운로드 |
| `google-api-python-client` | YouTube Data API v3 |
| `google-generativeai==0.8.*` | Gemini API |
| `ffmpeg` | 영상→오디오 추출 |
| `deno` | yt-dlp YouTube 포맷 추출용 JS 런타임 |
| `yfinance` | 미국 주식 과거 시세 |

---

## youtube_data_pipeline 설정

### 필요한 것
- YouTube Data API 키 (Google Cloud Console에서 발급, YouTube Data API v3 활성화 필요)
- `.env` 파일: `VideoConviction/youtube_data_pipeline/.env`
  ```
  YOUTUBE_API_KEY="발급받은_키"
  ```

### 실행 방법
```bash
conda activate finfluencer-credibility
cd VideoConviction/youtube_data_pipeline
python run_pipeline.py
```

### 현재 설정값 (테스트용)
- `total_videos_to_sample = 1` (기본값 10에서 변경)
- `past_years_to_consider = 1` (기본값 3에서 변경)
- `channel_ids.txt`: 채널 1개만 (`UCAHr-sT0AjrD3sBwr1eRUNg`)

### 결과물 저장 위치
```
youtube_data_pipeline/
├── dataset/
│   ├── video_ids.text
│   ├── videos_metadata.csv
│   ├── videos_comments.csv
│   ├── channels_metadata.csv
│   ├── filtered_dataset.csv
│   ├── sampled_dataset.csv
│   ├── video_transcriptions.csv
│   ├── preliminary_dataset.csv     ← 최종 결과물 (다음 단계 입력)
│   └── transcript_files/
├── videos/                          ← 다운로드된 영상 (.mp4)
└── audios/                          ← 추출된 오디오 (.mp3)
```

---

## 수정된 코드 목록

### 1. `run_pipeline.py`
- `--generate_segment_wise_transcripts` 인자 추가 (없으면 AttributeError 발생)
- `--total_videos_to_sample` 기본값 → 1 (테스트용)
- `--past_years_to_consider` 기본값 → 1 (테스트용)

### 2. `transcripts/transcript_generator.py`
- `import torch` 추가
- `get_device()` 함수 추가: CUDA → MPS → CPU 순으로 자동 선택
- `whisper.load_model("large-v2", device=get_device())` 로 변경
  - M시리즈 Mac: MPS 사용 (3~5배 빠름)
  - Windows NVIDIA: CUDA 사용
  - 그 외: CPU 사용

### 3. `channels/channel_ids.txt`
- 테스트용으로 채널 1개만 남김

### 4. `environment.yaml` (youtube_data_pipeline 내부)
- 구버전, 더 이상 사용 안 함 (통합 환경으로 대체)

---

## 다음 단계: Gemini 프롬핑 수정

`prompting/inference/GeminiPrompt.ipynb`을 `preliminary_dataset.csv` 직접 입력 받도록 수정 필요.

### 수정할 내용
1. **Colab 코드 제거**
   ```python
   # 삭제
   from google.colab import drive
   drive.mount('/content/drive')
   ```

2. **데이터 경로 변경**
   ```python
   data_path = '../../youtube_data_pipeline/dataset/preliminary_dataset.csv'
   ```

3. **Gemini API 키 입력**
   ```python
   GOOGLE_API_KEY = '발급받은_키'
   ```

4. **컬럼명 변환**
   ```python
   data = data.rename(columns={'videoId': 'video_id', 'videoTitle': 'video_title'})
   ```

5. **필터링 조건 변경** (사람 라벨 기반 → 트랜스크립트 기반)
   ```python
   data = data.loc[
       (~data['transcript'].isna()) &
       (data['transcript'].str.strip() != "")
   ]
   ```

6. **전체 트랜스크립트 모드 사용**
   ```python
   prompt = segment_create_prompt(series=series, lm_type='lm', whole=True)
   ```

---

## Git 설정

- 레포: `https://github.com/Graduation-Project-Fintech/Notebook`
- 현재 브랜치: `setup/init`
- remote 이름: `graduation`
- 푸시 명령: `git push graduation setup/init`
- **현재 상태**: 조직 push 권한 대기 중 (`Jae-ah` 계정을 조직 Collaborator로 추가 필요)
