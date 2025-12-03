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

# Google Drive 相關套件
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# 1. 核心設定與初始化
# ==========================================
st.set_page_config(page_title="辦公室飲料點餐系統", page_icon="🥤", layout="wide")

# 設定常數
DEFAULT_MENUS = {"範例店家": {"紅茶": {"單一規格": 30}}}
SUGAR_OPTS = ["正常糖", "少糖 (8分)", "半糖 (5分)", "微糖 (3分)", "一分糖", "無糖"]
ICE_OPTS = ["正常冰", "少冰", "微冰", "去冰", "常溫", "熱"]

# 初始化字型 (快取資源)
@st.cache_resource
def setup_chinese_font():
    font_path = "chinese_font.ttf"
    # 優先使用 Open Huninn (粉圓體)，備用 Google Noto Sans TC
    urls = [
        "https://raw.githubusercontent.com/justfont/open-huninn-font/master/font/jf-openhuninn-1.1.ttf",
        "https://github.com/google/fonts/raw/main/ofl/notosanstc/static/NotoSansTC-Regular.ttf"
    ]
    
    # 檢查並下載字型
    if not os.path.exists(font_path):
        with st.spinner("正在初始化系統字型 (第一次需約 10 秒)..."):
            downloaded = False
            for url in urls:
                try:
                    response = requests.get(url, timeout=15)
                    # 檢查內容是否為有效的二進位檔 (避免下載到 HTML 錯誤頁面)
                    if response.status_code == 200 and len(response.content) > 1000 and not response.content.startswith(b"<"):
                        with open(font_path, "wb") as f:
                            f.write(response.content)
                        downloaded = True
                        break
                except:
                    continue
            
            if not downloaded:
                st.error("⚠️ 無法下載中文字型，PDF 報表可能會顯示亂碼。")
                return None

    try:
        pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
        return 'ChineseFont'
    except Exception:
        # 如果註冊失敗（例如檔案損壞），刪除檔案以便下次重試
        if os.path.exists(font_path): os.remove(font_path)
        return None

# 初始化 Google Sheet 連線 (快取資源)
@st.cache_resource
def get_google_sheet_data():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        # 取得 Secrets
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            s_info = st.secrets["connections"]["gsheets"]
        elif "type" in st.secrets and "project_id" in st.secrets:
            s_info = st.secrets
        else:
            raise ValueError("找不到憑證！請確認 Secrets 設定。")

        # 修復 Private Key
        private_key = s_info["private_key"]
        if "\\n" in private_key:
            private_key = private_key.replace("\\n", "\n")

        # 建立憑證
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
    except Exception as e:
        st.error(f"連線設定錯誤: {e}")
        st.stop()

# ==========================================
# 2. 資料讀取層 (Data Access Layer)
# ==========================================

# 讀取菜單 (快取 60s)
@st.cache_data(ttl=60)
def load_menu_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        try:
            worksheet = spreadsheet.worksheet("菜單設定")
        except gspread.WorksheetNotFound:
            return None, "找不到「菜單設定」分頁"
        
        rows = worksheet.get_all_values()
        if len(rows) < 2: return None, "無資料"
        
        headers = [h.strip() for h in rows[0]]
        
        # 欄位對應
        def find_idx(candidates):
            for c in candidates:
                if c in headers: return headers.index(c)
            return -1
            
        idx_store = find_idx(["店家", "Store"])
        idx_item = find_idx(["品項", "Item", "飲料"])
        idx_m = find_idx(["中杯", "M", "m", "中"])
        idx_l = find_idx(["大杯", "L", "l", "大"])
        idx_price = find_idx(["價格", "Price", "單一規格"])
        
        if idx_store == -1 or idx_item == -1: return None, "欄位對應失敗"

        menus = {}
        for row in rows[1:]:
            if len(row) <= max(idx_store, idx_item): continue
            store, item = row[idx_store].strip(), row[idx_item].strip()
            if not store or not item: continue
            
            prices = {}
            def clean_p(val):
                v = str(val).replace("$", "").replace(",", "").strip()
                return int(v) if v.isdigit() else None

            pm, pl, pp = None, None, None
            if idx_m != -1 and idx_m < len(row): pm = clean_p(row[idx_m])
            if idx_l != -1 and idx_l < len(row): pl = clean_p(row[idx_l])
            if idx_price != -1 and idx_price < len(row): pp = clean_p(row[idx_price])
            
            if pm: prices["中杯"] = pm
            if pl: prices["大杯"] = pl
            if not prices: prices["單一規格"] = pp if pp else 0
            
            if store not in menus: menus[store] = {}
            menus[store][item] = prices
            
        return menus, None
    except Exception as e:
        return None, str(e)

