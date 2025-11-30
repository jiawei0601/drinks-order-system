import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 1. 基礎設定與菜單資料
# ==========================================

# 設定網頁標題與圖示
st.set_page_config(page_title="辦公室點餐系統", page_icon="🥤")

# 建立 Google Sheets 連線
# ⚠️ 注意：必須先在 Streamlit Cloud 的 Secrets 設定好 [connections.gsheets]
conn = st.connection("gsheets", type=GSheetsConnection)

# 定義菜單 (您可以隨時在這裡新增店家或修改價格)
ALL_MENUS = {
    "可不可熟成紅茶": {
        "熟成紅茶": 30,
        "鴉片紅茶": 30,
        "太妃紅茶": 35,
        "熟成冷露": 30,
        "白玉歐蕾": 50,
        "春梅冰茶": 45
    },
    "50嵐": {
        "四季春青茶": 30,
        "黃金烏龍": 30,
        "珍珠奶茶": 50,
        "波霸奶茶": 50,
        "紅茶拿鐵": 55,
        "8冰綠": 50
    },
    "迷客夏": {
        "大正紅茶拿鐵": 60,
        "伯爵紅茶拿鐵": 60,
        "珍珠紅茶拿鐵": 65,
        "柳丁綠茶": 60,
        "芋頭鮮奶": 65
    }
}

# 定義通用選項
SUGAR_OPTS = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "一分糖", "無糖"]
ICE_OPTS = ["正常冰", "少冰", "微冰", "去冰", "常溫", "熱"]

# ==========================================
# 2. 網頁介面設計
# ==========================================

st.title("🥤 辦公室飲料點餐系統")

# --- 側邊欄：選擇店家 ---
st.sidebar.header("設定")
selected_store = st.sidebar.selectbox("今天喝哪一家？", list(ALL_MENUS.keys()))

# 根據選擇載入對應菜單
current_menu = ALL_MENUS[selected_store]
st.subheader(f"目前店家：{selected_store}")

# --- 主表單區域 ---
with st.form("order_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("你的名字 (必填)")
    with col2:
        # 下拉選單會自動根據上面的 current_menu 變換
        drink = st.selectbox("飲料品項", list(current_menu.keys()))
    
    col3, col4 = st.columns(2)
    with col3:
        sugar = st.selectbox("甜度", SUGAR_OPTS)
    with col4:
        ice = st.selectbox("冰塊", ICE_OPTS)
        
    note = st.text_input("備註 (例如: 加珍珠+10元)")

    # 送出按鈕
    submitted = st.form_submit_button("送出訂單")

# ==========================================
# 3. 邏輯處理：送出訂單與儲存
# ==========================================

if submitted:
    if not name:
        st.error("❌ 請記得輸入名字！")
    else:
        try:
            # 3-1. 準備要寫入的新資料
            price = current_menu[drink]
            order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            new_entry = pd.DataFrame([{
                "時間": order_time,
                "店家": selected_store,
                "姓名": name,
                "品項": drink,
                "價格": price,
                "甜度": sugar,
                "冰塊": ice,
                "備註": note
            }])

            # 3-2. 讀取目前的 Google Sheet 資料 (ttl=0 代表不快取，強制抓最新的)
            # 預設寫入 Sheet1，如果你的分頁名稱不同請修改 worksheet="你的分頁名稱"
            try:
                existing_data = conn.read(worksheet="Sheet1", usecols=list(range(8)), ttl=0)
                # 簡單檢查是否為空表格
                if existing_data.empty:
                    updated_data = new_entry
                else:
                    updated_data = pd.concat([existing_data, new_entry], ignore_index=True)
            except:
                # 如果讀取失敗(例如表格是全空的)，直接當作這是第一筆資料
                updated_data = new_entry

            # 3-3. 將合併後的資料寫回 Google Sheet
            conn.update(worksheet="Sheet1", data=updated_data)

            # 3-4. 成功訊息
            st.success(f"✅ {name} 點餐成功！資料已寫入試算表。")
            st.balloons()
            
        except Exception as e:
            st.error(f"⚠️ 寫入失敗，請檢查 Secrets 設定。錯誤訊息：{e}")

# ==========================================
# 4. 顯示目前統計 (選用功能)
# ==========================================
st.divider()
st.write("📊 **目前訂單列表：**")

try:
    # 再次讀取顯示給使用者看
    display_df = conn.read(worksheet="Sheet1", ttl=0)
    st.dataframe(display_df)
except:
    st.info("目前還沒有訂單，或是無法讀取試算表。")
