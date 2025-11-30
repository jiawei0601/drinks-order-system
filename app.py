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
    
    try:
        # --- 1. 取得 Secrets 資料 ---
        # 優先檢查標準位置 [connections.gsheets]
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            s_info = st.secrets["connections"]["gsheets"]
        # 次要檢查根目錄 (直接貼 JSON)
        elif "type" in st.secrets and "project_id" in st.secrets:
            s_info = st.secrets
        else:
            raise ValueError("找不到憑證！請確認 Secrets 設定中包含 [connections.gsheets] 區塊。")

        # --- 2. 處理 Private Key 格式問題 (關鍵) ---
        # 這是最容易出錯的地方：Streamlit Secrets 有時會把 \n 讀成字串，導致憑證無效
        # 我們強制把它轉回正確的換行符號
        private_key = s_info["private_key"]
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

        # --- 3. 建立憑證物件 ---
        # 使用 .get() 提供預設值，避免漏貼一些固定網址導致報錯
        creds_dict = {
            "type": s_info["type"],
            "project_id": s_info["project_id"],
            "private_key_id": s_info["private_key_id"],
            "private_key": private_key,  # 使用修正後的 Key
            "client_email": s_info["client_email"],
            "client_id": s_info["client_id"],
            "auth_uri": s_info.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": s_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": s_info.get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"),
            "client_x509_cert_url": s_info["client_x509_cert_url"]
        }
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        
        # --- 4. 連線 ---
        client = gspread.authorize(creds)
        return client, s_info

    except KeyError as e:
        st.error(f"❌ Secrets 設定缺少必要欄位：{e}")
        st.stop()
    except Exception as e:
        st.error(f"❌ Google 連線發生錯誤：{e}")
        st.stop()

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

# 嘗試連線取得機器人資訊 (為了顯示 Email 給使用者看)
try:
    client, s_info = get_google_sheet_data()
    bot_email = s_info['client_email']
    # 在側邊欄顯示機器人資訊，方便除錯
    st.sidebar.info(f"🤖 **機器人帳號：**\n\n`{bot_email}`\n\n(請確認已將試算表共用給這個 Email)")
except Exception as e:
    # 這裡的錯誤已經在 get_google_sheet_data 處理過了，這裡只是保險
    st.stop()

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

            # 取得試算表網址
            sheet_url = s_info.get("spreadsheet")
            if not sheet_url:
                st.error("❌ Secrets 中缺少 'spreadsheet' 設定。")
                st.stop()

            # 開啟試算表
            spreadsheet = client.open_by_url(sheet_url)
            sheet = spreadsheet.get_worksheet(0) # 寫入第一頁
            
            # 寫入資料
            sheet.append_row(row_data)
            
            st.success(f"✅ {name} 點餐成功！")
            st.balloons()
            
        except Exception as e:
            error_msg = str(e)
            st.error(f"⚠️ 寫入失敗：{error_msg}")
            
            # 智慧錯誤分析
            if "403" in error_msg or "permission" in error_msg.lower():
                st.warning(f"🚨 **權限錯誤！**\n請複製側邊欄那個 `iam.gserviceaccount.com` 的 Email，\n去您的 Google 試算表按「共用」，把它加為「編輯者」。")
            elif "404" in error_msg or "not found" in error_msg.lower():
                st.warning("🚨 **找不到試算表！**\n請確認 Secrets 裡的網址是否正確，且您已將試算表共用給機器人。")
            elif "API has not been used" in error_msg:
                st.warning("🚨 **API 未啟用！**\n請去 Google Cloud Console 啟用 Google Sheets API。")

# ==========================================
# 5. 顯示目前清單
# ==========================================
st.divider()
st.write("📊 **目前訂單列表：**")
try:
    sheet_url = s_info.get("spreadsheet")
    if sheet_url:
        spreadsheet = client.open_by_url(sheet_url)
        sheet = spreadsheet.get_worksheet(0)
        data = sheet.get_all_records()
        if data:
            st.dataframe(pd.DataFrame(data))
        else:
            st.info("目前沒有資料")
except Exception as e:
    st.info("等待訂單中...")
