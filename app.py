import os

# --- Auto-Generate Streamlit Light Theme Config ---
os.makedirs(".streamlit", exist_ok=True)
config_toml_path = os.path.join(".streamlit", "config.toml")
with open(config_toml_path, "w", encoding="utf-8") as f:
    f.write('''[theme]
base="light"
primaryColor="#CC0000"
backgroundColor="#FFFFFF"
secondaryBackgroundColor="#F8F9FA"
textColor="#111111"
''')

import streamlit as st
import sqlite3
import pandas as pd
from PIL import Image
import google.generativeai as genai
import json
import io
import zipfile
from datetime import datetime
import difflib

# --- Gemini API Key Configuration ---
GEMINI_API_KEY = "AQ.Ab8RN6L2IcRS1tYxqyHQ_4bEwUPU-DiCJZbCSDeqdkbRsAGlIQ" 
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- Auto-Discovery AI Agent ---
def analyze_bill_image(image):
    prompt = """
    Analyze this handwritten receipt/summary bill image. The text might be in Bengali or English. Extract:
    1. Date (DD/MM/YYYY)
    2. Items list (comma separated)
    3. Total Bill Amount
    
    Return ONLY valid JSON format exactly like this:
    {"date": "DD/MM/YYYY", "items": "item1, item2", "total_amount": 0.0}
    """
    
    models_to_try = ['gemini-3.8-flash', 'models/gemini-3.8-flash']
    last_error = None
    
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash_models = [m for m in available_models if 'flash' in m.lower()]
        if flash_models:
            models_to_try = flash_models + models_to_try
    except Exception:
        pass

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([prompt, image])
            
            clean_text = response.text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
                
            return json.loads(clean_text.strip())
        except Exception as e:
            last_error = e
            continue
            
    raise Exception(f"Google AI Error: {last_error}")

# --- Smart Search Function (Fuzzy Matching) ---
def is_fuzzy_match(query, text, threshold=0.50):
    query = str(query).lower()
    text = str(text).lower()
    if query in text:
        return True
    
    words = text.split()
    for word in words:
        if difflib.SequenceMatcher(None, query, word).ratio() >= threshold:
            return True
    return False

# --- Zip Creator for Single Voucher (Main + Supporting) ---
def create_single_voucher_zip(main_path, supp_paths_str, v_date):
    zip_buffer = io.BytesIO()
    has_file = False
    safe_date = str(v_date).replace('/', '-').replace('\\', '-')
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        if main_path and os.path.exists(main_path):
            ext = os.path.splitext(main_path)[1] or ".jpg"
            zip_file.write(main_path, arcname=f"Main_Bill_{safe_date}{ext}")
            has_file = True
        
        if supp_paths_str and pd.notna(supp_paths_str) and str(supp_paths_str).strip() != "":
            s_paths = str(supp_paths_str).split(",")
            for idx, sp in enumerate(s_paths):
                sp = sp.strip()
                if os.path.exists(sp):
                    ext = os.path.splitext(sp)[1] or ".jpg"
                    zip_file.write(sp, arcname=f"Supporting_Bill_{idx+1}_{safe_date}{ext}")
                    has_file = True
                    
    zip_buffer.seek(0)
    return zip_buffer if has_file else None

# --- Zip Creator for Date Range / Bulk Export ---
def create_bulk_date_range_zip(df_subset):
    zip_buffer = io.BytesIO()
    has_file = False
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for idx, row in df_subset.iterrows():
            v_id = row['id']
            v_date = str(row['তারিখ']).replace('/', '-').replace('\\', '-')
            m_path = row['image_path']
            s_paths_str = row['supporting_images']
            
            folder_prefix = f"Voucher_{v_date}_Ref{v_id}/"
            
            if m_path and os.path.exists(m_path):
                ext = os.path.splitext(m_path)[1] or ".jpg"
                zip_file.write(m_path, arcname=f"{folder_prefix}Main_Bill{ext}")
                has_file = True
                
            if s_paths_str and pd.notna(s_paths_str) and str(s_paths_str).strip() != "":
                s_paths = str(s_paths_str).split(",")
                for s_idx, sp in enumerate(s_paths):
                    sp = sp.strip()
                    if os.path.exists(sp):
                        ext = os.path.splitext(sp)[1] or ".jpg"
                        zip_file.write(sp, arcname=f"{folder_prefix}Supporting_{s_idx+1}{ext}")
                        has_file = True

    zip_buffer.seek(0)
    return zip_buffer if has_file else None

