import streamlit as st
import yfinance as yf
import pandas as pd
import datetime

# 1. Page Configuration
st.set_page_config(page_title="Nifty 50 Final", layout="wide")
st.title("📈 Nifty 50 Live Dashboard (Fixed)")

# 2. Refresh Button
if st.button("🔄 Refresh Data"):
    st.rerun()

# 3. 100% Working Static List (முழு 50 பங்குகள்)
# இனி இது விக்கிப்பீடியாவை நம்பி இருக்காது. எப்போதும் வேலை செய்யும்.
nifty_50_symbols = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BEL.NS", "BHARTIARTL.NS",
    "BPCL.NS", "BRITANNIA.NS", "CIPLA.NS", "COALINDIA.NS", "DIVISLAB.NS",
    "DRREDDY.NS", "EICHERMOT.NS", "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS",
    "HDFCLIFE.NS", "HEROMOTOCO.NS", "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS",
    "INDIGO.NS", "INDUSINDBK.NS", "INFY.NS", "ITC.NS", "JSWSTEEL.NS",
    "KOTAKBANK.NS", "LT.NS", "LTIM.NS", "M&M.NS", "MARUTI.NS",
    "NESTLEIND.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "RELIANCE.NS",
    "SBILIFE.NS", "SBIN.NS", "SHRIRAMFIN.NS", "SUNPHARMA.NS", "TATACONSUM.NS",
    "TATAMOTORS.NS", "TATASTEEL.NS", "TCS.NS", "TECHM.NS", "TITAN.NS",
    "TRENT.NS", "ULTRACEMCO.NS", "WIPRO.NS"
]

# 4. Data Fetching Function
def get_stock_data(symbols):
    data_list = []
    advances = 0
    declines = 0
    neutral = 0
    
    # Progress Bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_stocks = len(symbols)
    
    for i, symbol in enumerate(symbols):
        # Update Progress
        progress = (i + 1) / total_stocks
        progress_bar.progress(progress)
        status_text.text(f"Scanning: {symbol} ({i+1}/{total_stocks})")
        
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="2d")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                # Previous Close Calculation
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else hist['Open'].iloc[-1]
                
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                if change_pct > 0:
                    status = "🟢 Advance"
                    advances += 1
                elif change_pct < 0:
                    status = "🔴 Decline"
                    declines += 1
                else:
                    status = "⚪ Neutral"
                    neutral += 1
                
                data_list.append({
                    "Stock": symbol.replace(".NS", ""),
                    "Price": round(current_price, 2),
                    "Change %": round(change_pct, 2),
                    "Status": status
                })
        except:
            pass

    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data_list), advances, declines

# Run the function
df, adv, dec = get_stock_data(nifty_50_symbols)

# 5. Metrics Display
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Stocks", len(df))
col1.metric("🟢 Advances", adv)
col1.metric("🔴 Declines", dec)
col4.metric("Market Sentiment", "Bullish 🐂" if adv > dec else "Bearish 🐻")

# 6. Table Display with Colors
def color_surya(val):
    if 'Advance' in val:
        return 'background-color: #ccffcc; color: black; font-weight: bold' # Green
    elif 'Decline' in val:
        return 'background-color: #ffcccc; color: black; font-weight: bold' # Red
    return ''

if not df.empty:
    st.dataframe(df.style.applymap(color_surya, subset=['Status']), use_container_width=True, height=600)
else:
    st.error("Data Load Failed. Please Refresh.")
