# 讀取會員存款 (新增)
@st.cache_data(ttl=60)
def load_balances_from_sheet(_client, sheet_url):
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        try:
            worksheet = spreadsheet.worksheet("會員儲值")
        except gspread.WorksheetNotFound:
            return None # 代表沒有設定存款分頁
            
        # 改用 get_all_values 避免標題重複報錯
        rows = worksheet.get_all_values()
        if len(rows) < 2: return {}
        
        headers = [h.strip() for h in rows[0]]
        
        # 尋找欄位 (支援多種寫法)
        def get_col_index(possible_names):
            for name in possible_names:
                if name in headers:
                    return headers.index(name)
            return -1
            
        idx_name = get_col_index(["姓名", "Name", "員工", "員工姓名"])
        idx_balance = get_col_index(["存款餘額", "餘額", "存款", "Balance", "金額", "目前餘額"])
        
        if idx_name == -1 or idx_balance == -1:
            return {}

        balances = {}
        for row in rows[1:]:
            if len(row) <= max(idx_name, idx_balance): continue
            
            name = str(row[idx_name]).strip()
            # 清理金額格式 (去除 $ 和 ,)
            balance_str = str(row[idx_balance]).replace("$", "").replace(",", "").strip()
            
            if name:
                try:
                    balances[name] = int(float(balance_str))
                except:
                    balances[name] = 0
        return balances
    except Exception:
        return {}
