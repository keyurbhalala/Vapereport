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

st.set_page_config(page_title="🧪 Combined Product Tools", layout="wide")
# --- Login Block ---
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
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    login()
else:
    st.title("🧰 Product Utility Suite")


# --- Sidebar Navigation ---
    app_choice = st.sidebar.radio("Choose Tool", [
        "🔁 Vape & Smoking Report",
        "📦 E-Liquid Report",
        "🔮 Product Run-Out Forecaster"
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
    
    # --- Router ---
    def runout_forecaster():
        st.set_page_config(page_title="🔮 Forecast Wizard", layout="wide", page_icon="📦")
        st.title("📦 Product Run-Out Forecaster(12 Weeks sold Avg)")
        
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
        
            df1_trimmed[brand_col] = (
                df1[brand_col]
                .astype(str)
                .str.encode('ascii', 'ignore')  # Remove weird unicode
                .str.decode('utf-8')
                .str.strip()
                .str.replace(r'\s+', ' ', regex=True)
            )

            # ✅ Auto-detect Supplier column
            supplier_col = None
            for col in df1.columns:
                if col.strip().lower() == "supplier":
                    supplier_col = col
                    break
            if not supplier_col:
                st.error("❌ 'Supplier' column not found in your sales sheet.")
                st.stop()
        
            df1_trimmed[supplier_col] = (
                df1[supplier_col]
                .astype(str)
                .str.encode('ascii', 'ignore')
                .str.decode('utf-8')
                .str.strip()
                .str.replace(r'\s+', ' ', regex=True)
            )

        
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
            # First, do full outer merge to catch everything
            merged_df = pd.merge(df1_trimmed, df2_trimmed, on="Product Name", how="outer")

            # Fill missing brand/supplier with blank strings after merge
            merged_df[brand_col] = merged_df[brand_col].fillna("").astype(str)
            merged_df[supplier_col] = merged_df[supplier_col].fillna("").astype(str)

            
            # Fill NA in numerical fields to 0 (to avoid NaN in calc)
            merged_df["Closing Inventory"] = pd.to_numeric(merged_df["Closing Inventory"], errors="coerce").fillna(0)
            merged_df[date_cols] = merged_df[date_cols].fillna(0)
            
            # Recalculate totals/averages for newly added inventory-only rows
            merged_df["Total Sold"] = merged_df[date_cols].sum(axis=1)
            merged_df["Avg Weekly Sold"] = merged_df[date_cols].mean(axis=1)
            
            # ✅ Filter out rows that are only from inventory and have 0 stock
            merged_df = merged_df[~((merged_df["Total Sold"] == 0) & (merged_df["Closing Inventory"] == 0))]

        
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
                        value = item.replace("[BRAND]", "").strip().lower()    
                        conditions = conditions | (merged_df[brand_col].str.lower() == value)
                    elif item.endswith("[SUPPLIER]"):
                        value = item.replace("[SUPPLIER]", "").strip().lower()
                        conditions = conditions | (merged_df[supplier_col].str.lower() == value)


        
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
    
    # --- Router ---
    if app_choice == "🔁 Vape & Smoking Report":
        description_finder()
    elif app_choice == "📦 E-Liquid Report":
        inventory_matcher()
    elif app_choice == "🔮 Product Run-Out Forecaster":
        runout_forecaster()

