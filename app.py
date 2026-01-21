import streamlit as st

st.set_page_config(page_title="Trade App – Setup Test", layout="centered")

st.title("Trade App Prototype")

st.markdown("Fresh repo test – if you see this page without errors, deployment works!")

st.header("Basic checks")

st.write("✅ Streamlit is running")
st.write("Current time (server):", st.session_state.get("time", "not set"))

if st.button("Show random data table"):
    import pandas as pd
    import numpy as np
    df = pd.DataFrame(
        np.random.randn(8, 4),
        columns=["Open", "High", "Low", "Close"]
    )
    st.dataframe(df.style.format("{:.2f}"))
    st.success("Pandas + NumPy are installed and working!")

st.markdown("---")
st.caption("Next: Add API keys & trading logic once this deploys cleanly.")
