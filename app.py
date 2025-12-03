if report_data:
                            balance_df = pd.DataFrame(report_data)
                            
                            st.caption("👇 您可以直接修改「扣款後餘額」，確認無誤後請按下方按鈕更新回 Google Sheet。")
                            
                            edited_balance_df = st.data_editor(
                                balance_df, 
                                use_container_width=True,
                                key="balance_editor",
                                disabled=["姓名", "目前存款", "今日消費", "狀態"], # 鎖定這些欄位不讓改
                                column_config={
                                    "扣款後餘額": st.column_config.NumberColumn(
                                        "扣款後餘額 (可編輯)",
                                        help="修改此數值將會更新到儲值表",
                                        required=True,
                                        step=1
                                    ),
                                    "狀態": st.column_config.TextColumn(
                                        "狀態",
                                        width="small"
                                    )
                                }
                            )
                            
                            if st.button("💸 確認扣款並更新儲值表 (Update Deposit)", type="primary"):
                                try:
                                    # 1. 準備要更新的資料對應表 {姓名: 新餘額}
                                    update_map = {}
                                    for index, row in edited_balance_df.iterrows():
                                        update_map[row['姓名']] = row['扣款後餘額']
                                    
                                    # 2. 讀取目前的儲值表
                                    spreadsheet = client.open_by_url(sheet_url)
                                    try:
                                        wks_balance = spreadsheet.worksheet("會員儲值")
                                    except gspread.WorksheetNotFound:
                                        st.error("找不到「會員儲值」分頁，無法更新。")
                                        st.stop()
                                    
                                    # 3. 讀取所有資料並更新
                                    all_rows = wks_balance.get_all_values()
                                    
                                    if len(all_rows) < 1:
                                        # 如果是空的，建立標題
                                        all_rows = [["姓名", "存款餘額"]]
                                        
                                    headers = all_rows[0]
                                    
                                    # 尋找欄位索引
                                    def find_col(keywords):
                                        for k in keywords:
                                            if k in headers: return headers.index(k)
                                        return -1
                                    
                                    idx_name = find_col(["姓名", "Name", "員工"])
                                    idx_val = find_col(["存款餘額", "餘額", "存款", "Balance"])
                                    
                                    if idx_name == -1 or idx_val == -1:
                                        st.error("儲值表欄位辨識失敗，請確認有「姓名」與「存款餘額」欄位。")
                                    else:
                                        # 更新現有使用者
                                        updated_names = set()
                                        new_rows_data = []
                                        
                                        # 遍歷現有資料列 (跳過標題)
                                        for i in range(1, len(all_rows)):
                                            row = all_rows[i]
                                            if len(row) > idx_name:
                                                r_name = row[idx_name].strip()
                                                if r_name in update_map:
                                                    # 更新餘額
                                                    # 確保 row 長度足夠
                                                    while len(row) <= idx_val:
                                                        row.append("")
                                                    row[idx_val] = str(update_map[r_name])
                                                    updated_names.add(r_name)
                                        
                                        # 處理新使用者 (在訂單中有，但儲值表中沒有)
                                        for name, bal in update_map.items():
                                            if name not in updated_names:
                                                new_row = [""] * (max(idx_name, idx_val) + 1)
                                                new_row[idx_name] = name
                                                new_row[idx_val] = str(bal)
                                                all_rows.append(new_row)
                                        
                                        # 4. 寫回 Google Sheet
                                        wks_balance.clear()
                                        wks_balance.update(values=all_rows)
                                        
                                        # 清除快取，讓下次讀取能抓到最新餘額
                                        load_balances_from_sheet.clear()
                                        
                                        st.success("✅ 儲值表餘額已更新完成！")
                                        st.rerun()
                                        
                                except Exception as e:
                                    st.error(f"更新失敗：{e}")

                        else:
                            st.caption("今日尚未有訂單，無法計算扣款。")
                    
                    st.write("---")
