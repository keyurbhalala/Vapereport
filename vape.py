import streamlit as st
import pandas as pd
import re
import os
import datetime
import requests
import tempfile
import io
from io import BytesIO
from rapidfuzz import process, fuzz
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="🧪 Combined Product Tools", layout="wide")
# --- Login Block ---
def log_login_attempt(username, status):
    # Google Sheets setup
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(credentials)
    
    SHEET_ID = "1FT1sWAEDCLGL4sWXNA1ap12a8cvCvtdmVGLuAz4OrS0"
    sheet = client.open_by_key(SHEET_ID).sheet1


    # Log attempt
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([timestamp, username, status])

def login():
    st.title("🔐 Login Required")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("🔓 Login")

    if submit:
        valid_users = st.secrets["users"]

        if username in valid_users and password == valid_users[username]:
            st.session_state["logged_in"] = True
            log_login_attempt(username, "Success")
            st.rerun()
        else:
            log_login_attempt(username, "Failed")
            st.error("❌ Invalid username or password")

if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
    st.title("🧰 Product Utility Suite")


# --- Sidebar Navigation ---
    app_choice = st.sidebar.radio("Choose Tool", [
        "🔁 Vape & Smoking Report",
        "📦 E-Liquid Report",
        "🔮 Product Run-Out Forecaster",
        "Product Merge Tool",
        "Stock Rotation Advisor"
    ])

    # 🚪 Logout Button
    if st.sidebar.button("🚪 Logout"):
        st.session_state["logged_in"] = False
        st.rerun()

    # --- App 1 ---
    def description_finder():
        st.header("Vape Smoking Report")
    
        file1 = st.file_uploader("Upload File 1 (WMS Full Inventory From stock Report Excle file)", type=["xlsx"], key="file1")
        file2 = st.file_uploader("Upload File 2 (Shortlisted Products)", type=["xlsx"], key="file2")
    
        if file1 and file2:
            # Read files without headers
            df_full = pd.read_excel(file1, header=None)
            df_shortlist = pd.read_excel(file2, header=None)
    
            try:
                # Rename columns explicitly
                df_full.columns = ['Description', 'Avail. Stock']
                df_shortlist.columns = ['Description']
    
                # Merge using exact match on Description
                df_result = pd.merge(
                    df_shortlist,
                    df_full,
                    on='Description',
                    how='left'
                )
    
                # Rename column for clarity
                df_result.rename(columns={'Avail. Stock': 'Matched Avail. Stock'}, inplace=True)
    
                st.success("✅ Exact match completed!")
                st.dataframe(df_result)
    
                # Excel download preparation
                def to_excel_download(df):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False)
                    return output.getvalue()
    
                st.download_button(
                    label="📥 Download Result as Excel",
                    data=to_excel_download(df_result),
                    file_name="matched_stock_exact.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
            except Exception as e:
                st.error(f"❌ Error processing files: {e}")
    
    
    # --- App 2 ---
    def inventory_matcher():
        st.header("📦 Product Strength-wise Inventory Matcher")
    
        file_full = st.file_uploader("Upload Full Inventory File (Excel or CSV) From Vend", type=["xlsx", "csv"], key="full")
        file_subset = st.file_uploader("Upload Selected Product List (Excel or CSV)", type=["xlsx", "csv"], key="subset")
    
        valid_strengths = ["20mg", "40mg", "50mg"]
    
        def read_file(file):
            return pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    
        def normalize_name(name):
            name = str(name).lower()
            name = re.sub(r"\b(0|10|20|25|30|35|40|45|50|60|70|80|90|100) ?mg\b", "", name)
            name = re.sub(r"[^a-z0-9]+", " ", name).strip()
            return name
    
        def extract_strength(name):
            match = re.search(r"\b(20|40|50) ?mg\b", str(name).lower())
            return f"{match.group(1)}mg" if match else None
    
        def match_and_gather_variants(df_full, df_subset):
            df_full["NormName"] = df_full["SKU Name"].apply(normalize_name)
            df_full["Strength"] = df_full["SKU Name"].apply(extract_strength)
    
            results = []
            for prod in df_subset["SKU Name"]:
                norm = normalize_name(prod)
                match_result = process.extractOne(norm, df_full["NormName"], scorer=fuzz.token_sort_ratio)
                if match_result:
                    match_name, score, _ = match_result
                    if score >= 85:
                        matched_rows = df_full[df_full["NormName"] == match_name]
                        matched_rows = matched_rows[matched_rows["Strength"].isin(valid_strengths)]
                        matched_rows["Matched Product"] = prod
                        results.append(matched_rows)
    
            if results:
                final_df = pd.concat(results)
                final_df["Strength"] = pd.Categorical(final_df["Strength"], categories=valid_strengths, ordered=True)
                pivot_df = (
                    final_df.pivot_table(
                        index="Matched Product",
                        columns="Strength",
                        values="Closing Inventory",
                        aggfunc="sum",
                        fill_value=0
                    ).reindex(df_subset["SKU Name"]).reset_index()
                )
            else:
                final_df = pd.DataFrame()
                pivot_df = pd.DataFrame()
    
            return final_df, pivot_df
    
        if file_full and file_subset:
            df_full = read_file(file_full)
            df_subset = read_file(file_subset)
    
            if "SKU Name" not in df_full.columns or "SKU Name" not in df_subset.columns:
                st.error("Both files must have a 'SKU Name' column.")
                return
    
            matched_df, pivot_df = match_and_gather_variants(df_full, df_subset)
    
            st.subheader("🧾 Matched Inventory (Detailed)")
            st.dataframe(matched_df)
    
            st.subheader("📊 Strength-wise Pivot Table")
            st.dataframe(pivot_df)
    
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                matched_df.to_excel(writer, index=False, sheet_name="Matched_Inventory")
                pivot_df.to_excel(writer, index=False, sheet_name="Pivot_Summary")
            st.download_button("📥 Download Excel", data=output.getvalue(), file_name="matched_inventory.xlsx")
    
    # --- app 3 ---
    def runout_forecaster():
        st.set_page_config(page_title="🔮 Forecast Wizard", layout="wide", page_icon="📦")
        st.title("📦 Product Run-Out Forecaster")
        
        # ✅ Google Drive Direct Links
        SALES_FILE_LINK = "https://docs.google.com/spreadsheets/d/1oHWG7i0V08YQPHKARbdXjT_fbEFrmMg51LYtqZbDeag/export?format=csv"
        INVENTORY_FILE_LINK = "https://docs.google.com/spreadsheets/d/1xODr-YC8ej_5HNmoR7f9qTO7mnMOFAAwO6Kf-voBpY8/export?format=csv"
        
        def download_csv(url):
            """Download CSV file from Google Drive."""
            response = requests.get(url)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                    tmp_file.write(response.content)
                    return tmp_file.name
            else:
                raise Exception(f"Failed to download file from: {url}")
        
        try:
            # Download files from Google Drive
            sales_path = download_csv(SALES_FILE_LINK)
            inventory_path = download_csv(INVENTORY_FILE_LINK)
        
            # ✅ Read CSV & auto-remove commas
            df1 = pd.read_csv(sales_path, thousands=",")
            df2 = pd.read_csv(inventory_path, thousands=",")
        
            # Normalize columns
            df1.columns = df1.columns.astype(str)
            df2.columns = df2.columns.astype(str)
        
            # ✅ Always use 1st column as Product Name, 2nd as SKU/Product Code
            date_cols = [col for col in df1.columns if re.match(r"\d{1,2}(st|nd|rd|th)?\s+\w+\s+\d{4}", str(col))]
            if not date_cols:
                st.error("❌ No valid weekly date columns found in the sales file.")
                st.stop()
        
            product_col = df1.columns[0]
            sku_col = df1.columns[1]
        
            df1_trimmed = df1[[product_col, sku_col] + date_cols].copy()
            df1_trimmed.rename(columns={product_col: "Product Name", sku_col: "Product Code"}, inplace=True)
            df1_trimmed["Product Name"] = df1_trimmed["Product Name"].str.strip()
            df1_trimmed["Product Code"] = df1_trimmed["Product Code"].astype(str).str.strip()
        
            # ✅ Auto-detect Brand column
            brand_col = None
            for col in df1.columns:
                if "brand" in col.lower():
                    brand_col = col
                    break
            if not brand_col:
                st.error("❌ 'Brand' column not found in your sales sheet.")
                st.stop()
        
            df1_trimmed[brand_col] = df1[brand_col].astype(str).str.strip()
        
            # ✅ Auto-detect Supplier column
            supplier_col = None
            for col in df1.columns:
                if col.strip().lower() == "supplier":
                    supplier_col = col
                    break
            
            if not supplier_col:
                st.error("❌ 'Supplier' column not found in your sales sheet.")
                st.stop()

        
            df1_trimmed[supplier_col] = df1[supplier_col].astype(str).str.strip()
        
        
            # ✅ Ensure all date columns are numeric
            for col in date_cols:
                df1_trimmed[col] = pd.to_numeric(df1_trimmed[col], errors="coerce")
        
            # ✅ Rename first column of inventory file to "Product Name" for merging
            df2.rename(columns={df2.columns[0]: "Product Name"}, inplace=True)
            df2_trimmed = df2[["Product Name", "Closing Inventory"]].copy()
        
            # Calculate totals & averages
            df1_trimmed["Total Sold"] = df1_trimmed[date_cols].sum(axis=1)
            df1_trimmed["Avg Weekly Sold"] = df1_trimmed[date_cols].mean(axis=1)
        
            # Parse last date column header
            last_col_header = date_cols[-1]
            cleaned_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', last_col_header.strip())
            last_date = datetime.datetime.strptime(cleaned_date, "%d %b %Y")
        
            # Merge with inventory
            merged_df = pd.merge(df1_trimmed, df2_trimmed, on="Product Name", how="left")
        
            # Forecast calculations
            merged_df["Weeks Remaining"] = merged_df.apply(
                lambda row: round(row["Closing Inventory"] / row["Avg Weekly Sold"], 1)
                if row["Avg Weekly Sold"] > 0 else float('nan'),
                axis=1
            )
            merged_df["Estimated Run-Out Date"] = merged_df["Weeks Remaining"].apply(
                lambda w: (last_date + datetime.timedelta(weeks=w)) if pd.notna(w) else None
            )
            merged_df["Estimated Run-Out Date"] = merged_df["Estimated Run-Out Date"].apply(
                lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else ""
            )
            merged_df["Status"] = merged_df["Closing Inventory"].apply(
                lambda x: "❌ Out of Stock" if x <= 0 else "✅ In Stock"
            )
        
            st.success("✅ Forecast Completed Successfully!")
        
            # ✅ Inject CSS for Wide & Deep Table
            st.markdown("""
                <style>
                .stDataFrame {
                    height: 800px !important;
                }
                .stDataFrame div[data-testid="stVerticalBlock"] {
                    max-width: none;
                }
                .stDataFrame table {
                    font-size: 16px !important;
                }
                </style>
            """, unsafe_allow_html=True)
        
            # ✅ Tagged Multi-Select Search Bar
            suggestions = []
        
            # Add suggestions from Product Name, SKU, Brand (tagged)
            for name in merged_df["Product Name"].dropna().unique():
                suggestions.append(f"{name} [PRODUCT NAME]")
            for code in merged_df["Product Code"].dropna().unique():
                suggestions.append(f"{code} [PRODUCT CODE]")
            for brand in merged_df[brand_col].dropna().unique():
                suggestions.append(f"{brand} [BRAND]")
            for supplier in merged_df[supplier_col].dropna().unique():
                suggestions.append(f"{supplier} [SUPPLIER]")
        
        
            selected_items = st.multiselect("🔎 Select Product(s) by Name, Code, or Brand:", sorted(list(set(suggestions))))
        
            if selected_items:
                conditions = pd.Series(False, index=merged_df.index)
                for item in selected_items:
                    if item.endswith("[PRODUCT NAME]"):
                        value = item.replace("[PRODUCT NAME]", "").strip()
                        conditions = conditions | (merged_df["Product Name"] == value)
                    elif item.endswith("[PRODUCT CODE]"):
                        value = item.replace("[PRODUCT CODE]", "").strip()
                        conditions = conditions | (merged_df["Product Code"] == value)
                    elif item.endswith("[BRAND]"):
                        value = item.replace("[BRAND]", "").strip()
                        conditions = conditions | (merged_df[brand_col] == value)
                    elif item.endswith("[SUPPLIER]"):
                        value = item.replace("[SUPPLIER]", "").strip()
                        conditions = conditions | (merged_df[supplier_col] == value)
        
        
                filtered_df = merged_df[conditions]
                st.success(f"✅ Found {filtered_df.shape[0]} matching product(s):")
                st.dataframe(
                    filtered_df[[
                        "Product Name", "Product Code", brand_col, supplier_col,
                        "Closing Inventory", "Avg Weekly Sold",
                        "Weeks Remaining", "Estimated Run-Out Date", "Status"
                    ]],
                    use_container_width=True,
                    height=800,
                )
            else:
                st.info("ℹ️ Select products from the dropdown above to filter.")
        
        except Exception as e:
            st.error(f"❌ Error: {e}")
    # --- App 4 ---
    def Product_Merge_Tool():
        st.set_page_config(page_title="Product Merge Tool", page_icon="📦", layout="centered")
        st.title("📦 Merge Received Quantities from Multiple Files")
        
        uploaded_files = st.file_uploader(
            "Upload your files (Excel/CSV)", type=["csv", "xlsx"], accept_multiple_files=True
        )
        
        if uploaded_files:
            dfs = []
            for file in uploaded_files:
                try:
                    # Try Excel, then CSV
                    try:
                        df = pd.read_excel(file)
                    except Exception:
                        file.seek(0)
                        df = pd.read_csv(file)
                    # Only keep relevant columns
                    if all(col in df.columns for col in ['product', 'sku', 'quantity']):
                        df = df[['product', 'sku', 'quantity']]
                        dfs.append(df)
                    else:
                        st.warning(f"File {file.name} skipped: missing 'product', 'sku', or 'quantity' column.")
                except Exception as e:
                    st.error(f"File {file.name} could not be read. {e}")
        
            if dfs:
                all_data = pd.concat(dfs, ignore_index=True)
                # Group by product & sku, sum received
                all_data_grouped = all_data.groupby(['product', 'sku'], as_index=False)['quantity'].sum()
                all_data_grouped = all_data_grouped[all_data_grouped['quantity'] != 0]
                st.success("Merged Table")
                st.dataframe(all_data_grouped, use_container_width=True)
        
                # Download merged data as Excel
                output = io.BytesIO()
                all_data_grouped.to_excel(output, index=False)
                st.download_button(
                    "Download Merged File (Excel)",
                    output.getvalue(),
                    file_name="merged_products_with_sku.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("No valid files found!")
        else:
            st.info("Please upload one or more Excel/CSV files.")
    # --- App 5 ---
    def Stock_Rotation_Advisor():
        # ------------------- PAGE CONFIG -------------------
        st.set_page_config(page_title="Stock Rotation Advisor", layout="wide")
        st.title("🛒 Stock Rotation Advisor (Island & Group Prioritization)")
        
        # ------------------- DATA LOADING HELPERS -------------------
        def load_excel_from_github(url):
            response = requests.get(url)
            response.raise_for_status()
            return pd.read_excel(BytesIO(response.content))
        # --- Always load mapping files from GitHub ---
        store_to_group_url = "https://github.com/keyurbhalala/Vapereport/blob/main/store_to_group.xlsx"
        group_to_island_url = "https://github.com/keyurbhalala/Vapereport/blob/main/group_to_island.xlsx"
        
        
        
        store_to_group_df = load_excel_from_url(store_to_group_url)
        group_to_island_df = load_excel_from_url(group_to_island_url)
        
        def build_outlet_to_group_and_island(store_to_group_df, group_to_island_df):
            outlet_to_group = dict(zip(store_to_group_df['Store Name'], store_to_group_df['Group Name']))
            group_to_island = dict(zip(group_to_island_df['Group Name'], group_to_island_df['Island']))
            outlet_to_group_and_island = {
                outlet: {
                    'group': outlet_to_group.get(outlet, ''),
                    'island': group_to_island.get(outlet_to_group.get(outlet, ''), '')
                }
                for outlet in outlet_to_group
            }
            return outlet_to_group, group_to_island, outlet_to_group_and_island
        
        def prioritize_sources(need_outlet, source_outlets, outlet_lookup):
            """Return sources sorted: same island+group > same island+other group > other island"""
            need_info = outlet_lookup.get(need_outlet, {})
            need_group = need_info.get('group', '')
            need_island = need_info.get('island', '')
            tier1, tier2, tier3 = [], [], []
            for src in source_outlets:
                src_info = outlet_lookup.get(src, {})
                if src_info.get('island') == need_island:
                    if src_info.get('group') == need_group:
                        tier1.append(src)
                    else:
                        tier2.append(src)
                else:
                    tier3.append(src)
            return tier1 + tier2 + tier3
        
        # ------------------- MAIN LOGIC -------------------
        
        def stock_rotation_logic(df, warehouse_name="Warehouse", to_outlets=None, outlet_lookup=None):
            suggestions = []
        
            for sku in df["SKU"].unique():
                sku_df = df[df["SKU"] == sku].copy()
                needs_stock = sku_df[
                    (sku_df["Closing Inventory"] == 0) & (sku_df["Items Sold"] > 0)
                ]
                if to_outlets:
                    needs_stock = needs_stock[needs_stock["Outlet"].isin(to_outlets)]
        
                # Warehouse handling
                warehouse_row = sku_df[
                    (sku_df["Outlet"] == warehouse_name) & (sku_df["Closing Inventory"] > 0)
                ]
                warehouse_remaining = (
                    warehouse_row.iloc[0]["Closing Inventory"] if not warehouse_row.empty else 0
                )
        
                # Overstocked sources
                overstocked = sku_df[
                    (sku_df["Outlet"] != warehouse_name)
                    & (sku_df["Closing Inventory"] > 0)
                    & (sku_df["Items Sold"] == 0)
                ]
                overstocked_remaining = {
                    over["Outlet"]: over["Closing Inventory"] for _, over in overstocked.iterrows()
                }
        
                for _, need in needs_stock.iterrows():
                    qty_needed = need["Items Sold"]
        
                    # 1. Try warehouse
                    if warehouse_remaining > 0 and qty_needed > 0:
                        qty = min(warehouse_remaining, qty_needed)
                        suggestions.append({
                            "SKU": sku,
                            "Product": need["SKU Name"],
                            "From Outlet": warehouse_name,
                            "From Outlet Closing Inv": warehouse_remaining,
                            "To Outlet": need["Outlet"],
                            "To Outlet Closing Inv": need["Closing Inventory"],
                            "Qty to Transfer (suggested)": qty
                        })
                        warehouse_remaining -= qty
                        qty_needed -= qty
        
                    # 2. Prioritized overstocked sources
                    source_outlets = list(overstocked_remaining.keys())
                    if outlet_lookup:
                        prioritized_sources = prioritize_sources(need["Outlet"], source_outlets, outlet_lookup)
                    else:
                        prioritized_sources = source_outlets
        
                    for outlet_name in prioritized_sources:
                        available = overstocked_remaining[outlet_name]
                        if qty_needed <= 0 or available <= 0:
                            continue
                        qty = min(available, qty_needed)
                        suggestions.append({
                            "SKU": sku,
                            "Product": need["SKU Name"],
                            "From Outlet": outlet_name,
                            "From Outlet Closing Inv": available,
                            "To Outlet": need["Outlet"],
                            "To Outlet Closing Inv": need["Closing Inventory"],
                            "Qty to Transfer (suggested)": qty
                        })
                        overstocked_remaining[outlet_name] -= qty
                        qty_needed -= qty
                        if qty_needed <= 0:
                            break  # Stop when need is satisfied
        
            return pd.DataFrame(suggestions)
        
        # =============================================================
        # ========================== UI SECTION =======================
        # =============================================================
        
        # --------- 1. MAIN INVENTORY UPLOAD -----------
        file = st.file_uploader("Upload inventory CSV or Excel file", type=["csv", "xlsx"])
        # --------- 2. MAPPING FILES UPLOAD -----------
        st.sidebar.header("Upload Mapping Files")
        store_to_group_file = st.sidebar.file_uploader("Store to Group Mapping (Excel)", type=["xlsx"])
        group_to_island_file = st.sidebar.file_uploader("Group to Island Mapping (Excel)", type=["xlsx"])
        
        if file and store_to_group_file and group_to_island_file:
            # --- Load all files ---
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            df.columns = [c.strip() for c in df.columns]
        
            store_to_group_df = load_excel(store_to_group_file)
            group_to_island_df = load_excel(group_to_island_file)
        
            outlet_to_group, group_to_island, outlet_to_group_and_island = build_outlet_to_group_and_island(
                store_to_group_df, group_to_island_df)
        
            st.write("Raw Data", df)
        
            # FILTERS
            tags = df["Tag"].dropna().unique().tolist()
            brands = df["Brand"].dropna().unique().tolist()
            cats = df["Category"].dropna().unique().tolist()
            prod_names = df["SKU Name"].dropna().unique().tolist()
            skus = df["SKU"].dropna().unique().tolist()
            suppliers = df["Supplier"].dropna().unique().tolist()
            all_outlets = df["Outlet"].dropna().unique().tolist()
        
            with st.sidebar:
                st.header("Filter Products")
                sel_tags = st.multiselect("Tag", options=tags)
                sel_brands = st.multiselect("Brand", options=brands)
                sel_cats = st.multiselect("Category", options=cats)
                sel_prod = st.multiselect("Product Name", options=prod_names)
                sel_sku = st.multiselect("SKU", options=skus)
                sel_sup = st.multiselect("Supplier", options=suppliers)
                sel_to_outlets = st.multiselect(
                    "Limit suggestions to these destination outlets (To Outlet)",
                    options=all_outlets,
                    help="Leave empty to allow suggestions for all stores"
                )
                st.markdown("Filters are **ANDed** together.")
        
            # Apply filters
            def apply_filters(df, sel_tags, sel_brands, sel_cats, sel_prod, sel_sku, sel_sup):
                if sel_tags:
                    df = df[df["Tag"].isin(sel_tags)]
                if sel_brands:
                    df = df[df["Brand"].isin(sel_brands)]
                if sel_cats:
                    df = df[df["Category"].isin(sel_cats)]
                if sel_prod:
                    df = df[df["SKU Name"].isin(sel_prod)]
                if sel_sku:
                    df = df[df["SKU"].isin(sel_sku)]
                if sel_sup:
                    df = df[df["Supplier"].isin(sel_sup)]
                return df
        
            filtered = apply_filters(df, sel_tags, sel_brands, sel_cats, sel_prod, sel_sku, sel_sup)
            st.write("Filtered Data", filtered)
        
            if filtered.empty:
                st.warning("No data after filtering. Adjust your filter selections.")
            else:
                result_df = stock_rotation_logic(
                    filtered,
                    warehouse_name="Warehouse",
                    to_outlets=sel_to_outlets,
                    outlet_lookup=outlet_to_group_and_island
                )
                if result_df.empty:
                    st.info("No stock rotation suggestions found for the current filters and data.")
                else:
                    st.success(f"Found {len(result_df)} stock rotation suggestions.")
                    st.dataframe(result_df, use_container_width=True)
                    csv = result_df.to_csv(index=False)
                    st.download_button(
                        "Download Rotation Suggestions as CSV",
                        csv,
                        file_name="stock_rotation_suggestions.csv",
                        mime="text/csv"
                    )
        
            # Optional: Show mapping for verification
            with st.expander("🔍 Show unique SKU / SKU Name mapping (for verification)"):
                st.dataframe(df[["SKU", "SKU Name"]].drop_duplicates())
        
            with st.expander("🏷️ Store to Group/Island Mapping"):
                st.write(pd.DataFrame([
                    {"Store": o, "Group": outlet_to_group_and_island[o]['group'], "Island": outlet_to_group_and_island[o]['island']}
                    for o in outlet_to_group_and_island
                ]))
        
        else:
            st.info("Upload your inventory file **AND** both mapping Excel files to start.")
    # --- Router ---
    if app_choice == "🔁 Vape & Smoking Report":
        description_finder()
    elif app_choice == "📦 E-Liquid Report":
        inventory_matcher()
    elif app_choice == "🔮 Product Run-Out Forecaster":
        runout_forecaster()
    elif app_choice == "Product Merge Tool":
        Product_Merge_Tool()
    elif app_choice == "Stock Rotation Advisor":
        Stock_Rotation_Advisor()

