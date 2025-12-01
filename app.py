# ==========================================
# 5. 管理員結算專區
# ==========================================
st.sidebar.divider()
st.sidebar.header("👮‍♂️ 管理員專區")

if st.sidebar.checkbox("開啟結算功能"):
    st.divider()
    st.header("💰 結算管理")
    
    try:
        if s_info:
            sheet_url = s_info.get("spreadsheet")
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
                    
                    # --- 編輯區塊 (升級) ---
                    st.markdown("### ✏️ 訂單管理與編輯")
                    st.caption("您可以直接點擊表格修改內容，或選取左側方框刪除列。修改完請務必按下方「儲存變更」。")
                    
                    edited_df = st.data_editor(
                        df, 
                        num_rows="dynamic", # 允許新增或刪除列
                        use_container_width=True,
                        key="order_editor"
                    )
                    
                    if st.button("💾 儲存變更 (Save Changes)", type="primary"):
                        try:
                            # 準備寫入的資料
                            updated_headers = edited_df.columns.tolist()
                            updated_values = edited_df.astype(str).values.tolist() # 轉成字串確保相容性
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
                            get_orders_from_sheet.clear()
                            st.success("✅ 資料已清空，可以開始新的一天了！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"清空失敗：{e}")
            else:
                st.info("📭 目前是空的，沒有訂單。")
    except Exception as e:
        st.error(f"讀取資料失敗：{e}")
