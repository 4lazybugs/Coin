import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

DB_PATH = "bitcoin_trades.db"

def load_trades(db_path=DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path, check_same_thread=False) as conn:
        df = pd.read_sql_query("SELECT * FROM trades", conn)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.sort_values("timestamp")

def line(df: pd.DataFrame, x: str, y: str, title: str):
    st.plotly_chart(px.line(df, x=x, y=y, title=title), use_container_width=True)

def main():
    st.title("Bitcoin Trades Viewer")

    df = load_trades()

    coins = sorted(df["coin_name"].dropna().unique())
    selected = st.sidebar.multiselect("coin_name", coins, default=coins)

    df = df[df["coin_name"].isin(selected)]

    st.header("Overview")
    st.write(f"Total trades: {len(df)}")
    st.write(f"First trade: {df['timestamp'].min()}")
    st.write(f"Last trade: {df['timestamp'].max()}")

    eq_first = df["equity_now"].iloc[0]
    eq_last = df["equity_now"].iloc[-1]
    st.metric("Equity change (last - first)", f"{(eq_last - eq_first):,.0f} KRW")

    st.header("Trade History")
    st.dataframe(df)

    st.header("Trade Decision Distribution")
    counts = df["decision"].value_counts()
    st.plotly_chart(px.pie(values=counts.values, names=counts.index, title="Trade Decisions"),
                    use_container_width=True)

    st.header("Per-Coin Charts")
    for coin in selected:
        d = df[df["coin_name"] == coin]
        st.subheader(coin)

        c1, c2 = st.columns(2)
        with c1:
            line(d, "timestamp", "asset_balance", "Asset Balance")
        with c2:
            line(d, "timestamp", "asset_krw_price", "Asset Price (KRW)")

        c3, c4 = st.columns(2)
        with c3:
            line(d, "timestamp", "krw_balance", "KRW Balance")
        with c4:
            line(d, "timestamp", "equity_now", "Equity Now (KRW)")

if __name__ == "__main__":
    main()
    # 실행: streamlit run streamlit_app.py