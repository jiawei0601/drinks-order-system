import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# PDF 相關套件
import requests
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO

# ==========================================
# 0. PDF 字型設定 (解決中文亂碼問題)
# ==========================================
@st.cache_resource
def setup_chinese_font():
    font_path = "chinese_font.ttf"
    url_primary = "https://raw.githubusercontent.com/justfont/open-huninn-font/master/font/jf-openhuninn-1.1.ttf"
    url_backup = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
    
    def download_font(url):
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                if len(response.content) < 1000 or response.content.startswith(b"<") or response.content.startswith(b"\n"):
                    return False
                with open(font_path, "wb") as f:
                    f.write(response.content)
                return True
            return False
        except:
            return False

    if not os.path.exists(font_path):
        with st.spinner("正在下載中文字型以支援 PDF (第一次需約 10 秒)..."):
            if not download_font(url_primary):
                if not download_font(url_backup):
                    st.error("⚠️ 無法下載中文字型，PDF 報表可能會顯示亂碼。")
                    return None
    try:
        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
        return 'ChineseFont'
    except Exception as e:
        if os.path.exists(font_path):
            os.remove(font_path)
        st.warning(f"字型載入異常 ({e})，請重新整理頁面試試。")
        return None

# ==========================================
# 1. Google Sheets 連線設定
# ==========================================
@st.cache_resource
def get_google_sheet_data():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            s_info = st.secrets["connections"]["gsheets"]
        elif "type" in st.secrets and "project_id" in st.secrets:
            s_info = st.secrets
        else:
            raise ValueError("找不到憑證！請確認 Secrets 設定。")

        private_key = s_info["private_key"]
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

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
        client = gspread.authorize(creds)
        return client, s_info

    except KeyError as e:
        st.error(f"❌ Secrets 設定缺少必要欄位：{e}")
        st.stop()
    except Exception as e:
        st.error(f"❌ Google 連線發生錯誤：{e}")
        st.stop()

# ==========================================
# 2. 資料讀取 (菜單、加料 & 訂單) - 含快取機制
# ==========================================

# 讀取菜單
@st.cache_data(ttl=60)
def load_menu_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        try:
            worksheet = spreadsheet.worksheet("菜單設定")
        except gspread.WorksheetNotFound:
            return None, "找不到「菜單設定」分頁"
        
        rows = worksheet.get_all_values()
        if len(rows) < 2:
            return None, "菜單分頁沒有資料"
            
        headers = [h.strip() for h in rows[0]]
        
        def get_col_index(possible_names):
            for name in possible_names:
                if name in headers:
                    return headers.index(name)
            return -1

        idx_store = get_col_index(["店家", "Store"])
        idx_item = get_col_index(["品項", "Item", "飲料"])
        idx_m = get_col_index(["中杯", "M", "m", "中"])
        idx_l = get_col_index(["大杯", "L", "l", "大"])
        idx_price = get_col_index(["價格", "Price", "單一規格"])
        
        if idx_store == -1 or idx_item == -1:
             return None, "找不到「店家」或「品項」欄位，請檢查 Google Sheet 標題。"

        cloud_menus = {}
        for row in rows[1:]:
            if len(row) <= max(idx_store, idx_item): continue
            
            store = row[idx_store].strip()
            item = row[idx_item].strip()
            
            if not store or not item: continue
            
            item_prices = {}
            
            def get_clean_price(idx):
                if idx != -1 and idx < len(row):
                    val = str(row[idx]).replace("$", "").replace(",", "").strip()
                    if val.isdigit():
                        return int(val)
                return None

            p_m = get_clean_price(idx_m)
            p_l = get_clean_price(idx_l)
            p_s = get_clean_price(idx_price)
            
            if p_m: item_prices["中杯"] = p_m
            if p_l: item_prices["大杯"] = p_l
            
            if not item_prices:
                if p_s: 
                    item_prices["單一規格"] = p_s
                else:
                    item_prices = {"單一規格": 0}
            
            if store not in cloud_menus:
                cloud_menus[store] = {}
            cloud_menus[store][item] = item_prices
            
        return cloud_menus, None

    except Exception as e:
        return None, str(e)

# 讀取加料設定
@st.cache_data(ttl=60)
def load_toppings_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        try:
            worksheet = spreadsheet.worksheet("加料設定")
        except gspread.WorksheetNotFound:
            return {} 
            
        rows = worksheet.get_all_values()
        if len(rows) < 2: return {}
        
        headers = [h.strip() for h in rows[0]]
        
        try:
            idx_store = headers.index("店家")
            idx_name = headers.index("加料品項") if "加料品項" in headers else headers.index("品項")
            idx_price = headers.index("價格")
        except:
            return {}

        toppings = {}
        for row in rows[1:]:
            if len(row) <= max(idx_store, idx_name, idx_price): continue
            store = str(row[idx_store]).strip()
            name = str(row[idx_name]).strip()
            price_str = str(row[idx_price]).replace("$", "").replace(",", "").strip()
            
            if store and name and price_str.isdigit():
                if store not in toppings:
                    toppings[store] = {}
                toppings[store][name] = int(price_str)
        return toppings
    except Exception:
        return {}

