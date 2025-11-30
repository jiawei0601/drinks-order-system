import streamlit as st
import pandas as pd
from datetime import datetime

st.title("🥤 辦公室飲料點餐系統")

# 簡單的點餐表單
with st.form("order_form"):
    name = st.text_input("你的名字")
    drink = st.selectbox("想喝什麼", ["紅茶", "綠茶", "珍奶"])
    submitted = st.form_submit_button("送出")

    if submitted:
        st.success(f"{name} 點了 {drink}！")
        # 注意：雲端重啟後 CSV 會重置，長期使用建議串接 Google Sheets