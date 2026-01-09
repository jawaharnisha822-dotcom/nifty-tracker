import streamlit as st
import yfinance as yf
import pandas as pd
import datetime

# 1. Page Configuration (வெப்சைட் செட்டிங்ஸ்)
st.set_page_config(
    page_title="Nifty 50 Live Dashboard",
    page_icon="📈",
    layout="wide"
)

# தலைப்பு மற்றும் டிசைன்
st.title("🇮🇳 Nifty 50 Market Breadth Tracker")
st.markdown("---")

# 2. ஆட்டோமேட்டிக்காக Nifty 50 லிஸ்ட்டை எடுக்கும் ஃபங்ஷன் (Caching உடன்)
@st.cache_data(ttl=3600)  # 1 மணி நேரத்திற்கு ஒரு முறை மட்டும் லிஸ்ட்டை புதுப்பிக்கும்
def get_nifty50_symbols():
    try:
        url = "https://en.wikipedia.org/wiki/NIFTY_50"
        tables = pd.read_html(url)
        # விக்கிப்பீடியாவில் 'Symbol' அல்லது 'Ticker' உள்ள அட்டவணையை தேடுகிறது
        for table in tables:
            if 'Symbol' in table.columns:
                return [f"{sym}.NS" for sym in table['Symbol'].tolist()]
            elif 'Ticker' in table.columns:
                return [f"{sym}.NS" for sym in table['Ticker'].tolist()]
        
        # எதுவும் சிக்கவில்லை என்றால் பழைய லிஸ்ட் (Backup)
        st.warning("⚠️ Live list fetch failed. Using backup list.")
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]
    except Exception as e:
        st.error(f"Error fetching symbols: {e}")
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

# 3. ஸ்டாக் டேட்டாவை எடுக்கும் ஃபங்ஷன் (Progress Bar உடன்)
def get_stock_data(symbols):
    data_list = []
    advances = 0
    declines = 0
    neutral = 0
    
    # Progress Bar உருவாக்கம்
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_stocks = len(symbols)
    
    for i, symbol in enumerate(symbols):
        # Progress Bar அப்டேட்
        progress = (i + 1) / total_stocks
        progress_bar.progress(progress)
        status_text.text(f"Fetching data for: {symbol} ({i+1}/{total_stocks})")
        
        try:
            stock = yf.Ticker(symbol)
            # கடந்த 2 நாட்களின் டேட்டாவை எடுப்பது (Previous Close கணக்கிட)
            hist = stock.history(period="2d")
            
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                # மார்க்கெட் ஓபன் ஆனால் Live Open Price, இல்லையென்றால் Previous Close
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else hist['Open'].iloc[-1]
                
                change_value = current_price - prev_close
                change_pct = (change_value / prev_close) * 100
                
                # Advance / Decline / Neutral Status
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
                    "Symbol": symbol.replace(".NS", ""),
                    "LTP (₹)": round(current_price, 2),
                    "Change (%)": round(change_pct, 2),
                    "Status": status
                })
        except Exception:
            pass # எரர் வந்தால் அந்த ஸ்டாக்கை மட்டும் விட்டுவிடும்

    # Progress Bar மறைத்தல்
    progress_bar.empty()
    status_text.empty()
    
    return pd.DataFrame(data_list), advances, declines, neutral

# 4. முதன்மை செயல்பாடு (Main Execution)
if st.button("🔄 Refresh Live Data", type="primary"):
    st.rerun()

# டேட்டாவை பெறுதல்
symbols = get_nifty50_symbols()
df, adv, dec, neu = get_stock_data(symbols)

# 5. Dashboard Metrics (மேலே பெரிய எழுத்தில் காட்டுவது)
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Total Stocks", value=len(df))
with col2:
    st.metric(label="🟢 Advances", value=adv)
with col3:
    st.metric(label="🔴 Declines", value=dec)
with col4:
    # A/D Ratio கணக்கீடு
    ratio = round(adv/dec, 2) if dec > 0 else adv
    st.metric(label="A/D Ratio", value=ratio)

# 6. Advanced Table Styling (கலர் மற்றும் டிசைன்)
def style_dataframe(row):
    color = ''
    if 'Advance' in row['Status']:
        color = 'background-color: #d4edda; color: #155724' # Light Green
    elif 'Decline' in row['Status']:
        color = 'background-color: #f8d7da; color: #721c24' # Light Red
    return [color] * len(row)

st.subheader(f"Live Market Data - {datetime.datetime.now().strftime('%H:%M:%S')}")

# டேபிள் காட்டுதல் (Search வசதியுடன்)
if not df.empty:
    # கலரிங் செய்வது
    styled_df = df.style.apply(style_dataframe, axis=1).format({"LTP (₹)": "{:.2f}", "Change (%)": "{:+.2f}"})
    st.dataframe(styled_df, use_container_width=True, height=600)
else:
    st.error("டேட்டா கிடைக்கவில்லை. சிறிது நேரம் கழித்து முயற்சிக்கவும்.")

# Footer
st.markdown("---")
st.caption("Developed with ❤️ using Python & Streamlit")
