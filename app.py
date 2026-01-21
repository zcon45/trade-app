import streamlit as st
import os
import pandas as pd
import numpy as np
from polygon import RESTClient
from datetime import datetime

st.set_page_config(
    page_title="Simple Day Trading Helper",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Simple Day Trading Helper")

st.markdown("This tool looks at recent stock prices and suggests possible quick trades. "
            "It uses simple rules and always includes safety stops to limit losses.")

# ────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("Your Choices")
    
    symbol = st.text_input(
        "Which stock or crypto? (e.g. AAPL, TSLA, BTCUSD)",
        value="AAPL"
    )
    
    timeframe_label = st.selectbox(
        "How far apart should the prices be?",
        options=["1 minute", "1 hour", "1 day"],
        index=2  # default to 1 day
    )
    
    # Map user-friendly label to API timespan value
    timeframe_map = {
        "1 minute": "minute",
        "1 hour": "hour",
        "1 day": "day"
    }
    api_timespan = timeframe_map[timeframe_label]
    
    capital = st.number_input(
        "How much money do you have to trade with? ($)",
        value=10000.0,
        step=1000.0,
        min_value=1000.0
    )
    
    risk_percent = st.slider(
        "How much of your money are you willing to risk on ONE trade? (%)",
        min_value=0.5,
        max_value=5.0,
        value=1.0,
        step=0.5,
        help="Example: 1% means if you lose the full amount on this trade, you only lose 1% of your total money."
    ) / 100

# ────────────────────────────────────────────────
# API key
# ────────────────────────────────────────────────
POLYGON_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_KEY:
    st.error("Missing connection key. Add POLYGON_API_KEY in Manage app → Secrets.")
    st.stop()

# ────────────────────────────────────────────────
# Get prices
# ────────────────────────────────────────────────
if st.button("Get Latest Prices"):
    with st.spinner("Downloading prices..."):
        try:
            client = RESTClient(api_key=POLYGON_KEY)
            from_date = (datetime.now() - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")

            aggs = client.get_aggs(
                ticker=symbol,
                multiplier=1,
                timespan=api_timespan,  # Now correct: 'minute', 'hour', 'day'
                from_=from_date,
                to=to_date,
                limit=500
            )

            if not aggs:
                st.warning("No prices found. Try a different stock or switch to '1 day'.")
            else:
                df = pd.DataFrame([{
                    "Date/Time": pd.to_datetime(bar.timestamp, unit="ms"),
                    "Open": bar.open,
                    "High": bar.high,
                    "Low": bar.low,
                    "Close": bar.close,
                    "Volume": bar.volume
                } for bar in aggs]).set_index("Date/Time")

                # Standardize columns to lowercase for calculations
                df.columns = [col.lower() for col in df.columns]

                st.session_state["data"] = df
                st.success(f"Got {len(df)} price updates for {symbol} ({timeframe_label})")
                st.dataframe(df.tail(10).style.format({
                    "open": "${:,.2f}",
                    "high": "${:,.2f}",
                    "low": "${:,.2f}",
                    "close": "${:,.2f}",
                    "volume": "{:,.0f}"
                }))

        except Exception as e:
            st.error(f"Couldn't get prices: {str(e)}")
            st.info("Common fixes: Use '1 day' if markets are closed, check symbol spelling, or verify your API key limits.")

# ────────────────────────────────────────────────
# Price patterns - using lowercase columns
# ────────────────────────────────────────────────
def calculate_price_patterns(df):
    if df is None or df.empty:
        st.warning("No data available to analyze. Click 'Get Latest Prices' first.")
        return None

    df = df.copy()

    df['Short Average Price (20)'] = df['close'].rolling(window=20).mean()
    df['Longer Average Price (50)'] = df['close'].ewm(span=50, adjust=False).mean()

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    df['Overbought/Oversold Score (0-100)'] = 100 - (100 / (1 + rs))

    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['Momentum Line'] = ema12 - ema26
    df['Momentum Signal Line'] = df['Momentum Line'].ewm(span=9, adjust=False).mean()

    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['Typical Daily Price Swing'] = tr.rolling(window=14).mean()

    return df.dropna()

# ────────────────────────────────────────────────
# Find possible trades
# ────────────────────────────────────────────────
def find_possible_trades(df, capital, risk_pct):
    if df is None or df.empty:
        return None, None

    df = calculate_price_patterns(df)
    if df is None or df.empty:
        return None, None

    trades = []
    for i in range(1, len(df)):
        price = df['close'].iloc[i]
        swing = df['Typical Daily Price Swing'].iloc[i]

        # BUY
        if (df['Short Average Price (20)'].iloc[i] > df['Longer Average Price (50)'].iloc[i] and
            df['Short Average Price (20)'].iloc[i-1] <= df['Longer Average Price (50)'].iloc[i-1] and
            df['Overbought/Oversold Score (0-100)'].iloc[i] < 70):

            safety_stop = price - swing * 1.5
            risk_amount = price - safety_stop
            target_price = price + risk_amount * 2
            shares = max(1, int((capital * risk_pct) / risk_amount))

            trades.append({
                "Date/Time": df.index[i],
                "Buy or Sell": "BUY",
                "Entry Price": price,
                "Safety Stop Price": safety_stop,
                "Target Sell Price": target_price,
                "Number of Shares": shares
            })

        # SELL
        elif ((df['Short Average Price (20)'].iloc[i] < df['Longer Average Price (50)'].iloc[i] and
               df['Short Average Price (20)'].iloc[i-1] >= df['Longer Average Price (50)'].iloc[i-1]) or
              df['Overbought/Oversold Score (0-100)'].iloc[i] > 70):

            safety_stop = price + swing * 1.5
            risk_amount = safety_stop - price
            target_price = price - risk_amount * 2
            shares = max(1, int((capital * risk_pct) / risk_amount))

            trades.append({
                "Date/Time": df.index[i],
                "Buy or Sell": "SELL",
                "Entry Price": price,
                "Safety Stop Price": safety_stop,
                "Target Sell Price": target_price,
                "Number of Shares": shares
            })

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    return df, trades_df

# ────────────────────────────────────────────────
# Find trades button
# ────────────────────────────────────────────────
if "data" in st.session_state and st.button("Find Possible Trades"):
    with st.spinner("Looking for good opportunities..."):
        data = st.session_state["data"]
        pattern_df, trades_df = find_possible_trades(data, capital, risk_percent)

        if pattern_df is not None:
            st.subheader("Recent Price Patterns & Strength (Last 10 Prices)")
            st.dataframe(pattern_df.tail(10).style.format({
                "close": "${:,.2f}",
                "Short Average Price (20)": "${:,.2f}",
                "Longer Average Price (50)": "${:,.2f}",
                "Overbought/Oversold Score (0-100)": "{:,.1f}",
                "Momentum Line": "{:,.4f}",
                "Momentum Signal Line": "{:,.4f}",
                "Typical Daily Price Swing": "{:,.2f}"
            }))

        if not trades_df.empty:
            st.subheader("Possible Trades Found")
            st.dataframe(trades_df.style.format({
                "Entry Price": "${:,.2f}",
                "Safety Stop Price": "${:,.2f}",
                "Target Sell Price": "${:,.2f}",
                "Number of Shares": "{:,}"
            }))
            st.info("These are suggestions only. Always double-check and never risk more than you can afford to lose.")
        else:
            st.info("No clear opportunities right now. Try a different stock or timeframe.")

st.markdown("---")
st.caption("This is a learning tool — not financial advice. Test everything in paper trading mode first.")
