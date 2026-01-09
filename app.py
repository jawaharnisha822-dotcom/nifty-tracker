# --- ஆட்டோமேட்டிக் Nifty 50 லிஸ்ட் எடுக்கும் வசதி ---
@st.cache_data
def get_nifty50_list():
    try:
        # Wikipedia-வில் இருந்து லேட்டஸ்ட் லிஸ்ட்டை எடுக்கும்
        url = "https://en.wikipedia.org/wiki/NIFTY_50"
        tables = pd.read_html(url)
        
        # 'Symbol' அல்லது 'Ticker' உள்ள அட்டவணையை தேடுகிறது
        for table in tables:
            if 'Symbol' in table.columns:
                nifty_df = table
                break
        
        # .NS சேர்த்து லிஸ்டாக மாற்றுகிறது (Yahoo Finance-க்கு ஏற்றபடி)
        symbols = [f"{sym}.NS" for sym in nifty_df['Symbol'].tolist()]
        return symbols
    except Exception as e:
        st.error("ஆட்டோமேட்டிக் லிஸ்ட் எடுப்பதில் சிக்கல். பழைய லிஸ்ட்டை பயன்படுத்துகிறது.")
        # அவசரத்திற்கு ஒரு பேக்-அப் லிஸ்ட் (Backup)
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

# பழைய கையால் டைப் செய்த லிஸ்ட்டுக்கு பதில் இதை அழைக்கிறோம்
nifty_50_symbols = get_nifty50_list()
# -----------------------------------------------------
