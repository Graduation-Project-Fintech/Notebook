import os
import pickle
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from datetime import datetime
from collections import defaultdict, Counter
import backtrader as bt
import yfinance as yf

# ── 설정 ──────────────────────────────────────────────────────────────────
INPUT_PATH = '../data_analysis/notebooks/non_penny_recommendations.csv'
HISTORICAL_SAVE_PATH = './historical_data'
START_DATE = datetime(2018, 1, 1).date()
END_DATE = datetime(2024, 8, 1).date()

np.random.seed(42)
pd.set_option('display.float_format', '{:.2f}'.format)
pd.set_option('display.max_columns', None)

os.makedirs(HISTORICAL_SAVE_PATH, exist_ok=True)
os.makedirs('computed_data', exist_ok=True)
os.makedirs('computed_graphics', exist_ok=True)


# ── 티커 정제 ─────────────────────────────────────────────────────────────
ticker_corrections = {
    'APPL': 'AAPL', 'GOOGL': 'GOOG', 'FB': 'META',
    'GLDLF': 'GLDG', 'HLIX': 'HLX', 'AI†': 'AI', 'SKWS': 'SWKS'
}

def process_ticker(ticker):
    if pd.isnull(ticker):
        return None
    ticker = ticker.strip().upper().split(':')[-1].split(' ')[-1].strip()
    return ticker_corrections.get(ticker, ticker)


# ── 주가 데이터 수집 (yfinance) ────────────────────────────────────────────
def fetch_and_save_ticker_data(ticker, start_date, end_date, save_path):
    file_path = os.path.join(save_path, f"{ticker}.csv")
    if os.path.exists(file_path):
        return True
    df = yf.download(ticker, start=start_date, end=end_date,
                     auto_adjust=True, progress=False)
    if df.empty:
        print(f"  데이터 없음: {ticker}")
        return False
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.to_csv(file_path)
    return True


# ── Backtrader 데이터 피드 ─────────────────────────────────────────────────
class MyPandasData(bt.feeds.PandasData):
    params = (('nullvalue', float('nan')), ('plot', False), ('datetime', None),
              ('open', 'Open'), ('high', 'High'), ('low', 'Low'),
              ('close', 'Close'), ('volume', 'Volume'), ('openinterest', None))


# ── 전략 클래스들 ──────────────────────────────────────────────────────────
class HoldSP500Strategy(bt.Strategy):
    params = (('hold_period', 365), ('allocation_per_trade', 1.0),
              ('strategy_recs', {}), ('last_date', None), ('max_size', 100))

    def __init__(self):
        self.start_traded = False

    def next(self):
        if not self.start_traded:
            for data in self.datas:
                if data._name == 'SPY':
                    cash = self.broker.getcash()
                    size = int(cash / max(data.close[0], 1e-6))
                    if size > 0:
                        self.buy(data=data, size=size)
            self.start_traded = True

    def stop(self):
        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0:
                self.sell(data=data, size=pos.size)


class HoldQQQStrategy(bt.Strategy):
    params = (('hold_period', 365), ('allocation_per_trade', 1.0),
              ('strategy_recs', {}), ('last_date', None), ('max_size', 100))

    def __init__(self):
        self.start_traded = False

    def next(self):
        if not self.start_traded:
            for data in self.datas:
                if data._name == 'QQQ':
                    cash = self.broker.getcash()
                    size = int(cash / max(data.close[0], 1e-6))
                    if size > 0:
                        self.buy(data=data, size=size)
            self.start_traded = True

    def stop(self):
        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0:
                self.sell(data=data, size=pos.size)


class BuyAndHoldStrategy(bt.Strategy):
    params = (('hold_period', 365), ('allocation_per_trade', 1.0),
              ('strategy_recs', {}), ('last_date', None), ('max_size', 100))

    def __init__(self):
        self.buy_dates = {}
        self.strategy_recs = self.params.strategy_recs

    def next(self):
        current_date = self.datetime.date(0)
        buys = []
        for data in self.datas:
            pos = self.getposition(data)
            ticker = data._name
            recommendations = self.strategy_recs.get((ticker, current_date), [])
            for rec in recommendations:
                if rec['action'] == 'Buy' and not pos:
                    buys.append(data)
        if buys:
            allocation = self.broker.getcash() / len(buys)
            for data in buys:
                size = min(self.params.max_size,
                           int(allocation / max(data.close[0], 1e-6)))
                if size > 0:
                    self.buy(data=data, size=size)
                    self.buy_dates[data] = current_date

        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0 and data in self.buy_dates:
                if ((current_date - self.buy_dates[data]).days >= self.params.hold_period
                        or current_date == self.params.last_date):
                    self.sell(data=data, size=pos.size)
                    del self.buy_dates[data]


