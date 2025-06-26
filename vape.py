import streamlit as st
import pandas as pd
from io import BytesIO

st.title("Exact Product Stock Matcher (Ignore Column Names)")

# File upload
file1 = st.file_uploader("Upload File 1 (Full Inventory)", type=["xlsx"])
file2 = st.file_uploader("Upload File 2 (Shortlisted Products)", type=["xlsx"])

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

        st.success("Exact match completed!")
        st.dataframe(df_result)

        # Excel download preparation
        def to_excel_download(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()

        st.download_button(
            label="Download Result as Excel",
            data=to_excel_download(df_result),
            file_name="matched_stock_exact.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Error processing files: {e}")
