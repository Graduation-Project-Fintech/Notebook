import os, json, time
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
model_id = 'gemini-2.5-flash'
temperature = 0.0
data_path = '../../youtube_data_pipeline/dataset/preliminary_dataset.csv'
video_dir = '../../youtube_data_pipeline/videos'
output_path = './outputs/gemini_output.csv'


def extract_json_or_list(output):
    start = output.find("```json")
    if start != -1:
        start += len("```json")
        end = output.find("```", start)
        if end != -1:
            return output[start:end].strip()
    start = output.find('{')
    if start != -1:
        end = output.rfind('}')
        if end != -1:
            return output[start:end+1].strip()
    return output


def load_gemini_client():
    return genai.Client(api_key=GOOGLE_API_KEY)


def upload_video(client, video_path):
    video_file = client.files.upload(file=video_path)
    while video_file.state.name == 'PROCESSING':
        time.sleep(10)
        video_file = client.files.get(name=video_file.name)
    if video_file.state.name == 'FAILED':
        raise ValueError(f'Video processing failed: {video_file.state.name}')
    print(f'  업로드 완료: {video_file.uri}')
    return video_file


def segment_create_prompt(series, lm_type='vlm', whole=True):
    title = series['video_title']

    if whole:
        transcript = series['transcript']

    if lm_type == 'vlm':
        facial_expression = (
            "\n           - Facial Expressions: Neutral or doubtful (furrowed brows, pursed lips).",
            "\n           - Facial Expressions: Moderate enthusiasm (mild smiles, slightly raised eyebrows).",
            "\n           - Facial Expressions: Enthusiastic, energetic (wide smiles, raised eyebrows)."
        )
    else:
        facial_expression = ("", "", "")

    if lm_type == 'vlm' and whole:
        yt_video_statement = "video excerpt, "
    else:
        yt_video_statement = ""

    if whole:
        whole_transcript_specific = (
            " and video title",
            f"""Inputs:
    - Video Title: {title}
    - Transcript: {transcript}""",
            "\n           - Consistency: Low conviction if the title makes a bold claim, but the transcript lacks matching conviction.",
            "\n           - Consistency: Medium conviction if the title makes a bold claim, followed by consistent confidence in the transcript.",
            "\n           - Consistency: High conviction if the title and transcript are strongly aligned."
        )

    prompt = f"""Analyze the YouTube {yt_video_statement}transcript segment{whole_transcript_specific[0]} of an influencer discussing the US stock market. Identify the single stock recommendation and assess its conviction level.
    {whole_transcript_specific[1]}

    Instructions:
    1. Does the video contain a stock recommendation:
       - Label this as `Stock Recommendation Present` with either "Yes" or "No".

    2. If `Stock Recommendation Present` is "Yes", store the single stock recommendation under the key "Recommendation", formatted as a one-item list. The recommendation should follow this structure:{{"Action": "Buy | Hold | Don't Buy | Sell | Short Sell | Unclear",
         "Justification": "Brief explanation for the action based on the transcript",
         "Conviction Score": "1 | 2 | 3",
         "Ticker Name": "Ticker name"}}

       Details for each field:
        - `Action`: Categorize the recommendation as:
          - "Buy": Purchase shares of the stock.
          - "Hold": Retain the stock if already owned.
          - "Don't Buy": Refrain from purchasing the stock.
          - "Sell": Sell shares currently owned.
          - "Short Sell": Sell shares not currently owned, intending to buy them back later at a lower price.
          - "Unclear": When the action is not explicitly stated.
       - `Justification`: Provide a brief explanation for the action based on the transcript.
       - `Conviction Score`: Assign a score based on the following criteria:
         - "1" (Low Conviction):
           - Tone: Hesitant or uncertain language, frequent qualifiers (e.g., "maybe," "possibly").{facial_expression[0]}
           - Delivery: Reserved or doubtful language.{whole_transcript_specific[2]}
         - "2" (Moderate Conviction):
           - Tone: Relatively confident language with some qualifiers.{facial_expression[1]}
           - Delivery: Balanced and moderately positive language.{whole_transcript_specific[3]}
         - "3" (High Conviction):
           - Tone: Strong, assertive language without hesitation.{facial_expression[2]}
           - Delivery: Decisive recommendations with no qualifiers.{whole_transcript_specific[4]}
       - `Ticker Name`: Specify the ticker name of the stock being discussed.

    3. If `Stock Recommendation Present` is "No", return the following structure:{{"Stock Recommendation Present": "No",
         "Recommendation": []
       }}

    Output Requirements:
    - Return only valid JSON that can be directly parsed by JSON libraries.
    - Do not include any additional text, comments, formatting indicators (e.g., `json` or backticks), or explanatory content.
    """
    return prompt


def main():
    data = pd.read_csv(data_path)
    data = data.rename(columns={
        'videoId': 'video_id', 'videoTitle': 'video_title',
        'channelId': 'channel_id', 'publishedAt': 'published_at'
    })
    data = data[data['transcript'].notna() & (data['transcript'].str.strip() != '')].reset_index(drop=True)

    # 영상 파일이 존재하는 행만 처리
    data['video_path'] = data['video_id'].apply(lambda vid: os.path.join(video_dir, f"{vid}.mp4"))
    data = data[data['video_path'].apply(os.path.exists)].reset_index(drop=True)
    print(f"분석할 영상 수: {len(data)}")

    # 이미 처리된 영상 스킵
    os.makedirs('./outputs', exist_ok=True)
    if os.path.exists(output_path):
        existing = pd.read_csv(output_path)
        done_ids = set(existing['video_id'].tolist())
        results = existing.to_dict('records')
        print(f"기존 결과 {len(done_ids)}개 로드 — 이미 처리된 영상 스킵")
    else:
        done_ids = set()
        results = []

    client = load_gemini_client()

    for idx, row in data.iterrows():
        if row['video_id'] in done_ids:
            print(f"[스킵] {row['video_title'][:60]}")
            continue

        print(f"\n[{idx+1}/{len(data)}] {row['video_title'][:60]}...")

        try:
            print("  영상 업로드 중...")
            video_file = upload_video(client, row['video_path'])

            prompt = segment_create_prompt(row, lm_type='vlm', whole=True)
            response = client.models.generate_content(
                model=model_id,
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )
            raw = extract_json_or_list(response.text)
            print(f"  응답: {raw[:200]}")

            client.files.delete(name=video_file.name)

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"parse_error": True, "raw": raw}

        except Exception as e:
            print(f"  오류: {e}")
            parsed = {"error": str(e)}

        results.append({
            'video_id': row['video_id'],
            'video_title': row['video_title'],
            'channel_id': row.get('channel_id', ''),
            'published_at': row.get('published_at', ''),
            'gemini_response': json.dumps(parsed)
        })
        # 영상마다 즉시 저장 (중간에 꺼져도 복구 가능)
        pd.DataFrame(results).to_csv(output_path, index=False)

    print(f"\n완료! 저장 위치: {output_path}")


if __name__ == '__main__':
    main()
