import streamlit as st
import pandas as pd
from datetime import datetime

# --- 1. 設定區 (請在這裡修改你的菜單) ---
STORE_NAME = "大安區手搖飲"
menu = {
    "熟成紅茶": 30,
    "春芽綠茶": 30,
    "白玉歐蕾": 50,
    "熟成冷露": 35,
    "春梅冰茶": 45
}
sugar_opts = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "無糖"]
ice_opts = ["正常冰", "少冰", "微冰", "去冰", "溫", "熱"]

# --- 2. 網頁介面設計 ---
st.title(f"🥤 {STORE_NAME} 點餐系統")

st.write("### 請填寫訂購資訊")

# 建立表單
with st.form("order_form"):
    # 輸入欄位
    col1, col2 = st.columns(2) # 分成兩欄比較好看
    with col1:
        name = st.text_input("你的名字 (必填)")
    with col2:
        drink = st.selectbox("飲料品項", list(menu.keys()))
    
    col3, col4 = st.columns(2)
    with col3:
        sugar = st.selectbox("甜度", sugar_opts)
    with col4:
        ice = st.selectbox("冰塊", ice_opts)
        
    # 備註欄位
    note = st.text_input("備註 (例如: 如果沒珍珠改椰果)")

    # 送出按鈕
    submitted = st.form_submit_button("送出訂單")

    # --- 3. 送出後的處理邏輯 ---
    if submitted:
        if not name:
            st.error("請記得輸入名字喔！")
        else:
            price = menu[drink] # 自動抓取價格
            order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 顯示成功訊息
            st.success(f"✅ 訂單已接收！")
            st.info(f"{name} 點了：{drink} ({price}元) / {sugar} / {ice}")
            
            # (之後這下面要加上儲存到 Google Sheet 的程式碼)
