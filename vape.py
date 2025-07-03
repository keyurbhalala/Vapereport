import streamlit as st
import pandas as pd
import re
import os
import io
from io import BytesIO
from rapidfuzz import process, fuzz

st.set_page_config(page_title="🧪 Combined Product Tools", layout="wide")
st.title("🧰 Product Utility Suite")

# --- Sidebar Navigation ---
app_choice = st.sidebar.radio("Choose Tool", ["🔁 Old ➡ New Description Finder", "📦 Strength-wise Inventory Matcher"])

# --- App 1 ---
# --- App 1 ---
def description_finder():
    st.header("🔁 Exact Product Stock Matcher (Ignore Column Names)")

    file1 = st.file_uploader("Upload File 1 (Full Inventory)", type=["xlsx"], key="file1")
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

    file_full = st.file_uploader("Upload Full Inventory File (Excel or CSV)", type=["xlsx", "csv"], key="full")
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
if app_choice == "🔁 Old ➡ New Description Finder":
    description_finder()
elif app_choice == "📦 Strength-wise Inventory Matcher":
    inventory_matcher()