# 讀取訂單 (快取 5 秒)
@st.cache_data(ttl=5)
def get_orders_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        sheet = spreadsheet.get_worksheet(0)
        return sheet.get_all_values()
    except Exception:
        return []

# ==========================================
# 3. PDF 生成函式
# ==========================================
def generate_pdf_report(df, total_amount):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    
    font_name = setup_chinese_font()
    if not font_name:
        font_name = 'Helvetica'

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontName=font_name, fontSize=20, leading=24)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName=font_name, fontSize=12, leading=16)
    
    today = datetime.now().strftime("%Y-%m-%d")
    elements.append(Paragraph(f"飲料訂購結算單 ({today})", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"今日總營業額：{total_amount} 元", normal_style))
    elements.append(Spacer(1, 12))
    
    display_cols = ['時間', '姓名', '品項', '大小', '加料', '甜度', '冰塊', '價格', '備註']
    cols = [c for c in display_cols if c in df.columns]
    
    data = [cols] + df[cols].values.tolist()
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black),
        ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 10), 
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

DEFAULT_MENUS = {"範例店家": {"紅茶": {"單一規格": 30}}}
SUGAR_OPTS = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "一分糖", "無糖"]
ICE_OPTS = ["正常冰", "少冰", "微冰", "去冰", "常溫", "熱"]

# ==========================================
# 4. 主程式介面
# ==========================================
st.title("🥤 辦公室飲料點餐系統")

client = None
s_info = None
current_menus = DEFAULT_MENUS
all_toppings = {}

# --- 連線與資料載入 ---
try:
    client, s_info = get_google_sheet_data()
    sheet_url = s_info.get("spreadsheet")
    if sheet_url:
        cloud_menus, error_msg = load_menu_from_sheet(client, sheet_url)
        all_toppings = load_toppings_from_sheet(client, sheet_url)
        
        if cloud_menus:
            current_menus = cloud_menus
        else:
            st.sidebar.warning(f"⚠️ 使用預設菜單 ({error_msg})")
except Exception as e:
    st.sidebar.error(f"連線異常: {e}")

st.sidebar.header("點餐設定")

if not current_menus:
    st.error("❌ 無法載入菜單")
    st.stop()

selected_store = st.sidebar.selectbox("今天喝哪一家？", list(current_menus.keys()))
current_menu_items = current_menus[selected_store]
st.subheader(f"目前店家：{selected_store}")

# 點餐區塊
st.write("---")
col1, col2 = st.columns(2)
with col1:
    name = st.text_input("你的名字 (必填)")
with col2:
    drink = st.selectbox("飲料品項", list(current_menu_items.keys()))
    price_dict = current_menu_items[drink]

col3, col4, col5 = st.columns(3)
with col3:
    size = st.selectbox("大小", list(price_dict.keys()))
    base_price = price_dict[size]
with col4:
    sugar = st.selectbox("甜度", SUGAR_OPTS)
with col5:
    ice = st.selectbox("冰塊", ICE_OPTS)

# --- 加料區塊 ---
topping_price = 0
selected_toppings = []
store_toppings_options = all_toppings.get(selected_store, {})

if store_toppings_options:
    st.write("---")
    st.markdown("#### 🍬 加料區")
    topping_labels = [f"{name} (+{price})" for name, price in store_toppings_options.items()]
    selected_labels = st.multiselect("選擇配料", topping_labels)
    
    for label in selected_labels:
        t_name = label.split(" (+")[0]
        t_price = store_toppings_options[t_name]
        topping_price += t_price
        selected_toppings.append(t_name)
else:
    st.caption("(此店家目前無設定加料選項)")

final_price = base_price + topping_price
st.write("---")
st.info(f"💰 **總金額：{final_price} 元** (飲料 {base_price} + 加料 {topping_price})")

note = st.text_input("備註")

if st.button("送出訂單", type="primary"):
    if not name:
        st.error("❌ 請記得輸入名字！")
    else:
        try:
            order_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            topping_str = ", ".join(selected_toppings) if selected_toppings else ""
            
            row_data = [
                order_time, selected_store, name, drink, size, 
                topping_str, final_price, sugar, ice, note
            ]
            
            sheet_url = s_info.get("spreadsheet")
            spreadsheet = client.open_by_url(sheet_url)
            sheet = spreadsheet.get_worksheet(0) 
            sheet.append_row(row_data)
            
            # 清除訂單快取
            get_orders_from_sheet.clear()
            
            st.success(f"✅ {name} 點餐成功！")
            st.balloons()
        except Exception as e:
            st.error(f"⚠️ 寫入失敗：{e}")

