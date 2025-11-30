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
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            s_info = st.secrets["connections"]["gsheets"]
        elif "type" in st.secrets and "project_id" in st.secrets:
            s_info = st.secrets
        else:
            raise ValueError("找不到憑證！請確認 Secrets 設定中包含 [connections.gsheets] 區塊。")

        # --- 2. 處理 Private Key 格式問題 ---
        private_key = s_info["private_key"]
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

        # --- 3. 建立憑證物件 ---
        creds_dict = {
            "type": s_info["type"],
            "project_id": s_info["project_id"],
            "private_key_id": s_info["private_key_id"],
            "private_key": private_key,
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
# 2. 讀取雲端菜單 (新增功能)
# ==========================================
# 設定 TTL=60 秒，代表菜單更新後，網頁約 1 分鐘後會抓到新資料
@st.cache_data(ttl=60)
def load_menu_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        # 嘗試讀取名為 "菜單設定" 的分頁
        try:
            worksheet = spreadsheet.worksheet("菜單設定")
        except gspread.WorksheetNotFound:
            return None, "找不到「菜單設定」分頁"
            
        records = worksheet.get_all_records()
        
        # 將資料轉換成程式需要的格式: {店家: {品項: 價格}}
        cloud_menus = {}
        for row in records:
            store = str(row.get("店家", "")).strip()
            item = str(row.get("品項", "")).strip()
            price_raw = row.get("價格", 0)
            
            if store and item:
                if store not in cloud_menus:
                    cloud_menus[store] = {}
                try:
                    cloud_menus[store][item] = int(price_raw)
                except:
                    cloud_menus[store][item] = 0
                    
        if not cloud_menus:
            return None, "菜單分頁是空的"
            
        return cloud_menus, None

    except Exception as e:
        return None, str(e)


# ==========================================
# 3. 預設備用菜單 (當雲端讀不到時使用)
# ==========================================
DEFAULT_MENUS = {
    "範例店家(未設定雲端菜單)": {
        "測試紅茶": 30, "測試綠茶": 30
    }
}

SUGAR_OPTS = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "一分糖", "無糖"]
ICE_OPTS = ["正常冰", "少冰", "微冰", "去冰", "常溫", "熱"]

# ==========================================
# 4. 網頁介面
# ==========================================
st.title("🥤 辦公室飲料點餐系統")

# 初始化變數
client = None
s_info = None
current_menus = DEFAULT_MENUS

# --- 連線與資料載入 ---
try:
    client, s_info = get_google_sheet_data()
    sheet_url = s_info.get("spreadsheet")
    
    # 嘗試讀取雲端菜單
    if sheet_url:
        cloud_menus, error_msg = load_menu_from_sheet(client, sheet_url)
        if cloud_menus:
            current_menus = cloud_menus
            st.toast("✅ 雲端菜單更新成功！")
        else:
            # 讀取失敗時顯示提示 (在側邊欄)
            st.sidebar.warning(f"⚠️ 使用預設菜單 ({error_msg})")
            st.sidebar.info("💡 **如何啟用雲端菜單？**\n\n請在您的 Google 試算表中新增一個分頁，名稱改為 `菜單設定`，並建立三欄：`店家`、`品項`、`價格`。")

except Exception as e:
    st.sidebar.error(f"連線異常")


st.sidebar.header("點餐設定")

# 如果沒有菜單資料 (全空)
if not current_menus:
    st.error("❌ 無法載入任何菜單，請檢查 Google Sheet 設定。")
    st.stop()

selected_store = st.sidebar.selectbox("今天喝哪一家？", list(current_menus.keys()))
current_menu_items = current_menus[selected_store]
st.subheader(f"目前店家：{selected_store}")

with st.form("order_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("你的名字 (必填)")
    with col2:
        drink = st.selectbox("飲料品項", list(current_menu_items.keys()))
    col3, col4 = st.columns(2)
    with col3:
        sugar = st.selectbox("甜度", SUGAR_OPTS)
    with col4:
        ice = st.selectbox("冰塊", ICE_OPTS)
    note = st.text_input("備註")
    
    submitted = st.form_submit_button("送出訂單")

# ==========================================
# 5. 送出訂單邏輯
# ==========================================
if submitted:
    if not name:
        st.error("❌ 請記得輸入名字！")
    else:
        try:
            # 準備資料
            price = current_menu_items[drink]
            order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row_data = [order_time, selected_store, name, drink, price, sugar, ice, note]

            # 寫入資料
            sheet_url = s_info.get("spreadsheet")
            spreadsheet = client.open_by_url(sheet_url)
            # 嘗試寫入第一個分頁 (通常是訂單紀錄頁)
            # 建議把「菜單設定」放在第二頁，讓第一頁專門存訂單
            sheet = spreadsheet.get_worksheet(0) 
            
            sheet.append_row(row_data)
            
            st.success(f"✅ {name} 點餐成功！")
            st.balloons()
            
        except Exception as e:
            st.error(f"⚠️ 寫入失敗：{e}")

# ==========================================
# 6. 顯示訂單列表
# ==========================================
st.divider()
st.write("📊 **目前訂單列表：**")
try:
    if s_info:
        sheet_url = s_info.get("spreadsheet")
        spreadsheet = client.open_by_url(sheet_url)
        sheet = spreadsheet.get_worksheet(0)
        data = sheet.get_all_records()
        if data:
            st.dataframe(pd.DataFrame(data))
        else:
            st.info("目前沒有資料")
except:
    pass
