import streamlit as st
import os
import pandas as pd
import numpy as np
from polygon import RESTClient
from datetime import datetime

st.set_page_config(
    page_title="Trade App – Day Trader Prototype",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Day Trading Prototype – Indicators & Signals")

# ────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    symbol = st.text_input("Stock Symbol", value="AAPL")
    timeframe = st.selectbox("Timeframe", ["minute", "hour", "day"], index=2)  # default to day
    capital = st.number_input("Account Capital ($)", value=10000.0, step=1000.0)
    risk_percent = st.slider("Risk per Trade (%)", 0.5, 5.0, 1.0) / 100

# ────────────────────────────────────────────────
# Load API key
# ────────────────────────────────────────────────
POLYGON_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_KEY:
    st.error("POLYGON_API_KEY not found in secrets.")
    st.stop()

st.success("API key loaded ✓")

# ────────────────────────────────────────────────
# Fetch Data Button
# ────────────────────────────────────────────────
if st.button("Fetch Recent Data from Massive/Polygon"):
    with st.spinner("Fetching..."):
        try:
            client = RESTClient(api_key=POLYGON_KEY)
            from_date = (datetime.now() - pd.Timedelta(days=60)).strftime("%Y-%m-%d")  # more history for indicators
            to_date = datetime.now().strftime("%Y-%m-%d")

            aggs = client.get_aggs(
                ticker=symbol,
                multiplier=1,
                timespan=timeframe,
                from_=from_date,
                to=to_date,
                limit=500  # enough for indicators
            )

            if not aggs:
                st.warning("No data returned. Try 'day' timeframe or different symbol.")
            else:
                df = pd.DataFrame([{
                    "timestamp": pd.to_datetime(bar.timestamp, unit="ms"),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                } for bar in aggs]).set_index("timestamp")

                st.session_state["data"] = df  # store for later use
                st.success(f"Fetched {len(df)} bars for {symbol} ({timeframe})")
                st.dataframe(df.tail(10).style.format({
                    "open": "${:,.2f}", "high": "${:,.2f}", "low": "${:,.2f}", "close": "${:,.2f}",
                    "volume": "{:,.0f}"
                }))

        except Exception as e:
            st.error(f"Fetch error: {str(e)}")

# ────────────────────────────────────────────────
# Calculate Indicators (manual, no extra deps)
# ────────────────────────────────────────────────
def calculate_indicators(df):
    if df is None or df.empty:
        return None

    df = df.copy()

    # SMA 20
    df['sma_20'] = df['close'].rolling(window=20).mean()

    # EMA 50
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

    # RSI 14
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # MACD (12,26,9)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # ATR 14
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(window=14).mean()

    return df.dropna()

# ────────────────────────────────────────────────
# Generate Signals with Risk Management
# ────────────────────────────────────────────────
def generate_signals(df, capital, risk_pct):
    if df is None or df.empty:
        return None, None

    df = calculate_indicators(df)
    if df is None or df.empty:
        return None, None

    signals = []
    for i in range(1, len(df)):
        price = df['close'].iloc[i]
        atr = df['atr_14'].iloc[i]

        # Buy: SMA20 crosses above EMA50, RSI < 70
        if (df['sma_20'].iloc[i] > df['ema_50'].iloc[i] and
            df['sma_20'].iloc[i-1] <= df['ema_50'].iloc[i-1] and
            df['rsi_14'].iloc[i] < 70):

            stop_loss = price - atr * 1.5
            risk_dist = price - stop_loss
            take_profit = price + risk_dist * 2.0  # 2:1 reward:risk

            qty = max(1, int((capital * risk_pct) / risk_dist))

            signals.append({
                "timestamp": df.index[i],
                "action": "BUY",
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "quantity": qty
            })

        # Sell: SMA20 crosses below EMA50 or RSI > 70
        elif ((df['sma_20'].iloc[i] < df['ema_50'].iloc[i] and
               df['sma_20'].iloc[i-1] >= df['ema_50'].iloc[i-1]) or
              df['rsi_14'].iloc[i] > 70):

            stop_loss = price + atr * 1.5
            risk_dist = stop_loss - price
            take_profit = price - risk_dist * 2.0

            qty = max(1, int((capital * risk_pct) / risk_dist))

            signals.append({
                "timestamp": df.index[i],
                "action": "SELL",
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "quantity": qty
            })

    signals_df = pd.DataFrame(signals) if signals else pd.DataFrame()
    return df, signals_df

# ────────────────────────────────────────────────
# Run Scan Button
# ────────────────────────────────────────────────
if "data" in st.session_state and st.button("Run Scan & Generate Signals"):
    with st.spinner("Analyzing..."):
        data = st.session_state["data"]
        ind_df, sig_df = generate_signals(data, capital, risk_percent)

        if ind_df is not None:
            st.subheader("Indicators (Last 10 Rows)")
            st.dataframe(ind_df.tail(10).style.format({
                "close": "${:,.2f}", "sma_20": "${:,.2f}", "ema_50": "${:,.2f}",
                "rsi_14": "{:,.2f}", "macd": "{:,.4f}", "macd_signal": "{:,.4f}",
                "atr_14": "{:,.2f}"
            }))

        if not sig_df.empty:
            st.subheader("Generated Signals")
            st.dataframe(sig_df.style.format({
                "price": "${:,.2f}", "stop_loss": "${:,.2f}", "take_profit": "${:,.2f}",
                "quantity": "{:,}"
            }))
        else:
            st.info("No clear signals generated with current data/strategy.")

st.markdown("---")
st.caption("Next up (after you test this): Alpaca trading execution + portfolio monitor")
