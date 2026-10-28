import os
import time
import logging
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# ---------------- CONFIGURATION ----------------

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "stock_data.csv"
LOG_FILE = BASE_DIR / "pipeline.log"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
URL = "https://www.alphavantage.co/query"

SYMBOLS = ["IBM", "AAPL", "MSFT", "AMZN"]

# ---------------- LOGGING ----------------

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------- FETCH DATA ----------------

def fetch_stock_data(symbol):
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
        "apikey": API_KEY
    }

    try:
        response = requests.get(
            URL, params=params, timeout=30
        )
        response.raise_for_status()
        result = response.json()

        if "Time Series (Daily)" not in result:
            message = (
                result.get("Note")
                or result.get("Information")
                or result.get("Error Message")
                or str(result)
            )
            logging.error("%s: API error: %s", symbol, message)
            print(f"{symbol}: API error - {message}")
            return None

        df = pd.DataFrame.from_dict(
            result["Time Series (Daily)"],
            orient="index"
        )

        df.index.name = "date"
        df = df.reset_index()

        df.columns = [
            "date", "open", "high",
            "low", "close", "volume"
        ]

        df["symbol"] = symbol
        df["date"] = pd.to_datetime(df["date"])

        numeric_cols = [
            "open", "high", "low", "close", "volume"
        ]

        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        logging.info(
            "%s: fetched %s records", symbol, len(df)
        )
        print(f"{symbol}: fetched {len(df)} records")

        return df

    except requests.RequestException as error:
        logging.exception("%s: request failed", symbol)
        print(f"{symbol}: request failed - {error}")
        return None


# ---------------- SAVE / UPDATE CSV ----------------

def update_csv(new_data):
    if not new_data:
        print("No successful API responses. CSV unchanged.")
        return

    fresh_df = pd.concat(new_data, ignore_index=True)

    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        try:
            old_df = pd.read_csv(
                DATA_FILE, parse_dates=["date"]
            )
            combined = pd.concat(
                [old_df, fresh_df], ignore_index=True
            )
        except pd.errors.EmptyDataError:
            combined = fresh_df
    else:
        combined = fresh_df

    combined["date"] = pd.to_datetime(combined["date"])

    combined.drop_duplicates(
        subset=["symbol", "date"],
        keep="last",
        inplace=True
    )

    combined.sort_values(
        ["symbol", "date"], inplace=True
    )

    combined.to_csv(DATA_FILE, index=False)

    print("\nTotal unique records:", len(combined))
    print("\nRecords per company:")
    print(combined.groupby("symbol").size())
    print("\nCSV saved to:", DATA_FILE)

    logging.info("CSV updated: %s rows", len(combined))


# ---------------- MAIN PIPELINE ----------------

def main():
    if not API_KEY:
        raise ValueError(
            "API key missing. Add ALPHA_VANTAGE_API_KEY to .env"
        )

    fetched_data = []

    for i, symbol in enumerate(SYMBOLS):
        df = fetch_stock_data(symbol)

        if df is not None:
            fetched_data.append(df)

        # Respect the API's one-request-per-second guidance.
        if i < len(SYMBOLS) - 1:
            time.sleep(1.5)

    update_csv(fetched_data)


if __name__ == "__main__":
    main()