# 讀取加料 (快取 60s)
@st.cache_data(ttl=60)
def load_toppings_from_sheet(_client, sheet_url):
    try:
        sh = _client.open_by_url(sheet_url)
        ws = sh.worksheet("加料設定")
        rows = ws.get_all_values()
        if len(rows) < 2: return {}
        
        headers = [h.strip() for h in rows[0]]
        idx_store = headers.index("店家") if "店家" in headers else -1
        idx_name = headers.index("加料品項") if "加料品項" in headers else headers.index("品項")
        idx_price = headers.index("價格") if "價格" in headers else -1
        
        if idx_store == -1 or idx_name == -1 or idx_price == -1: return {}
        
        toppings = {}
        for row in rows[1:]:
            if len(row) <= max(idx_store, idx_name, idx_price): continue
            store, name = row[idx_store].strip(), row[idx_name].strip()
            price = str(row[idx_price]).replace("$", "").strip()
            if store and name and price.isdigit():
                if store not in toppings: toppings[store] = {}
                toppings[store][name] = int(price)
        return toppings
    except:
        return {}

# 讀取存款 (快取 60s)
@st.cache_data(ttl=60)
def load_balances_from_sheet(_client, sheet_url):
    try:
        sh = _client.open_by_url(sheet_url)
        ws = sh.worksheet("會員儲值")
        rows = ws.get_all_values()
        if len(rows) < 2: return {}
        
        headers = [h.strip() for h in rows[0]]
        idx_name = -1
        for k in ["姓名", "Name", "員工", "員工姓名"]:
            if k in headers: 
                idx_name = headers.index(k)
                break
        
        idx_bal = -1
        for k in ["存款餘額", "餘額", "存款", "Balance", "金額", "目前餘額"]:
            if k in headers:
                idx_bal = headers.index(k)
                break
                
        if idx_name == -1 or idx_bal == -1: return {}
        
        balances = {}
        for row in rows[1:]:
            if len(row) <= max(idx_name, idx_bal): continue
            name = str(row[idx_name]).strip()
            bal = str(row[idx_bal]).replace("$", "").replace(",", "").strip()
            if name:
                try: balances[name] = int(float(bal))
                except: balances[name] = 0
        return balances
    except:
        return {}

# 讀取訂單 (快取 5s - 高頻率)
@st.cache_data(ttl=5)
def get_orders_from_sheet(_client, sheet_url):
    try:
        sh = _client.open_by_url(sheet_url)
        ws = sh.get_worksheet(0)
        return ws.get_all_values()
    except:
        return []

# ==========================================
# 3. 功能操作層 (Actions Layer)
# ==========================================

# 寫入交易紀錄
def log_transaction(_client, sheet_url, name, amount_change, new_balance, note=""):
    try:
        sh = _client.open_by_url(sheet_url)
        try:
            ws_log = sh.worksheet("交易紀錄")
        except:
            ws_log = sh.add_worksheet(title="交易紀錄", rows=1000, cols=5)
            ws_log.append_row(["時間", "姓名", "變動金額", "變動後餘額", "備註"])
        
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws_log.append_row([ts, name, amount_change, new_balance, note])
        return True
    except Exception as e:
        print(f"Log Error: {e}")
        return False