class BuyAndHoldWeightedStrategy(bt.Strategy):
    params = (('hold_period', 365), ('allocation_per_trade', 1.0),
              ('strategy_recs', {}), ('last_date', None), ('max_size', 100))

    def __init__(self):
        self.buy_dates = {}
        self.strategy_recs = self.params.strategy_recs

    def next(self):
        current_date = self.datetime.date(0)
        buys = []
        total_conviction = 0
        for data in self.datas:
            ticker = data._name
            for rec in self.strategy_recs.get((ticker, current_date), []):
                if rec['action'] == 'Buy' and not self.getposition(data):
                    buys.append((data, int(rec['conviction_score'])))
                    total_conviction += int(rec['conviction_score'])
        if buys and total_conviction > 0:
            cash = self.broker.getcash()
            for data, score in buys:
                alloc = cash * (score / total_conviction)
                size = min(self.params.max_size,
                           int(alloc / max(data.close[0], 1e-6)))
                if size > 0:
                    self.buy(data=data, size=size)
                    self.buy_dates[data] = current_date

        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0 and data in self.buy_dates:
                if ((current_date - self.buy_dates[data]).days >= self.params.hold_period
                        or current_date == self.params.last_date):
                    self.sell(data=data, size=pos.size)
                    del self.buy_dates[data]


class YouTuberInverseStrategy(bt.Strategy):
    params = (('hold_period', 365), ('allocation_per_trade', 1.0),
              ('strategy_recs', {}), ('last_date', None), ('max_size', 100))

    def __init__(self):
        self.sell_dates = {}
        self.strategy_recs = self.params.strategy_recs

    def next(self):
        current_date = self.datetime.date(0)
        for data in self.datas:
            ticker = data._name
            pos = self.getposition(data)
            for rec in self.strategy_recs.get((ticker, current_date), []):
                if rec['action'] == 'Buy' and not pos:
                    size = min(self.params.max_size,
                               int(self.broker.getcash() / max(data.close[0], 1e-6)))
                    if size > 0:
                        self.sell(data=data, size=size)
                        self.sell_dates[data] = current_date
            if pos.size < 0 and data in self.sell_dates:
                if ((current_date - self.sell_dates[data]).days >= self.params.hold_period
                        or current_date == self.params.last_date):
                    self.buy(data=data, size=abs(pos.size))
                    del self.sell_dates[data]


class UnclearAsBuyStrategy(bt.Strategy):
    params = (('hold_period', 365), ('allocation_per_trade', 1.0),
              ('strategy_recs', {}), ('last_date', None), ('max_size', 100))

    def __init__(self):
        self.buy_dates = {}
        self.strategy_recs = self.params.strategy_recs

    def next(self):
        current_date = self.datetime.date(0)
        buys = []
        for data in self.datas:
            ticker = data._name
            pos = self.getposition(data)
            for rec in self.strategy_recs.get((ticker, current_date), []):
                if rec['action'] in ['Buy', 'Unclear'] and not pos:
                    buys.append(data)
        if buys:
            allocation = self.broker.getcash() / len(buys)
            for data in buys:
                size = min(self.params.max_size,
                           int(allocation / max(data.close[0], 1e-6)))
                if size > 0:
                    self.buy(data=data, size=size)
                    self.buy_dates[data] = current_date

        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0 and data in self.buy_dates:
                if ((current_date - self.buy_dates[data]).days >= self.params.hold_period
                        or current_date == self.params.last_date):
                    self.sell(data=data, size=pos.size)
                    del self.buy_dates[data]


