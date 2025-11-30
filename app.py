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
# 2. 讀取雲端菜單 (功能升級：支援大小杯)
# ==========================================
@st.cache_data(ttl=60)
def load_menu_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        try:
            worksheet = spreadsheet.worksheet("菜單設定")
        except gspread.WorksheetNotFound:
            return None, "找不到「菜單設定」分頁"
            
        records = worksheet.get_all_records()
        
        # 資料格式轉換: {店家: {品項: {規格: 價格}}}
        cloud_menus = {}
        for row in records:
            store = str(row.get("店家", "")).strip()
            item = str(row.get("品項", "")).strip()
            
            # 支援多種欄位名稱
            price_m = row.get("中杯") or row.get("M")
            price_l = row.get("大杯") or row.get("L")
            price_single = row.get("價格") # 舊格式相容
            
            if store and item:
                if store not in cloud_menus:
                    cloud_menus[store] = {}
                
                # 建構該品項的價格表
                item_prices = {}
                
                # 嘗試解析中杯
                try:
                    if price_m and int(price_m) > 0: item_prices["中杯"] = int(price_m)
                except: pass
                
                # 嘗試解析大杯
                try:
                    if price_l and int(price_l) > 0: item_prices["大杯"] = int(price_l)
                except: pass
                
                # 如果沒有分大小，試試看舊的單一價格
                if not item_prices:
                    try:
                        if price_single and int(price_single) > 0: item_prices["單一規格"] = int(price_single)
                    except: pass
                
                # 如果還是空的，預設為 0
                if not item_prices:
                    item_prices = {"單一規格": 0}

                cloud_menus[store][item] = item_prices
                    
        if not cloud_menus:
            return None, "菜單分頁是空的"
            
        return cloud_menus, None

    except Exception as e:
        return None, str(e)


# ==========================================
# 3. 預設備用菜單 (更新為含規格結構)
# ==========================================
DEFAULT_MENUS = {
    "範例店家(未設定雲端菜單)": {
        "測試紅茶": {"中杯": 30, "大杯": 35},
        "測試綠茶": {"單一規格": 30}
    }
}

SUGAR_OPTS = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "一分糖", "無糖"]
ICE_OPTS = ["正常冰", "少冰", "微冰", "去冰", "常溫", "熱"]

# ==========================================
# 4. 網頁介面
# ==========================================
st.title("🥤 辦公室飲料點餐系統")

client = None
s_info = None
current_menus = DEFAULT_MENUS

# --- 連線與資料載入 ---
try:
    client, s_info = get_google_sheet_data()
    sheet_url = s_info.get("spreadsheet")
    
    if sheet_url:
        cloud_menus, error_msg = load_menu_from_sheet(client, sheet_url)
        if cloud_menus:
            current_menus = cloud_menus
            st.toast("✅ 雲端菜單更新成功！")
        else:
            st.sidebar.warning(f"⚠️ 使用預設菜單 ({error_msg})")
            st.sidebar.info("💡 **如何設定大小杯？**\n\n請在 Google 試算表「菜單設定」分頁，將欄位設為：`店家`、`品項`、`中杯`、`大杯`。")

except Exception as e:
    st.sidebar.error(f"連線異常")


st.sidebar.header("點餐設定")

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
        # 取得該飲料的規格與價格表
        price_dict = current_menu_items[drink]

    # 改用三欄位佈局，加入大小選擇
    col3, col4, col5 = st.columns(3)
    with col3:
        # 大小選單
        size = st.selectbox("大小", list(price_dict.keys()))
        price = price_dict[size]
        st.caption(f"💰 價格：{price} 元")
    with col4:
        sugar = st.selectbox("甜度", SUGAR_OPTS)
    with col5:
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
            order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 新增 size 欄位
            row_data = [order_time, selected_store, name, drink, size, price, sugar, ice, note]

            sheet_url = s_info.get("spreadsheet")
            spreadsheet = client.open_by_url(sheet_url)
            sheet = spreadsheet.get_worksheet(0) 
            
            sheet.append_row(row_data)
            
            st.success(f"✅ {name} 點餐成功！({drink} {size})")
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
