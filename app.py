import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. Google Sheets 連線設定 (使用 gspread)
# ==========================================
# 加入快取裝飾器，避免每次操作都重新連線
@st.cache_resource
def get_google_sheet_data():
    # 定義授權範圍
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # --- 智慧偵測 Secrets 格式 ---
    # 情況 A: 使用標準 [connections.gsheets] 格式
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        s_info = st.secrets["connections"]["gsheets"]
    # 情況 B: 直接貼上 JSON 內容在根目錄
    elif "type" in st.secrets and "project_id" in st.secrets:
        s_info = st.secrets
    else:
        st.error("❌ 找不到 Google 憑證資料！請檢查 Secrets 設定是否包含 [connections.gsheets] 區塊。")
        st.stop()
    
    # 建立憑證物件
    creds = Credentials.from_service_account_info(
        {
            "type": s_info["type"],
            "project_id": s_info["project_id"],
            "private_key_id": s_info["private_key_id"],
            "private_key": s_info["private_key"],
            "client_email": s_info["client_email"],
            "client_id": s_info["client_id"],
            "auth_uri": s_info["auth_uri"],
            "token_uri": s_info["token_uri"],
            "auth_provider_x509_cert_url": s_info["auth_provider_x509_cert_url"],
            "client_x509_cert_url": s_info["client_x509_cert_url"]
        },
        scopes=scopes
    )
    
    # 連線
    client = gspread.authorize(creds)
    
    # 開啟試算表 (透過網址)
    # 嘗試從 Secrets 讀取網址，如果沒有則使用預設提示
    sheet_url = s_info.get("spreadsheet")
    if not sheet_url:
        st.error("❌ Secrets 中缺少 'spreadsheet' 網址設定。請在 Secrets 中加入 spreadsheet = '...您的網址...'")
        st.stop()
        
    sheet = client.open_by_url(sheet_url).sheet1
    return sheet

# ==========================================
# 2. 菜單資料庫
# ==========================================
ALL_MENUS = {
    "可不可熟成紅茶": {
        "熟成紅茶": 30, "鴉片紅茶": 30, "太妃紅茶": 35,
        "熟成冷露": 30, "白玉歐蕾": 50, "春梅冰茶": 45
    },
    "50嵐": {
        "四季春青茶": 30, "黃金烏龍": 30, "珍珠奶茶": 50,
        "波霸奶茶": 50, "紅茶拿鐵": 55, "8冰綠": 50
    },
    "迷客夏": {
        "大正紅茶拿鐵": 60, "伯爵紅茶拿鐵": 60, "珍珠紅茶拿鐵": 65,
        "柳丁綠茶": 60, "芋頭鮮奶": 65
    }
}
SUGAR_OPTS = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "一分糖", "無糖"]
ICE_OPTS = ["正常冰", "少冰", "微冰", "去冰", "常溫", "熱"]

# ==========================================
# 3. 網頁介面
# ==========================================
st.title("🥤 辦公室飲料點餐系統")

st.sidebar.header("設定")
selected_store = st.sidebar.selectbox("今天喝哪一家？", list(ALL_MENUS.keys()))
current_menu = ALL_MENUS[selected_store]
st.subheader(f"目前店家：{selected_store}")

with st.form("order_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("你的名字 (必填)")
    with col2:
        drink = st.selectbox("飲料品項", list(current_menu.keys()))
    col3, col4 = st.columns(2)
    with col3:
        sugar = st.selectbox("甜度", SUGAR_OPTS)
    with col4:
        ice = st.selectbox("冰塊", ICE_OPTS)
    note = st.text_input("備註")
    
    submitted = st.form_submit_button("送出訂單")

# ==========================================
# 4. 邏輯處理
# ==========================================
if submitted:
    if not name:
        st.error("❌ 請記得輸入名字！")
    else:
        try:
            # 準備資料
            price = current_menu[drink]
            order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row_data = [order_time, selected_store, name, drink, price, sugar, ice, note]

            # 連線並寫入 (使用 gspread 直接 append_row，速度更快更穩)
            sheet = get_google_sheet_data()
            sheet.append_row(row_data)
            
            st.success(f"✅ {name} 點餐成功！")
            st.balloons()
            
        except Exception as e:
            st.error(f"⚠️ 寫入失敗：{e}")

# ==========================================
# 5. 顯示目前清單
# ==========================================
st.divider()
st.write("📊 **目前訂單列表：**")
try:
    sheet = get_google_sheet_data()
    # 讀取所有紀錄並轉成 DataFrame 顯示
    data = sheet.get_all_records()
    if data:
        st.dataframe(pd.DataFrame(data))
    else:
        st.info("目前沒有資料")
except Exception as e:
    st.info("尚無訂單或連線設定中...")