# ── 백테스트 실행 함수 ─────────────────────────────────────────────────────
def run_backtest(strategy, name, historical_data, start_date, end_date, **strategy_params):
    cerebro = bt.Cerebro()
    strategy_params['last_date'] = last_date
    strategy_params['max_size'] = 100
    cerebro.addstrategy(strategy, **strategy_params)
    for ticker, df in historical_data.items():
        data = MyPandasData(dataname=df, name=ticker,
                            fromdate=start_date, todate=end_date)
        cerebro.adddata(data)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro.broker.setcash(100000.0)
    cerebro.broker.set_coc(True)
    results = cerebro.run()
    strat = results[0]

    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    drawdown = strat.analyzers.drawdown.get_analysis()
    max_drawdown = drawdown.max.drawdown
    portfolio_value = cerebro.broker.getvalue()
    pnl = portfolio_value - 100000.0
    total_return = pnl / 100000.0 * 100
    returns = pd.Series(strat.analyzers.pyfolio.get_analysis()['returns'])
    returns.index = returns.index.tz_localize(None)
    cumulative_returns = (1 + returns).cumprod()
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.total.get('closed', 0)
    winning_trades = trade_analysis.get('won', {}).get('total', 0)
    losing_trades = trade_analysis.get('lost', {}).get('total', 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    all_dates_bt = historical_data[next(iter(historical_data))].index
    total_years = (all_dates_bt.max() - all_dates_bt.min()).days / 365.25
    annualized_return = ((portfolio_value / 100000.0) ** (1 / total_years) - 1) * 100

    return {
        'name': name, 'sharpe_ratio': sharpe_ratio, 'max_drawdown': max_drawdown,
        'pnl': pnl, 'total_return': total_return, 'annualized_return': annualized_return,
        'total_trades': total_trades, 'winning_trades': winning_trades,
        'losing_trades': losing_trades, 'win_rate': win_rate,
        'returns': returns, 'cumulative_returns': cumulative_returns,
    }


# ── 메인 ──────────────────────────────────────────────────────────────────
df_stock = pd.read_csv(INPUT_PATH)
df_stock['conviction_score'] = pd.to_numeric(df_stock['conviction_score'], errors='coerce')
df_stock.dropna(subset=['action', 'conviction_score', 'ticker_name'], inplace=True)

tickers = df_stock['ticker_name'].dropna().unique().tolist() + ['QQQ', 'SPY']
processed_tickers = set(filter(None, [process_ticker(t) for t in tickers]))

print(f"주가 데이터 수집 중: {processed_tickers}")
failed_tickers = []
for ticker in processed_tickers:
    success = fetch_and_save_ticker_data(
        ticker, START_DATE.isoformat(), END_DATE.isoformat(), HISTORICAL_SAVE_PATH)
    if not success:
        failed_tickers.append(ticker)
if failed_tickers:
    print(f"데이터 수집 실패: {failed_tickers}")

historical_data = {}
date_sets = []
for ticker in processed_tickers:
    file = os.path.join(HISTORICAL_SAVE_PATH, f"{ticker}.csv")
    if os.path.exists(file):
        df = pd.read_csv(file, index_col=0, parse_dates=True)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index = pd.to_datetime(df.index).normalize()
        historical_data[ticker] = df
        date_sets.append(df.index)

all_dates = pd.DatetimeIndex(sorted(set().union(*date_sets))).normalize()
for ticker, df in historical_data.items():
    df = df.reindex(all_dates)
    df.ffill(inplace=True)
    df.bfill(inplace=True)
    df['Volume'] = df['Volume'].fillna(0).clip(lower=0)
    df = df[df['Volume'] > 0]
    historical_data[ticker] = df

last_date = all_dates.max().date() if not all_dates.empty else None
start_date = START_DATE
end_date = END_DATE

# 추천 매핑
strategy_recs = defaultdict(list)
for _, row in df_stock.iterrows():
    ticker = process_ticker(row['ticker_name'])
    if not ticker or ticker not in historical_data:
        continue
    date_col = row.get('action_date') if 'action_date' in row and pd.notnull(row.get('action_date')) \
        else row.get('published_at')
    if pd.isnull(date_col):
        continue
    action_date = pd.to_datetime(date_col).date()
    market_dates = historical_data[ticker].index.date
    try:
        snapped_date = min(market_dates, key=lambda d: abs(d - action_date))
    except Exception:
        continue
    strategy_recs[(ticker, snapped_date)].append({
        'ticker': ticker,
        'action': row['action'],
        'conviction_score': int(row['conviction_score'])
    })

print(f"\n추천 수: {sum(len(v) for v in strategy_recs.values())}")
print(f"데이터 기간: {all_dates.min().date()} ~ {all_dates.max().date()}")

# 백테스트 실행
print("\n백테스트 실행 중...")
analyses = []
for strategy, name, kwargs in [
    (HoldQQQStrategy,          'HoldQQQ',          {}),
    (HoldSP500Strategy,        'HoldSP500',        {}),
    (BuyAndHoldStrategy,       'BuyAndHold_6M',    {'strategy_recs': strategy_recs, 'hold_period': 182}),
    (BuyAndHoldStrategy,       'BuyAndHold_1Y',    {'strategy_recs': strategy_recs, 'hold_period': 365}),
    (BuyAndHoldWeightedStrategy,'BuyAndHoldWeighted',{'strategy_recs': strategy_recs}),
    (YouTuberInverseStrategy,  'YouTuberInverse',  {'strategy_recs': strategy_recs}),
    (UnclearAsBuyStrategy,     'UnclearAsBuy',     {'strategy_recs': strategy_recs}),
]:
    result = run_backtest(strategy, name, historical_data, start_date, end_date, **kwargs)
    analyses.append(result)
    print(f"  {name}: 수익률 {result['total_return']:.2f}%, 샤프 {result['sharpe_ratio']}")

# 결과 저장
results_df = pd.DataFrame([{
    'Strategy': a['name'],
    'Total Return (%)': round(a['total_return'], 2),
    'Annualized Return (%)': round(a['annualized_return'], 2),
    'Sharpe Ratio': a['sharpe_ratio'],
    'Max Drawdown (%)': round(a['max_drawdown'], 2),
    'Win Rate (%)': round(a['win_rate'], 2),
    'Total Trades': a['total_trades'],
} for a in analyses])

results_df.to_csv('computed_data/backtest_results.csv', index=False)
print(f"\n결과 저장: computed_data/backtest_results.csv")
print(results_df.to_string(index=False))