# --- Database Setup ---
conn = sqlite3.connect('it_purchases.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        vendor TEXT,
        items TEXT,
        requisition_amount REAL,
        bill_amount REAL,
        refund_amount REAL,
        image_path TEXT,
        entry_time TEXT
    )
''')
try:
    c.execute("ALTER TABLE purchases ADD COLUMN supporting_images TEXT")
except sqlite3.OperationalError:
    pass
conn.commit()

# --- Page Config ---
st.set_page_config(page_title="All Purchase By Rianul Karim Roudro", layout="wide")

# --- CSS Variables & Text Visibility Fix ---
st.markdown("""
    <style>
    /* Force Light Mode Color Palette at Root Level */
    :root, [data-testid="stAppViewContainer"], .stApp {
        --text-color: #111111 !important;
        --background-color: #FFFFFF !important;
        --secondary-background-color: #F8F9FA !important;
        background-color: #FFFFFF !important;
    }
    
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 1250px !important;
    }
    
    /* Global Text Colors */
    h1, h2, h3, h4, h5, h6, p, span, label, div, small, td, th { 
        color: #111111 !important; 
    }
    
    /* Header Container */
    .header-container { 
        background-color: #FFFFFF; 
        padding: 20px 25px; 
        border-top: 5px solid #CC0000;
        border-bottom: 1px solid #EAEAEA;
        text-align: left; 
        margin-bottom: 20px; 
        box-shadow: 0px 3px 10px rgba(0,0,0,0.02); 
        border-radius: 0px 0px 8px 8px;
    }
    .header-title { font-size: 28px; font-weight: 900; margin: 0; color: #111111 !important; letter-spacing: 0.5px; text-transform: uppercase; }
    .header-subtitle { color: #666666 !important; margin-top: 4px; font-size: 15px; font-weight: 500;}
    
    /* File Uploader Light Styling */
    div[data-testid="stFileUploader"] section {
        background-color: #FFFFFF !important;
        border: 2px dashed #D0D0D0 !important;
        border-radius: 8px !important;
        padding: 12px !important;
    }
    
    div[data-testid="stFileUploadDropzone"] button {
        background-color: #F1F3F5 !important;
        color: #111111 !important;
        border: 1px solid #CCCCCC !important;
        border-radius: 6px !important;
        padding: 6px 16px !important;
        font-weight: bold !important;
    }
    
    /* Dataframe Container Border & Background */
    div[data-testid="stDataFrame"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E0E0E0 !important;
        border-radius: 8px !important;
    }
    
    /* Selectbox & Input Box Colors */
    div[data-baseweb="select"],
    div[data-baseweb="select"] *,
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] *,
    ul[role="listbox"],
    li[role="option"] {
        background-color: #FFFFFF !important;
        color: #111111 !important;
    }
    
    li[role="option"]:hover {
        background-color: #FFF5F5 !important;
        color: #CC0000 !important;
    }

    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stTextArea>div>textarea { 
        border-radius: 6px !important; 
        border: 1px solid #D0D0D0 !important; 
        background-color: #FFFFFF !important;
        color: #111111 !important;
    }

    /* Action Buttons */
    .stButton>button { 
        background-color: #CC0000 !important; 
        color: #FFFFFF !important; 
        font-weight: bold !important; 
        border-radius: 6px !important; 
        border: none !important; 
        padding: 10px 20px !important; 
        transition: 0.3s; 
    }
    .stButton>button:hover { 
        background-color: #A30000 !important; 
        color: #FFFFFF !important; 
        box-shadow: 0px 4px 12px rgba(204,0,0,0.25) !important;
    }
    
    .stDownloadButton>button { 
        background-color: #0D6EFD !important; 
        color: #FFFFFF !important; 
        font-weight: bold !important; 
        border-radius: 6px !important; 
        border: none !important; 
        padding: 10px 20px !important; 
        transition: 0.3s;
        width: 100% !important;
    }
    .stDownloadButton>button:hover { 
        background-color: #0B5ED7 !important; 
        color: #FFFFFF !important;
        box-shadow: 0px 4px 12px rgba(13,110,253,0.25) !important;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] { gap: 15px; }
    .stTabs [data-baseweb="tab"] { height: 45px; white-space: pre-wrap; background-color: transparent !important; border-radius: 4px 4px 0 0; color: #444444 !important; font-weight: bold; font-size: 16px;}
    .stTabs [aria-selected="true"] { color: #CC0000 !important; border-bottom: 3px solid #CC0000 !important; }
    </style>
""", unsafe_allow_html=True)

# --- Header Section ---
st.markdown("""
    <div class="header-container">
        <div class="header-title">ABDULLAH POULTRY FEED MILL</div>
        <div class="header-subtitle">All Purchase By Rianul Karim Roudro</div>
    </div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📝 New Bill Entry", "🔍 Smart Search & Dashboard"])

# --- TAB 1: UPLOAD (Main + Supporting) ---
with tab1:
    c_req, c_ref = st.columns(2)
    with c_req:
        req_amount = st.number_input("💵 কত টাকা তুলেছিলেন? (Requisition)", min_value=0.0, value=0.0, step=50.0)
    with c_ref:
        refund_amount = st.number_input("↩️ কত টাকা ফেরত দিলেন? (Refund)", min_value=0.0, value=0.0, step=10.0)
        
    st.write("---")
    col_upload1, col_upload2 = st.columns(2)
    
    with col_upload1:
        st.info("📄 **মূল সামারি বিল:** যেটি AI রিড করবে।")
        main_file = st.file_uploader("মূল বিল আপলোড করুন", type=['jpg', 'jpeg', 'png'])
        
    with col_upload2:
        st.info("📎 **সাপোর্টিং বিলসমূহ:** প্রমাণ হিসেবে যুক্ত থাকবে।")
        supp_files = st.file_uploader("অন্যান্য বিল আপলোড করুন (একাধিক)", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
    
    if main_file:
        main_image = Image.open(main_file)
        st.image(main_image, caption="মূল সামারি বিল", width=300)
        
        if st.button("🤖 AI দিয়ে তথ্য বের করুন"):
            with st.spinner("AI হাতের লেখা স্ক্যান করছে..."):
                try:
                    result = analyze_bill_image(main_image)
                    st.success("✅ AI সফলভাবে ডেটা বের করেছে!")
                    st.session_state['ai_result'] = result
                except Exception as e:
                    st.error(f"AI ডেটা প্রসেস করতে পারেনি। Error: {e}")

        # Review & Save Form
        if 'ai_result' in st.session_state:
            result = st.session_state['ai_result']
            with st.form("save_form"):
                st.write("### 🔍 তথ্যগুলো পরীক্ষা করে সেভ করুন:")
                
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    b_date = st.text_input("তারিখ (DD/MM/YYYY)", value=result.get("date", ""))
                with col_f2:
                    b_amount = st.number_input("মোট বিলের পরিমাণ", value=float(result.get("total_amount", 0.0)))
                    st.caption(f"💡 আনুমানিক ফেরত দেয়ার কথা: {req_amount - b_amount if req_amount > 0 else refund_amount} BDT")
                
                b_items = st.text_area("আইটেম তালিকা", value=result.get("items", ""))
                
                if st.form_submit_button("💾 Save All to Database"):
                    timestamp = datetime.now().strftime('%H%M%S')
                    safe_date = b_date.replace("/", "-").replace("\\", "-").strip()
                    if not safe_date: safe_date = "Unknown_Date"
                    date_folder_path = os.path.join("bills_images", safe_date)
                    os.makedirs(date_folder_path, exist_ok=True)
                    
                    main_img_path = os.path.join(date_folder_path, f"main_{timestamp}.jpg")
                    main_image.save(main_img_path)
                    
                    supp_paths = []
                    if supp_files:
                        for idx, s_file in enumerate(supp_files):
                            s_img = Image.open(s_file)
                            s_path = os.path.join(date_folder_path, f"supp_{timestamp}_{idx}.jpg")
                            s_img.save(s_path)
                            supp_paths.append(s_path)
                    
                    supp_paths_str = ",".join(supp_paths)
                    
                    c.execute('''INSERT INTO purchases 
                               (date, vendor, items, requisition_amount, bill_amount, refund_amount, image_path, supporting_images, entry_time) 
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                              (b_date, "", b_items, req_amount, b_amount, refund_amount, main_img_path, supp_paths_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    
                    del st.session_state['ai_result']
                    st.balloons()
                    st.success(f"🎉 ডেটা সেভ হয়েছে! ছবিগুলো 'bills_images/{safe_date}' ফোল্ডারে সংরক্ষিত হয়েছে।")

# --- TAB 2: SMART SEARCH & DASHBOARD ---
with tab2:
    query = """
    SELECT id, date AS 'তারিখ', items AS 'পণ্যসমূহ', 
           requisition_amount AS 'উত্তোলিত টাকা', bill_amount AS 'মোট বিল', 
           refund_amount AS 'ফেরত টাকা', entry_time AS 'এন্ট্রি টাইম', image_path, supporting_images
    FROM purchases ORDER BY id DESC
    """
    df = pd.read_sql_query(query, conn)
    
    if not df.empty:
        # --- Top Filter & Search Bar ---
        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            search_term = st.text_input("🔎 তারিখ বা পণ্যের নাম লিখে সার্চ করুন (Live Auto-Search):", placeholder="উদা: 11/10/2026, গুরু মাংস, রাউটার...")
        with col_s2:
            unique_dates = ["সব তারিখ (All Dates)"] + sorted(list(df['তারিখ'].unique()), reverse=True)
            selected_date_filter = st.selectbox("📅 নির্দিষ্ট তারিখের ফিল্টার:", unique_dates)

        # Filter Logic
        filtered_df = df.copy()
        if selected_date_filter != "সব তারিখ (All Dates)":
            filtered_df = filtered_df[filtered_df['তারিখ'] == selected_date_filter]
        if search_term:
            filtered_df = filtered_df[filtered_df.apply(lambda row: is_fuzzy_match(search_term, f"{row['তারিখ']} {row['পণ্যসমূহ']}"), axis=1)]
        
        display_df = filtered_df.drop(columns=['image_path', 'supporting_images'])
        st.dataframe(display_df, use_container_width=True, height=220)
        
        # --- Middle Section: Date-Range Bulk Export ---
        st.markdown("<h4 style='margin-top:15px; color:#111;'>📦 তারিখ অনুযায়ী একসাথে একাধিক ভাউচার ডাউনলোড (Range Export)</h4>", unsafe_allow_html=True)
        col_r1, col_r2, col_r3 = st.columns([1.5, 1.5, 1.5])
        with col_r1:
            all_dates_list = sorted(list(df['তারিখ'].unique()))
            from_date = st.selectbox("শুরু তারিখ (From Date):", all_dates_list, index=0, key="range_from")
        with col_r2:
            to_date = st.selectbox("শেষ তারিখ (To Date):", all_dates_list, index=len(all_dates_list)-1, key="range_to")
        with col_r3:
            st.write("&nbsp;")
            st.write("&nbsp;")
            range_filtered = df[(df['তারিখ'] >= from_date) & (df['তারিখ'] <= to_date)]
            bulk_zip = create_bulk_date_range_zip(range_filtered)
            if bulk_zip:
                st.download_button(
                    label=f"📥 Download ({from_date} to {to_date})",
                    data=bulk_zip,
                    file_name=f"Vouchers_{from_date}_to_{to_date}.zip",
                    mime="application/zip",
                    key="bulk_download_btn"
                )
            else:
                st.button("📥 Download", disabled=True)

        st.markdown("<hr style='margin:15px 0; border:1px solid #EAEAEA;'>", unsafe_allow_html=True)
        st.markdown("### 📷 তারিখ ও পণ্য অনুযায়ী ভাউচার দেখুন ও ম্যানেজ করুন")
        
        # --- Voucher Viewer by Date + Item Preview ---
        voucher_options = {}
        for idx, row in filtered_df.iterrows():
            label_text = f"📅 {row['তারিখ']} | {str(row['পণ্যসমূহ'])[:40]}... (মোট: ৳{row['মোট বিল']})"
            voucher_options[label_text] = row
            
        if voucher_options:
            col_sel, col_down, col_del = st.columns([2.5, 1.2, 1.2])
            
            with col_sel:
                selected_label = st.selectbox("ভাউচার নির্বাচন করুন (Select Voucher):", list(voucher_options.keys()))
                selected_row = voucher_options[selected_label]
            
            selected_id = selected_row['id']
            m_path = selected_row['image_path']
            s_paths_str = selected_row['supporting_images']
            v_date = selected_row['তারিখ']
            
            # Single Voucher ZIP Download
            with col_down:
                st.write("&nbsp;")
                st.write("&nbsp;")
                zip_file_data = create_single_voucher_zip(m_path, s_paths_str, v_date)
                if zip_file_data:
                    st.download_button(
                        label="📥 Download",
                        data=zip_file_data,
                        file_name=f"Voucher_{str(v_date).replace('/','-')}.zip",
                        mime="application/zip",
                        key=f"download_zip_{selected_id}"
                    )
                else:
                    st.button("📥 Download", disabled=True, key=f"dis_dl_{selected_id}")

            # Delete Button
            with col_del:
                st.write("&nbsp;")
                st.write("&nbsp;")
                if st.button("🗑️ Delete", key="delete_record"):
                    if os.path.exists(m_path):
                        try: os.remove(m_path)
                        except: pass
                    if pd.notna(s_paths_str) and s_paths_str.strip() != "":
                        for sp in s_paths_str.split(","):
                            if os.path.exists(sp):
                                try: os.remove(sp)
                                except: pass
                    
                    c.execute("DELETE FROM purchases WHERE id = ?", (selected_id,))
                    conn.commit()
                    st.success(f"ভাউচারটি সফলভাবে মুছে ফেলা হয়েছে!")
                    st.rerun()
            
            # Images Display
            col_img1, col_img2 = st.columns([1, 2])
            with col_img1:
                if os.path.exists(m_path):
                    st.image(m_path, caption=f"📄 মূল সামারি বিল ({v_date})", width=380)
                else:
                    st.warning("মূল ছবিটি পিসিতে খুঁজে পাওয়া যায়নি।")
                    
            with col_img2:
                if pd.notna(s_paths_str) and s_paths_str.strip() != "":
                    st.write("#### 📎 সাপোর্টিং বিলসমূহ:")
                    s_paths = s_paths_str.split(",")
                    cols = st.columns(3)
                    col_idx = 0
                    for sp in s_paths:
                        if os.path.exists(sp):
                            cols[col_idx % 3].image(sp, caption="Supporting Bill", use_container_width=True)
                            col_idx += 1
        else:
            st.info("আপনার সার্চ অনুযায়ী কোনো রেকর্ড পাওয়া যায়নি।")
    else:
        st.info("কোনো ডেটা পাওয়া যায়নি। 'New Bill Entry' থেকে ডেটা যোগ করুন।")