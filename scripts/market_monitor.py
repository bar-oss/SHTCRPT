import argparse
import time
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from ta.momentum import RSIIndicator
from ta.trend import MACD


COINGECKO_ETH = "https://api.coingecko.com/api/v3/coins/ethereum"
BINANCE_KLINES = (
    "https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=1h&limit=100"
)
FUNDING_RATE = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT&limit=1"
OPEN_INTEREST = "https://fapi.binance.com/fapi/v1/openInterest?symbol=ETHUSDT"
COINGECKO_BTC = "https://api.coingecko.com/api/v3/coins/bitcoin"
COINGECKO_GLOBAL = "https://api.coingecko.com/api/v3/global"
FEAR_GREED = "https://api.alternative.me/fng/"
FOREX_FACTORY = "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"


class MarketSnapshot:
    def __init__(self):
        self.eth_price: float = 0.0
        self.market_cap: float = 0.0
        self.volume: float = 0.0
        self.rsi: float = 0.0
        self.macd: float = 0.0
        self.funding_rate: float = 0.0
        self.open_interest: float = 0.0
        self.btc_dominance: float = 0.0
        self.fear_greed: int = 0
        self.macro_events: list[dict] = []


def fetch_eth_market(snapshot: MarketSnapshot) -> None:
    resp = requests.get(COINGECKO_ETH, timeout=10)
    data = resp.json()["market_data"]
    snapshot.eth_price = data["current_price"]["usd"]
    snapshot.market_cap = data["market_cap"]["usd"]
    snapshot.volume = data["total_volume"]["usd"]


def fetch_rsi_macd(snapshot: MarketSnapshot) -> None:
    resp = requests.get(BINANCE_KLINES, timeout=10)
    klines = resp.json()
    closes = [float(k[4]) for k in klines]
    df = pd.DataFrame({"close": closes})
    snapshot.rsi = RSIIndicator(close=df["close"], window=14).rsi().iloc[-1]
    snapshot.macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9).macd_diff().iloc[-1]


def fetch_funding_rate(snapshot: MarketSnapshot) -> None:
    resp = requests.get(FUNDING_RATE, timeout=10)
    snapshot.funding_rate = float(resp.json()[0]["fundingRate"])


def fetch_open_interest(snapshot: MarketSnapshot) -> None:
    resp = requests.get(OPEN_INTEREST, timeout=10)
    snapshot.open_interest = float(resp.json()["openInterest"])


def fetch_btc_dominance(snapshot: MarketSnapshot) -> None:
    btc = requests.get(COINGECKO_BTC, timeout=10).json()["market_data"]["market_cap"]["usd"]
    total = requests.get(COINGECKO_GLOBAL, timeout=10).json()["data"]["total_market_cap"]["usd"]
    snapshot.btc_dominance = btc / total * 100


def fetch_fear_greed(snapshot: MarketSnapshot) -> None:
    resp = requests.get(FEAR_GREED, timeout=10)
    snapshot.fear_greed = int(resp.json()["data"][0]["value"])


def fetch_macro_events(snapshot: MarketSnapshot) -> None:
    try:
        resp = requests.get(FOREX_FACTORY, timeout=10)
        snapshot.macro_events = resp.json()
    except Exception:
        snapshot.macro_events = []


def gather_data() -> MarketSnapshot:
    snap = MarketSnapshot()
    fetch_eth_market(snap)
    fetch_rsi_macd(snap)
    fetch_funding_rate(snap)
    fetch_open_interest(snap)
    fetch_btc_dominance(snap)
    fetch_fear_greed(snap)
    fetch_macro_events(snap)
    return snap


def evaluate(snapshot: MarketSnapshot, last_oi: Optional[float]) -> Optional[str]:
    buy = (
        snapshot.rsi > 60
        and snapshot.macd > 0
        and snapshot.eth_price > 3550
        and snapshot.btc_dominance < 59.5
        and snapshot.funding_rate <= 0
        and (last_oi is not None and snapshot.open_interest > last_oi)
        and snapshot.fear_greed > 60
    )
    sell = (
        snapshot.rsi < 40
        and snapshot.macd < 0
        and snapshot.eth_price < 3550
        and snapshot.btc_dominance > 59.5
        and snapshot.funding_rate > 0
        and (last_oi is not None and snapshot.open_interest < last_oi)
        and snapshot.fear_greed < 40
    )
    if buy:
        return "GO LONG"
    if sell:
        return "SELL"
    return None


def main(run_forever: bool = True) -> None:
    last_oi: Optional[float] = None
    last_message = 0.0
    while True:
        try:
            snap = gather_data()
            signal = evaluate(snap, last_oi)
            if signal:
                print(signal)
                last_message = time.time()
            elif time.time() - last_message >= 3600:
                print("I'm still checking")
                last_message = time.time()
            last_oi = snap.open_interest
        except Exception as exc:  # pragma: no cover - best effort logging
            print(f"Error: {exc}")
        if not run_forever:
            break
        time.sleep(300)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single iteration and exit",
    )
    args = parser.parse_args()
    main(run_forever=not args.once)
