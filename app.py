import streamlit as st
import os
import pandas as pd
from polygon import RESTClient
from datetime import datetime

# ────────────────────────────────────────────────
# Force sidebar to be visible on first load
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Trade App – Day Trader Test",
    layout="wide",
    initial_sidebar_state="expanded"   # This should make the sidebar open by default
)

st.title("Day Trading Prototype – Step-by-Step Test")

# ────────────────────────────────────────────────
# Sidebar (should now be visible)
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    symbol = st.text_input("Stock Symbol", value="AAPL")
    timeframe = st.selectbox(
        "Timeframe",
        options=["minute", "hour", "day"],
        index=0
    )
    st.caption("Tip: Use 'day' if minute/hour returns no data (market closed)")

# ────────────────────────────────────────────────
# Main content
# ────────────────────────────────────────────────
st.markdown("### Current setup check")
st.write("• If you see this sidebar on the left → great!")
st.write("• If not → try refreshing or clicking the small > arrow in top-left corner")

# Load Polygon API key from secrets
POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

if not POLYGON_KEY:
    st.error("POLYGON_API_KEY not found in secrets.")
    st.info("Go to Manage app → Secrets and make sure it's spelled exactly POLYGON_API_KEY")
    st.stop()

st.success("API key detected ✓")

# ────────────────────────────────────────────────
# Test button
# ────────────────────────────────────────────────
if st.button("Fetch recent data from Polygon (test connection)"):
    with st.spinner("Fetching data..."):
        try:
            client = RESTClient(api_key=POLYGON_KEY)

            # Try to get the last few bars
            from_date = (datetime.now() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")

            aggs = client.get_aggs(
                ticker=symbol,
                multiplier=1,
                timespan=timeframe,
                from_=from_date,
                to=to_date,
                limit=20   # get up to 20 recent bars
            )

            if not aggs:
                st.warning("No data returned. Try changing timeframe to 'day' or use a different symbol.")
            else:
                df = pd.DataFrame([{
                    "timestamp": pd.to_datetime(bar.timestamp, unit="ms"),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                } for bar in aggs])

                st.success(f"Fetched {len(df)} bars for {symbol} ({timeframe})")
                st.dataframe(
                    df.style.format({
                        "open": "${:,.2f}",
                        "high": "${:,.2f}",
                        "low": "${:,.2f}",
                        "close": "${:,.2f}",
                        "volume": "{:,.0f}"
                    })
                )

        except Exception as e:
            st.error(f"Error during API call: {str(e)}")
            st.info("""
Common causes:
• Invalid or expired Polygon key
• Market closed → try timeframe = 'day'
• Rate limit / free tier restriction
• Wrong symbol spelling
            """)

st.markdown("---")
st.caption("Once this button shows real price data → reply and we'll add indicators + signals next.")
