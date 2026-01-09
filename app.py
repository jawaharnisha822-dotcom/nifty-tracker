import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Nifty 50 Tracker", layout="wide")
st.title("📈 Nifty 50 Advance/Decline Live Tracker")

# Refresh Button
if st.button('🔄 Refresh Data'):
    st.rerun()

# Nifty 50 Symbols (மாதிரிக்கு 10 கொடுக்கிறேன், நீங்கள் 50-யும் சேர்த்துக்கொள்ளலாம்)
nifty_50_symbols = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS",
    "TATAMOTORS.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS"
]

def get_stock_data():
    data_list = []
    advances = 0
    declines = 0
    st.write("Fetching live data from Yahoo Finance...")
    
    for symbol in nifty_50_symbols:
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                open_price = hist['Open'].iloc[-1]
                change = ((current_price - open_price) / open_price) * 100
                
                status = "Neutral"
                if change > 0:
                    status = "Advance 🟢"
                    advances += 1
                elif change < 0:
                    status = "Decline 🔴"
                    declines += 1
                
                data_list.append({
                    "Symbol": symbol.replace(".NS", ""),
                    "Price": round(current_price, 2),
                    "Change %": round(change, 2),
                    "Status": status
                })
        except:
            pass
            
    return pd.DataFrame(data_list), advances, declines

df, adv, dec = get_stock_data()

# Metrics
col1, col2, col3 = st.columns(3)
col1.metric("Total Stocks", len(df))
col1.metric("🟢 Advances", adv)
col1.metric("🔴 Declines", dec)

# Styling
def color_status(val):
    if 'Advance' in val: return 'color: green; font-weight: bold;'
    if 'Decline' in val: return 'color: red; font-weight: bold;'
    return ''

st.subheader("Stock List")
if not df.empty:
    st.dataframe(df.style.applymap(color_status, subset=['Status']), use_container_width=True)
else:
    st.error("Data fetch failed. Try clicking Refresh again.")