# 產生 PDF
def generate_pdf_report(df, total_amount):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    
    font_name = setup_chinese_font() or 'Helvetica'
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontName=font_name, fontSize=20, leading=24)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName=font_name, fontSize=12, leading=16)
    
    today = datetime.now().strftime("%Y-%m-%d")
    elements.append(Paragraph(f"飲料訂購結算單 ({today})", title_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"今日總營業額：{total_amount} 元", normal_style))
    elements.append(Spacer(1, 12))
    
    cols_to_show = ['時間', '姓名', '品項', '大小', '加料', '甜度', '冰塊', '價格', '備註']
    final_cols = [c for c in cols_to_show if c in df.columns]
    
    # 準備表格資料
    data = [final_cols] + df[final_cols].astype(str).values.tolist()
    
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

# 上傳 Google Drive
def upload_to_drive(pdf_bytes, filename, s_info):
    try:
        # 1. 檢查 Folder ID (增強版：支援多種 Secrets 位置)
        # 優先找全域設定
        folder_id = st.secrets.get("drive_folder_id")
        
        # 其次找 [drive] 區塊
        if not folder_id:
            folder_id = st.secrets.get("drive", {}).get("folder_id")
            
        # 最後找看看是不是不小心貼在 [connections.gsheets] (即 s_info) 裡面了
        if not folder_id and isinstance(s_info, dict):
            folder_id = s_info.get("drive_folder_id")
            
        if not folder_id:
            st.error("❌ 上傳失敗：未設定 `drive_folder_id`。請去 Streamlit Cloud 的 Secrets 補上資料夾 ID。")
            return None

        # 2. 重建憑證
        private_key = s_info["private_key"].replace("\\n", "\n")
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
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        
        # 3. 建立 Drive Service
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id] 
        }
        
        media = MediaIoBaseUpload(pdf_bytes, mimetype='application/pdf', resumable=True)
        
        # 4. 執行上傳 (supportsAllDrives=True 支援共用雲端硬碟)
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        error_str = str(e)
        if "storageQuotaExceeded" in error_str:
            st.error("❌ 上傳失敗：機器人無儲存空間，請確認資料夾ID正確並已共用(編輯者)。")
        elif "File not found" in error_str:
            st.error(f"❌ 上傳失敗：找不到資料夾 ID `{folder_id}`。請確認 ID 正確且機器人有權限。")
        else:
            st.error(f"上傳 Google Drive 失敗: {e}")
        return None

# ==========================================
# 4. 主程式邏輯 (Main UI)
# ==========================================

# 4-1. 初始化與載入資料
client, s_info = get_google_sheet_data()
sheet_url = s_info.get("spreadsheet")

current_menus = DEFAULT_MENUS
all_toppings = {}

if sheet_url:
    menus, err = load_menu_from_sheet(client, sheet_url)
    if menus: current_menus = menus
    else: st.sidebar.warning(f"⚠️ 菜單讀取：{err}")
    
    all_toppings = load_toppings_from_sheet(client, sheet_url)
else:
    st.error("❌ 請在 Secrets 設定 Spreadsheet 網址")
    st.stop()

# 4-2. 側邊欄設定
st.sidebar.title("🥤 點餐設定")
selected_store = st.sidebar.selectbox("請選擇店家", list(current_menus.keys()))
menu_items = current_menus[selected_store]
store_toppings = all_toppings.get(selected_store, {})

st.sidebar.divider()
st.sidebar.header("功能選單")
admin_mode = st.sidebar.checkbox("開啟管理員/結算專區")

# 4-3. 使用者點餐區
st.header(f"📍 目前店家：{selected_store}")

col1, col2 = st.columns(2)
with col1:
    user_name = st.text_input("你的名字 (必填)", key="u_name")
with col2:
    item_name = st.selectbox("飲料品項", list(menu_items.keys()), key="u_item")
    price_table = menu_items[item_name]

