import streamlit as st
import pandas as pd
import re
import os
import datetime
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
        valid_users = {
            "admin": "nauticalB",
            "keyur": "supersecure"
        }

        if username in valid_users and password == valid_users[username]:
            st.session_state["logged_in"] = True
            st.experimental_rerun()
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
    # --- App 1 ---
    def description_finder():
        st.header("Vape Smoking Reprot")
    
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
        st.header("🔮 Product Run-Out Forecaster")
    
        st.markdown("""
        Upload two files:
        1. **Weekly Sales Report**: First column = Product Name, weekly sales start from column H with dates like `3rd Mar 2025`. Extra columns (like `Items Sold`) after weekly data will be ignored.
        2. **Current Stock Report**: Contains product name and a column titled **"Closing Inventory"**.
        """)
    
        file1 = st.file_uploader("📄 Upload Weekly Sales Report", type=["xlsx", "csv"], key="sales")
        file2 = st.file_uploader("📄 Upload Current Stock Report", type=["xlsx", "csv"], key="stock")
    
        def clean_date_string(date_str):
            return re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
    
        if file1 and file2 and st.button("🔍 Analyze Run-Out Dates"):
            try:
                if file1.name.endswith("csv"):
                    df1 = pd.read_csv(file1)
                else:
                    df1 = pd.read_excel(file1)
    
                if file2.name.endswith("csv"):
                    df2 = pd.read_csv(file2)
                else:
                    df2 = pd.read_excel(file2)
    
                df1.columns = df1.columns.astype(str)
                df2.columns = df2.columns.astype(str)
    
                date_cols = [col for col in df1.columns if re.match(r"\d{1,2}(st|nd|rd|th)?\s+\w+\s+\d{4}", str(col))]
                if not date_cols:
                    st.error("❌ No valid weekly date columns found in the first file.")
                    st.stop()
    
                df1_trimmed = df1[[df1.columns[0]] + date_cols].copy()
                df1_trimmed.rename(columns={df1.columns[0]: "Product Name"}, inplace=True)
    
                df1_trimmed["Total Sold"] = df1_trimmed[date_cols].sum(axis=1)
                df1_trimmed["Avg Weekly Sold"] = df1_trimmed[date_cols].mean(axis=1)
    
                last_col_header = date_cols[-1]
                cleaned_date = clean_date_string(last_col_header.strip())
                try:
                    last_date = datetime.datetime.strptime(cleaned_date, "%d %b %Y")
                except ValueError:
                    st.error(f"❌ Could not parse the last date column: '{last_col_header}'. Please use format like '3rd Mar 2025'.")
                    st.stop()
    
                if "Closing Inventory" not in df2.columns:
                    st.error("❌ 'Closing Inventory' column not found in the second file.")
                    st.stop()
    
                df2_trimmed = df2[[df2.columns[0], "Closing Inventory"]].copy()
                df2_trimmed.rename(columns={df2.columns[0]: "Product Name"}, inplace=True)
    
                merged_df = pd.merge(df1_trimmed, df2_trimmed, on="Product Name", how="left")
    
                merged_df["Weeks Remaining"] = merged_df.apply(
                    lambda row: round(row["Closing Inventory"] / row["Avg Weekly Sold"], 1) if row["Avg Weekly Sold"] > 0 else float('nan'), axis=1
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
    
                st.success("✅ Run-Out Forecast Completed!")
    
                st.dataframe(
                    merged_df[["Product Name", "Closing Inventory", "Avg Weekly Sold", "Weeks Remaining", "Estimated Run-Out Date", "Status"]],
                    use_container_width=True,
                )
    
                csv = merged_df.to_csv(index=False)
                st.download_button("📥 Download Result as CSV", data=csv, file_name="runout_forecast.csv", mime="text/csv")
    
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # --- Router ---
    if app_choice == "🔁 Vape & Smoking Report":
        description_finder()
    elif app_choice == "📦 E-Liquid Report":
        inventory_matcher()
    elif app_choice == "🔮 Product Run-Out Forecaster":
        runout_forecaster()

