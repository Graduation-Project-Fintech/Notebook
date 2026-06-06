import json
import pandas as pd
import yfinance as yf

INPUT_PATH = '../../prompting/inference/outputs/gemini_output.csv'
OUTPUT_PATH = './non_penny_recommendations.csv'
PENNY_THRESHOLD = 5.0


def get_current_price(ticker):
    try:
        info = yf.Ticker(ticker).fast_info
        return info['lastPrice']
    except Exception as e:
        print(f"  가격 조회 실패 ({ticker}): {e}")
        return None


def parse_gemini_output(df):
    rows = []
    for _, row in df.iterrows():
        try:
            parsed = json.loads(row['gemini_response'])
        except (json.JSONDecodeError, TypeError):
            continue

        if parsed.get('Stock Recommendation Present') != 'Yes':
            continue

        for rec in parsed.get('Recommendation', []):
            ticker = rec.get('Ticker Name', '').strip().upper()
            if not ticker:
                continue
            rows.append({
                'video_id': row['video_id'],
                'video_title': row['video_title'],
                'channel_id': row['channel_id'],
                'published_at': row['published_at'],
                'ticker_name': ticker,
                'action': rec.get('Action', ''),
                'conviction_score': rec.get('Conviction Score', ''),
                'justification': rec.get('Justification', ''),
            })
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(INPUT_PATH)
    print(f"불러온 영상 수: {len(df)}")

    recs = parse_gemini_output(df)
    print(f"추출된 추천 수: {len(recs)}")

    print("\n현재 주가 조회 중 (yfinance)...")
    recs['current_price'] = recs['ticker_name'].apply(
        lambda t: (print(f"  {t}..."), get_current_price(t))[1]
    )

    before = len(recs)
    recs = recs[recs['current_price'] > PENNY_THRESHOLD].copy()
    after = len(recs)
    print(f"\n페니스톡 제거: {before}개 → {after}개 (제거 {before - after}개, 기준 ${PENNY_THRESHOLD})")

    recs.to_csv(OUTPUT_PATH, index=False)
    print(f"\n저장 완료: {OUTPUT_PATH}")
    print(recs[['ticker_name', 'action', 'conviction_score', 'current_price']].to_string(index=False))


if __name__ == '__main__':
    main()