col3, col4, col5 = st.columns(3)
with col3:
    size = st.selectbox("大小", list(price_table.keys()), key="u_size")
    base_price = price_table[size]
with col4:
    sugar = st.selectbox("甜度", SUGAR_OPTS, key="u_sugar")
with col5:
    ice = st.selectbox("冰塊", ICE_OPTS, key="u_ice")

# 加料區
topping_cost = 0
selected_toppings = []
if store_toppings:
    st.write("---")
    st.subheader("🍬 加料區")
    top_opts = [f"{k} (+{v})" for k, v in store_toppings.items()]
    picked_tops = st.multiselect("選擇配料", top_opts, key="u_top")
    
    for pt in picked_tops:
        tn = pt.split(" (+")[0]
        tp = store_toppings[tn]
        topping_cost += tp
        selected_toppings.append(tn)

final_price = base_price + topping_cost
st.write("---")
st.info(f"💰 **總金額：{final_price} 元** (飲料 {base_price} + 加料 {topping_cost})")
user_note = st.text_input("備註", key="u_note")

if st.button("送出訂單", type="primary", use_container_width=True):
    if not user_name:
        st.error("❌ 請輸入名字！")
    else:
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            t_str = ", ".join(selected_toppings)
            
            # 欄位順序：時間, 店家, 姓名, 品項, 大小, 加料, 價格, 甜度, 冰塊, 備註
            row = [ts, selected_store, user_name, item_name, size, t_str, final_price, sugar, ice, user_note]
            
            sh = client.open_by_url(sheet_url)
            ws = sh.get_worksheet(0)
            ws.append_row(row)
            
            get_orders_from_sheet.clear() # 清快取
            st.success(f"✅ {user_name} 點餐成功！")
            st.balloons()
        except Exception as e:
            st.error(f"寫入失敗: {e}")