# ==========================================
# 5. 管理員結算專區 (包含訂單編輯)
# ==========================================
st.sidebar.divider()
st.sidebar.header("👮‍♂️ 管理員專區")

if st.sidebar.checkbox("開啟結算功能"):
    st.divider()
    st.header("💰 結算管理")
    
    try:
        if s_info:
            sheet_url = s_info.get("spreadsheet")
            # 改用快取函式讀取資料
            all_values = get_orders_from_sheet(client, sheet_url)
            
            if len(all_values) > 1:
                headers = all_values[0]
                rows = all_values[1:]
                
                valid_indices = [i for i, h in enumerate(headers) if h.strip()]
                
                if not valid_indices:
                    st.warning("⚠️ 讀取失敗：找不到任何有效的欄位標題。")
                else:
                    clean_headers = [headers[i] for i in valid_indices]
                    clean_rows = []
                    for row in rows:
                        clean_row = [row[i] if i < len(row) else "" for i in valid_indices]
                        clean_rows.append(clean_row)
                    
                    df = pd.DataFrame(clean_rows, columns=clean_headers)
                    
                    total_amount = 0
                    if '價格' in df.columns:
                        total_amount = pd.to_numeric(df['價格'], errors='coerce').fillna(0).sum()
                    elif 'Price' in df.columns:
                        total_amount = pd.to_numeric(df['Price'], errors='coerce').fillna(0).sum()
                    
                    st.metric("💵 今日總營業額", f"{int(total_amount)} 元")
                    
                    # --- 編輯區塊 ---
                    st.markdown("### ✏️ 訂單管理與編輯")
                    st.caption("您可以直接點擊表格修改內容，或選取左側方框刪除列。修改完請務必按下方「儲存變更」。")
                    
                    edited_df = st.data_editor(
                        df, 
                        num_rows="dynamic",
                        use_container_width=True,
                        key="order_editor"
                    )
                    
                    if st.button("💾 儲存變更 (Save Changes)", type="primary"):
                        try:
                            # 準備寫入的資料
                            updated_headers = edited_df.columns.tolist()
                            updated_values = edited_df.astype(str).values.tolist()
                            all_data = [updated_headers] + updated_values
                            
                            spreadsheet = client.open_by_url(sheet_url)
                            sheet = spreadsheet.get_worksheet(0)
                            
                            sheet.clear()
                            sheet.update(values=all_data)
                            
                            # 清除快取
                            get_orders_from_sheet.clear()
                            
                            st.success("✅ 訂單已更新成功！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"儲存失敗：{e}")
                    
                    st.write("---")
                    
                    pdf_bytes = generate_pdf_report(df, int(total_amount))
                    st.download_button(
                        label="📄 下載 PDF 結算單",
                        data=pdf_bytes,
                        file_name=f"飲料結算_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime='application/pdf',
                    )
                    
                    st.write("---")
                    st.warning("⚠️ **危險操作區**")
                    
                    if st.button("🗑️ 清空所有訂單 (歸零)"):
                        try:
                            standard_headers = ['時間', '店家', '姓名', '品項', '大小', '加料', '價格', '甜度', '冰塊', '備註']
                            spreadsheet = client.open_by_url(sheet_url)
                            sheet = spreadsheet.get_worksheet(0)
                            sheet.clear()
                            sheet.append_row(standard_headers)
                            
                            # 清除快取
                            get_orders_from_sheet.clear()
                            
                            st.success("✅ 資料已清空，可以開始新的一天了！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"清空失敗：{e}")
            else:
                st.info("📭 目前是空的，沒有訂單。")
    except Exception as e:
        st.error(f"讀取資料失敗：{e}")

# ==========================================
# 6. 訂單列表 (常駐顯示)
# ==========================================
st.divider()
st.write("📊 **目前訂單列表：**")
try:
    if s_info:
        sheet_url = s_info.get("spreadsheet")
        all_values = get_orders_from_sheet(client, sheet_url)
        
        if len(all_values) > 1:
            headers = all_values[0]
            rows = all_values[1:]
            
            valid_indices = [i for i, h in enumerate(headers) if h.strip()]
            if valid_indices:
                clean_headers = [headers[i] for i in valid_indices]
                clean_rows = []
                for row in rows:
                    clean_row = [row[i] if i < len(row) else "" for i in valid_indices]
                    clean_rows.append(clean_row)
                
                df = pd.DataFrame(clean_rows, columns=clean_headers)
                st.dataframe(df)
        else:
            st.info("目前沒有資料")
except:
    pass