# ==========================================
# 5. 管理員專區 (Admin UI)
# ==========================================
if admin_mode:
    st.divider()
    st.header("👮‍♂️ 管理員專區")
    
    # 讀取訂單
    raw_data = get_orders_from_sheet(client, sheet_url)
    
    if len(raw_data) > 1:
        headers = raw_data[0]
        # 過濾空白標題
        valid_idx = [i for i, h in enumerate(headers) if h.strip()]
        if not valid_idx:
            st.error("無法讀取訂單標題，請檢查 Google Sheet")
        else:
            clean_headers = [headers[i] for i in valid_idx]
            clean_rows = [[r[i] if i < len(r) else "" for i in valid_idx] for r in raw_data[1:]]
            
            df = pd.DataFrame(clean_rows, columns=clean_headers)
            
            # 確保價格為數字
            for col in ['價格', 'Price']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            total_amount = df['價格'].sum() if '價格' in df.columns else 0
            st.metric("💵 今日總營業額", f"{int(total_amount)} 元")

            # --- A. 訂單編輯區 ---
            st.subheader("✏️ 訂單管理")
            st.caption("勾選「刪除」可移除訂單；修改內容後請按「儲存變更」，系統將自動重新計算價格。")
            
            # 準備下拉選單資料
            all_stores = list(current_menus.keys())
            all_items = set()
            for m in current_menus.values(): all_items.update(m.keys())
            all_items = sorted(list(all_items))
            all_sizes = ["中杯", "大杯", "單一規格", "L", "M"]

            # 插入刪除欄位
            df_edit = df.copy()
            df_edit.insert(0, "刪除", False)

            edited_df = st.data_editor(
                df_edit,
                num_rows="dynamic",
                use_container_width=True,
                key="order_editor",
                column_config={
                    "刪除": st.column_config.CheckboxColumn("刪除", width="small"),
                    "店家": st.column_config.SelectboxColumn("店家", options=all_stores, required=True),
                    "品項": st.column_config.SelectboxColumn("品項", options=all_items, required=True),
                    "大小": st.column_config.SelectboxColumn("大小", options=all_sizes, required=True),
                    "甜度": st.column_config.SelectboxColumn("甜度", options=SUGAR_OPTS, required=True),
                    "冰塊": st.column_config.SelectboxColumn("冰塊", options=ICE_OPTS, required=True),
                    "價格": st.column_config.NumberColumn("價格", min_value=0, step=1)
                }
            )

            if st.button("💾 儲存訂單變更 (Save Changes)"):
                try:
                    # 過濾刪除
                    rows_to_save = edited_df[edited_df["刪除"] == False].drop(columns=["刪除"])
                    
                    # 自動重算價格
                    for idx, row in rows_to_save.iterrows():
                        try:
                            r_store, r_item, r_size = row.get('店家'), row.get('品項'), row.get('大小')
                            r_tops = str(row.get('加料', ""))
                            
                            # 基底價格
                            base = 0
                            if r_store in current_menus and r_item in current_menus[r_store]:
                                sizes = current_menus[r_store][r_item]
                                base = sizes.get(r_size, sizes.get("單一規格", 0))
                            
                            # 加料價格
                            top_c = 0
                            if r_tops and r_store in all_toppings:
                                for t in r_tops.split(","):
                                    t = t.strip()
                                    if t in all_toppings[r_store]: top_c += all_toppings[r_store][t]
                            
                            new_p = base + top_c
                            if new_p > 0: rows_to_save.at[idx, '價格'] = new_p
                        except: pass
                    
                    # 寫回 Sheet
                    new_headers = rows_to_save.columns.tolist()
                    new_vals = rows_to_save.astype(str).values.tolist()
                    
                    sh = client.open_by_url(sheet_url)
                    ws = sh.get_worksheet(0)
                    ws.clear()
                    ws.update(values=[new_headers] + new_vals)
                    
                    get_orders_from_sheet.clear()
                    st.success("✅ 訂單更新成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"儲存失敗: {e}")

            # --- B. 餘額扣款與結算 ---
            st.divider()
            st.subheader("💰 餘額扣款與結算")
            
            balances = load_balances_from_sheet(client, sheet_url)
            
            if balances is None:
                st.warning("請先建立「會員儲值」分頁以使用扣款功能")
            elif '姓名' in df.columns and '價格' in df.columns:
                # 計算每人消費
                spending = df.groupby('姓名')['價格'].sum().reset_index()
                spending.columns = ['姓名', '今日消費']
                
                # 準備結算預覽表
                report_data = []
                for _, row in spending.iterrows():
                    name = row['姓名']
                    cost = int(row['今日消費'])
                    curr = balances.get(name, 0)
                    remain = curr - cost
                    status = "✅ 足夠" if remain >= 0 else "❌ 不足"
                    report_data.append({
                        "姓名": name, "目前存款": curr, "今日消費": cost, 
                        "扣款後餘額": remain, "狀態": status
                    })
                
                if report_data:
                    bal_df = pd.DataFrame(report_data)
                    st.caption("👇 請確認「扣款後餘額」，按下確認鍵將執行：更新餘額、寫Log、產PDF、上傳雲端、清空訂單。")
                    
                    edited_bal_df = st.data_editor(
                        bal_df,
                        use_container_width=True,
                        disabled=["姓名", "目前存款", "今日消費", "狀態"],
                        column_config={
                            "扣款後餘額": st.column_config.NumberColumn("扣款後餘額 (可編輯)", required=True, step=1)
                        }
                    )
                    
                    if st.button("💸 確認扣款並更新儲值表 (End of Day)", type="primary"):
                        status_box = st.empty()
                        status_box.info("⏳ 正在處理結算流程...")
                        
                        try:
                            sh = client.open_by_url(sheet_url)
                            ws_bal = sh.worksheet("會員儲值")
                            
                            # 1. 準備更新資料
                            update_map = {r['姓名']: r['扣款後餘額'] for _, r in edited_bal_df.iterrows()}
                            logs = []
                            for _, r in edited_bal_df.iterrows():
                                diff = r['扣款後餘額'] - r['目前存款']
                                if diff != 0:
                                    logs.append({"name": r['姓名'], "change": diff, "bal": r['扣款後餘額'], "note": f"消費 {r['今日消費']}"})
                            
                            # 2. 更新儲值表 (保留原順序，新增新人)
                            bal_rows = ws_bal.get_all_values()
                            if not bal_rows: bal_rows = [["姓名", "存款餘額"]]
                            
                            h_bal = bal_rows[0]
                            try:
                                i_n = -1
                                for k in ["姓名", "Name", "員工", "員工姓名"]: 
                                    if k in h_bal: i_n = h_bal.index(k)
                                i_b = -1
                                for k in ["存款餘額", "餘額", "存款", "Balance", "金額", "目前餘額"]: 
                                    if k in h_bal: i_b = h_bal.index(k)
                            except: i_n, i_b = -1, -1
                            
                            if i_n != -1 and i_b != -1:
                                updated_names = set()
                                for i in range(1, len(bal_rows)):
                                    r = bal_rows[i]
                                    if len(r) > i_n:
                                        nm = r[i_n].strip()
                                        if nm in update_map:
                                            while len(r) <= i_b: r.append("")
                                            r[i_b] = str(update_map[nm])
                                            updated_names.add(nm)
                                
                                for nm, val in update_map.items():
                                    if nm not in updated_names:
                                        nr = [""] * (max(i_n, i_b) + 1)
                                        nr[i_n], nr[i_b] = nm, str(val)
                                        bal_rows.append(nr)
                                
                                ws_bal.clear()
                                ws_bal.update(values=bal_rows)
                                
                                # 3. 寫Log
                                for l in logs:
                                    log_transaction(client, sheet_url, l["name"], l["change"], l["bal"], l["note"])
                                
                                # 4. PDF & Drive
                                status_box.info("⏳ 上傳報表中...")
                                pdf = generate_pdf_report(df, int(total_amount))
                                fname = f"飲料結算_{datetime.now().strftime('%Y%m%d')}.pdf"
                                link = upload_to_drive(pdf, fname, s_info)
                                
                                # 5. 清空訂單
                                status_box.info("⏳ 清空訂單中...")
                                ws_ord = sh.get_worksheet(0)
                                ws_ord.clear()
                                ws_ord.append_row(['時間', '店家', '姓名', '品項', '大小', '加料', '價格', '甜度', '冰塊', '備註'])
                                
                                load_balances_from_sheet.clear()
                                get_orders_from_sheet.clear()
                                
                                msg = f"✅ 結算完成！[PDF 下載]({link})" if link else "✅ 結算完成！(PDF 上傳失敗)"
                                status_box.markdown(msg)
                                if st.button("🔄 重新載入"): st.rerun()
                            else:
                                st.error("儲值表欄位辨識失敗")
                        except Exception as e:
                            st.error(f"結算失敗: {e}")
                else:
                    st.info("今日無訂單需扣款")

            # --- C. 檢視所有餘額 ---
            with st.expander("📋 查看所有人員儲值餘額"):
                if balances:
                    b_data = [{"姓名": k, "存款餘額": v} for k, v in balances.items()]
                    st.dataframe(pd.DataFrame(b_data).sort_values("存款餘額"), use_container_width=True)
                else:
                    st.write("無資料")

    else:
        st.info("📭 目前訂單列表是空的")

# ==========================================
# 6. 訂單列表 (Footer)
# ==========================================
st.divider()
st.subheader("📊 今日訂單列表")
data_disp = get_orders_from_sheet(client, sheet_url)
if len(data_disp) > 1:
    h = data_disp[0]
    r = data_disp[1:]
    v_idx = [i for i, x in enumerate(h) if x.strip()]
    if v_idx:
        c_h = [h[i] for i in v_idx]
        c_r = [[row[i] if i < len(row) else "" for i in v_idx] for row in r]
        st.dataframe(pd.DataFrame(c_r, columns=c_h), use_container_width=True)
else:
    st.info("尚無訂單")
