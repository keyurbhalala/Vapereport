import streamlit as st
import pandas as pd
import re
import os
import numpy as np
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
    # ======== FIXED DATA SOURCES (edit if needed) ========
        col_refresh = st.empty()
        if col_refresh.button("↻ Refresh data"):
            st.cache_data.clear()
            st.rerun()
        INVENTORY_CSV_URL = "https://docs.google.com/spreadsheets/d/1xODr-YC8ej_5HNmoR7f9qTO7mnMOFAAwO6Kf-voBpY8/export?format=csv"  # Sheet1 gid (change if needed)
    
        SHORTLIST_URL = "https://raw.githubusercontent.com/keyurbhalala/Vapereport/main/shortlisted_products.xlsx"
    
        # ======== FIXED MATCH SETTINGS (MG ONLY) ========
        VALID_STRENGTHS_NUM = [20,40,50,15,30,3,6,12,5,10]   # your list (order preserved)
        SCORE_THRESHOLD = 85
        SCORER = fuzz.token_sort_ratio
    
        # ---------- Helpers ----------
        def normalize_name(name: str) -> str:
            s = str(name).lower()
            # strip ANY mg token (so “same product” across strengths matches)
            s = re.sub(r"\b(\d{1,3})\s?mg\b", "", s)
            s = re.sub(r"[^a-z0-9]+", " ", s).strip()
            return s
    
        def build_strength_tools(nums):
            """Return (extract_strength_fn, category_labels_in_mg). MG ONLY."""
            nums = [int(x) for x in nums]
            mg_rx = re.compile(rf"\b({'|'.join(map(str, nums))})\s?mg\b", re.IGNORECASE)
    
            def extract_strength(name: str):
                s = str(name).lower()
                m = mg_rx.search(s)
                if m:
                    return f"{int(m.group(1))}mg"
                return None
    
            cats = [f"{n}mg" for n in nums]  # preserve user order
            return extract_strength, cats
    
        @st.cache_data(show_spinner=False)
        def load_inventory_csv(url: str) -> pd.DataFrame:
            import requests
            from io import BytesIO
            r = requests.get(url, timeout=30, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                st.error(
                    "Inventory fetch failed.\n"
                    f"HTTP {r.status_code}\nURL: {url}\nPreview: {r.text[:200]}"
                )
                return pd.DataFrame()
            try:
                df = pd.read_csv(BytesIO(r.content), dtype=str)
                df.columns = [c.strip() for c in df.columns]
                return df
            except Exception as e:
                st.error(f"CSV parse failed: {e}\nFirst 200 bytes: {r.content[:200]}")
                return pd.DataFrame()
    
        @st.cache_data(show_spinner=False)
        def load_shortlist(url: str) -> pd.DataFrame:
            u = url.lower().strip()
            if u.endswith(".csv"):
                df = pd.read_csv(url, dtype=str)
            else:
                df = pd.read_excel(url, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            return df
    
        def pick_inventory_column(df):
            # prefer common names; else first numeric column; else first column
            candidates = [
                "Closing Inventory","Avail. Stock","Available Stock",
                "Stock On Hand","On Hand","Stock","Quantity","Qty"
            ]
            present = [c for c in candidates if c in df.columns]
            if not present:
                numish = [c for c in df.columns if pd.to_numeric(df[c], errors="coerce").notna().any()]
                present = numish or df.columns.tolist()
            return present[0]
    
        # ======== Load data ========
        df_full = load_inventory_csv(INVENTORY_CSV_URL)
        df_subset = load_shortlist(SHORTLIST_URL)
        if df_full.empty or df_subset.empty:
            st.error("Couldn’t load inventory or shortlist.")
            return
        if "SKU Name" not in df_full.columns or "SKU Name" not in df_subset.columns:
            st.error("Both sources need a 'SKU Name' column.")
            return
    
        inv_col = pick_inventory_column(df_full)
        df_full[inv_col] = pd.to_numeric(df_full[inv_col], errors="coerce").fillna(0)
    
        extract_strength, CATS_MG = build_strength_tools(VALID_STRENGTHS_NUM)
    
        # prepare normalized names & strengths
        df_full = df_full.copy()
        df_full["NormName"] = df_full["SKU Name"].map(normalize_name)
        df_full["Strength"] = df_full["SKU Name"].map(extract_strength).str.lower()
    
        corpus = df_full["NormName"].tolist()
    
        # ======== Matching (minimal) ========
        matched_chunks = []
        for prod in df_subset["SKU Name"].astype(str):
            norm = normalize_name(prod)
            if not norm:
                continue
            hit = process.extractOne(norm, corpus, scorer=SCORER)
            if not hit:
                continue
            best_norm, score, _ = hit
            if score < SCORE_THRESHOLD:
                continue
    
            block = df_full[df_full["NormName"] == best_norm].copy()
            block["Matched Product"] = prod
    
            # keep only desired strengths (mg only)
            mask = block["Strength"].isin([c.lower() for c in CATS_MG])
            block = block.loc[mask]
            if not block.empty:
                matched_chunks.append(block)
    
        if not matched_chunks:
            st.info("No matches with current fixed settings.")
            return
    
        matched_df = pd.concat(matched_chunks, ignore_index=True)
        matched_df["Strength"] = pd.Categorical(
            matched_df["Strength"],
            categories=[c.lower() for c in CATS_MG],
            ordered=True
        )
    
        # keep shortlist order in pivot
        subset_order = pd.Series(df_subset["SKU Name"].astype(str)).drop_duplicates().tolist()
        pivot_df = (
            matched_df
            .pivot_table(
                index="Matched Product",
                columns="Strength",
                values=inv_col,
                aggfunc="sum",
                fill_value=0,
            )
            .reindex(subset_order)
            .reset_index()
        )
    
        # make pivot columns pretty/canonical (exact "XXmg" from your list)
        rename_map = {c.lower(): c for c in CATS_MG}
        pivot_df.rename(columns=rename_map, inplace=True)
    
        # ======== Show pivot + download only ========
        st.subheader("📊 Strength-wise Pivot Table")
        st.dataframe(pivot_df, use_container_width=True)
    
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pivot_df.to_excel(writer, index=False, sheet_name="Pivot_Summary")
        output.seek(0)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        st.download_button(
            "📥 Download Pivot (Excel)",
            data=output.getvalue(),
            file_name=f"matched_inventory_pivot_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    
    # --- app 3 ---
    def runout_forecaster():
        st.set_page_config(page_title="🔮 Forecast Wizard", layout="wide", page_icon="📦")
        st.title("📦 Product Run-Out Forecaster")
    
        # ======== CONFIG: Google Sheets CSV links ========
        SALES_FILE_LINK = "https://docs.google.com/spreadsheets/d/1oHWG7i0V08YQPHKARbdXjT_fbEFrmMg51LYtqZbDeag/export?format=csv"
        INVENTORY_FILE_LINK = "https://docs.google.com/spreadsheets/d/1xODr-YC8ej_5HNmoR7f9qTO7mnMOFAAwO6Kf-voBpY8/export?format=csv"
        STORE_INVENTORY_FILE_LINK = "https://docs.google.com/spreadsheets/d/1HCkYJucTjkZ5qCtu4ImIEoX2E-wv1W4Mv3zpH726_ho/export?format=csv"
    
        MIN_WEEKS = 4            # smoothing minimum (kept for future use if needed)
        USE_ADJUSTED = True      # kept for clarity
    
        def download_csv(url):
            r = requests.get(url)
            if r.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(r.content)
                    return tmp.name
            raise Exception(f"Failed to download file from: {url}")
    
        # --- Helpers for pack-size conversion on SALES (e.g., "... 4x" → *4 and name "... 1x") ---
        pack_tail_re = re.compile(r"(\d+)\s*x$", re.IGNORECASE)
    
        def pack_multiplier_from_name(name: str) -> int:
            if not isinstance(name, str):
                return 1
            m = pack_tail_re.search(name.strip())
            return int(m.group(1)) if m else 1
    
        def normalize_to_1x(name: str) -> str:
            if not isinstance(name, str):
                return name
            return pack_tail_re.sub("1x", name.strip())
    
        try:
            # ======== Load all 3 files ========
            sales_path = download_csv(SALES_FILE_LINK)
            inventory_path = download_csv(INVENTORY_FILE_LINK)
            store_inv_path = download_csv(STORE_INVENTORY_FILE_LINK)
    
            df_sales = pd.read_csv(sales_path, thousands=",")
            df_inv   = pd.read_csv(inventory_path, thousands=",")
            df_store = pd.read_csv(store_inv_path, thousands=",")
    
            # Normalize headers
            df_sales.columns = df_sales.columns.astype(str)
            df_inv.columns   = df_inv.columns.astype(str)
            df_store.columns = df_store.columns.astype(str)
    
            # ======== Detect weekly date columns in SALES ========
            date_cols = [c for c in df_sales.columns
                         if re.match(r"\d{1,2}(st|nd|rd|th)?\s+\w+\s+\d{4}", str(c))]
            if not date_cols:
                st.error("❌ No valid weekly date columns found in the sales file.")
                st.stop()
    
            # last_date from sales headers
            last_col_header = date_cols[-1]
            cleaned_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', last_col_header.strip())
            last_date = datetime.datetime.strptime(cleaned_date, "%d %b %Y")
    
            # ======== Prepare INVENTORY (authoritative identity, base DF) ========
            def inv_get(name):
                return next((c for c in df_inv.columns if c.strip().lower() == name.lower()), None)
    
            sku_name_col      = inv_get("SKU Name")
            sku_col           = inv_get("SKU")
            supplier_code_col = inv_get("Supplier Code")
            brand_inv_col     = inv_get("Brand")
            supplier_inv_col  = inv_get("Supplier")
            closing_col       = inv_get("Closing Inventory")
            tag_inv_col       = inv_get("Tag") or inv_get("Tags")  # ← (optional)
    
            needed = [sku_name_col, sku_col, supplier_code_col, brand_inv_col, supplier_inv_col, closing_col]
            if not all(needed):
                st.error("❌ Inventory file is missing one of: SKU Name, SKU, Supplier Code, Brand, Supplier, Closing Inventory.")
                st.stop()
    
            inv_cols = [sku_name_col, sku_col, supplier_code_col, brand_inv_col, supplier_inv_col, closing_col]
            if tag_inv_col:
                inv_cols.append(tag_inv_col)
    
            inv_trim = df_inv[inv_cols].copy()
            rename_map = {
                sku_name_col: "Product Name",
                sku_col: "Product Code",
                supplier_code_col: "Supplier Code",
                brand_inv_col: "Brand",
                supplier_inv_col: "Supplier",
                closing_col: "Warehouse Qnty"
            }
            if tag_inv_col:
                rename_map[tag_inv_col] = "Tags Raw"
            inv_trim.rename(columns=rename_map, inplace=True)
            inv_trim["Product Name"] = inv_trim["Product Name"].astype(str).str.strip()
            inv_trim["Product Code"] = inv_trim["Product Code"].astype(str).str.strip()
    
            # ======== Prepare SALES (normalize names to 1x and scale quantities by trailing Nx) ========
            sales_trim = df_sales.copy()
            sales_trim.rename(columns={
                df_sales.columns[0]: "Product Name",
                df_sales.columns[1]: "Product Code"
            }, inplace=True)
    
            # numeric weekly columns
            for c in date_cols:
                sales_trim[c] = pd.to_numeric(sales_trim[c], errors="coerce").fillna(0)
    
            # compute multiplier from original sales product name; then normalize name to 1x
            sales_trim["__mult"] = sales_trim["Product Name"].apply(pack_multiplier_from_name)
            sales_trim[date_cols] = sales_trim[date_cols].mul(sales_trim["__mult"], axis=0)
            sales_trim["Product Name"] = sales_trim["Product Name"].apply(normalize_to_1x)
    
            # keep tidy ids
            sales_trim["Product Name"] = sales_trim["Product Name"].astype(str).str.strip()
            sales_trim["Product Code"] = sales_trim["Product Code"].astype(str).str.strip()
    
            # optional brand/supplier/tags column names in SALES
            brand_sales_col    = next((c for c in df_sales.columns if "brand" in c.lower()), None)
            supplier_sales_col = next((c for c in df_sales.columns if c.strip().lower() == "supplier"), None)
            tag_sales_col      = next((c for c in df_sales.columns if c.strip().lower() in ("tag", "tags")), None)
    
            # ======== Prepare STORE INVENTORY (sum to Store Qnty) ========
            df_store = df_store.rename(columns={df_store.columns[0]: "Product Name"}).copy()
            df_store["Product Name"] = df_store["Product Name"].astype(str).str.strip().apply(normalize_to_1x)
    
            store_qty_col = next((c for c in df_store.columns
                                  if any(k in c.lower() for k in ["closing", "stock", "quantity"])), None)
            if not store_qty_col:
                st.error("❌ Store inventory file does not have a quantity/stock/closing column.")
                st.stop()
    
            df_store_grouped = df_store.groupby("Product Name")[store_qty_col].sum().reset_index()
            df_store_grouped.rename(columns={store_qty_col: "Store Qnty"}, inplace=True)
    
            # ======== Merge: Inventory base → Sales (by Product Name) ========
            merged = pd.merge(inv_trim, sales_trim, on="Product Name", how="left", suffixes=("", "_sales"))
    
            # Fill weekly NaN with 0 so 0-sale products remain visible
            for c in date_cols:
                merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)
    
            # Ensure Brand/Supplier exist (from inventory); then fallback to sales *_sales if inventory blank
            if "Brand" not in merged.columns:    merged["Brand"] = ""
            if "Supplier" not in merged.columns: merged["Supplier"] = ""
            brand_sales_merged    = f"{brand_sales_col}_sales"    if brand_sales_col else None
            supplier_sales_merged = f"{supplier_sales_col}_sales" if supplier_sales_col else None
    
            if "Product Code_sales" in merged.columns:
                merged["Product Code"] = merged["Product Code"].replace("", pd.NA).fillna(merged["Product Code_sales"])
            if brand_sales_merged and brand_sales_merged in merged.columns:
                merged["Brand"] = merged["Brand"].replace("", pd.NA).fillna(merged[brand_sales_merged])
            if supplier_sales_merged and supplier_sales_merged in merged.columns:
                merged["Supplier"] = merged["Supplier"].replace("", pd.NA).fillna(merged[supplier_sales_merged])
    
            # Bring tags through from inventory, or fall back to sales tag column
            if "Tags Raw" not in merged.columns:
                merged["Tags Raw"] = ""
            if tag_sales_col:
                cand = f"{tag_sales_col}_sales" if f"{tag_sales_col}_sales" in merged.columns else tag_sales_col
                if cand in merged.columns:
                    merged["Tags Raw"] = merged["Tags Raw"].fillna("").astype(str)
                    merged[cand] = merged[cand].fillna("").astype(str)
                    merged["Tags Raw"] = merged["Tags Raw"].where(merged["Tags Raw"].str.strip() != "", merged[cand])
    
            # Cleanup helper/suffix columns
            drop_cols = [c for c in ["Product Code_sales", brand_sales_merged, supplier_sales_merged, "__mult"]
                         if c and c in merged.columns]
            merged.drop(columns=drop_cols, inplace=True, errors="ignore")
    
            # ======== Merge: add Store Qnty ========
            merged = pd.merge(merged, df_store_grouped, on="Product Name", how="left")
            merged["Store Qnty"] = merged["Store Qnty"].fillna(0)
    
            # ======== Normalize Tags ========
            def _split_tags(s):
                if not isinstance(s, str):
                    return []
                parts = [t.strip() for t in s.split(",") if t.strip()]
                seen = set()
                out = []
                for p in parts:
                    pl = p.lower()
                    if pl not in seen:
                        seen.add(pl)
                        out.append(p)
                return out
    
            merged["Tags List"] = merged["Tags Raw"].apply(_split_tags)
            merged["Tags Search Set"] = merged["Tags List"].apply(lambda lst: {t.lower() for t in lst})
            merged["Tags"] = merged["Tags List"].apply(lambda lst: ", ".join(lst))  # pretty display
    
            # ======== Launch-aware average + smoothing ========
            weeks_total = len(date_cols)
    
            def launch_aware_metrics(row):
                vals = np.array([row[c] for c in date_cols], dtype=float)
                first_idx = next((i for i, v in enumerate(vals) if v > 0), None)
                if first_idx is None:
                    weeks_on_sale = 0
                    total_since_launch = 0.0
                else:
                    weeks_on_sale = len(vals) - first_idx
                    total_since_launch = float(vals[first_idx:].sum())
                total_period = float(vals.sum())
                return pd.Series({
                    "Weeks on Sale": weeks_on_sale,
                    "Total Sold (period)": total_period,
                    "Total Since Launch": total_since_launch,
                })
    
            metrics = merged.apply(launch_aware_metrics, axis=1)
            merged[["Weeks on Sale", "Total Sold (period)", "Total Since Launch"]] = metrics
    
           # --- 1) Plain period average (safe if only 1 week of data) ---
            if weeks_total > 1:
                merged["Avg Weekly Sold"] = (merged["Total Sold (period)"] / (weeks_total - 1)).round(2)
            else:
                merged["Avg Weekly Sold"] = 0.0
            
            # --- 2) Launch-aware average (safe & vectorized) ---
            wk  = pd.to_numeric(merged["Weeks on Sale"], errors="coerce").fillna(0)
            tsl = pd.to_numeric(merged["Total Since Launch"], errors="coerce").fillna(0)
            
            merged["Adj Avg Weekly Sold"] = 0.0
            mask = wk > 1                      # only compute when weeks >= 2
            merged.loc[mask, "Adj Avg Weekly Sold"] = (tsl[mask] / (wk[mask] - 1)).round(2)
            
            avg_col = "Adj Avg Weekly Sold"    # or "Avg Weekly Sold"
    
            # ======== Forecast calculations (warehouse stock) ========
            merged["Weeks Remaining"] = merged.apply(
                lambda r: round(r["Warehouse Qnty"] / r[avg_col], 1) if r[avg_col] > 0 else np.nan, axis=1
            )
            merged["Estimated Run-Out Date"] = merged["Weeks Remaining"].apply(
                lambda w: (last_date + datetime.timedelta(weeks=w)).strftime("%Y-%m-%d") if pd.notna(w) else ""
            )
            merged["Status"] = merged["Warehouse Qnty"].apply(lambda x: "❌ Out of Stock" if x <= 0 else "✅ In Stock")
    
            st.success("✅ Forecast Completed Successfully (sales normalized to units; launch-aware averages with tag search).")
    
            # ======== Search bar (inventory-backed fields + Tags) ========
            suggestions = []
            suggestions += [f"{x} [PRODUCT NAME]" for x in merged["Product Name"].dropna().unique()]
            suggestions += [f"{x} [PRODUCT CODE]" for x in merged["Product Code"].dropna().unique()]
            suggestions += [f"{x} [BRAND]"        for x in merged["Brand"].dropna().unique()]
            suggestions += [f"{x} [SUPPLIER]"     for x in merged["Supplier"].dropna().unique()]
            unique_tags = sorted({t for lst in merged["Tags List"] for t in lst})
            suggestions += [f"{t} [TAG]" for t in unique_tags]
            
            PAGE_KEY = "runout"  # different from the restock page
            def k(name): return f"{PAGE_KEY}:{name}"
            selected = st.multiselect("🔎 Search by Name, Code, Brand, Supplier, Tag:", sorted(list(set(suggestions))),key=k("search"))
    
            if selected:
                mask = pd.Series(False, index=merged.index)
                for item in selected:
                    if item.endswith("[PRODUCT NAME]"):
                        v = item.replace("[PRODUCT NAME]", "").strip()
                        mask |= merged["Product Name"] == v
                    elif item.endswith("[PRODUCT CODE]"):
                        v = item.replace("[PRODUCT CODE]", "").strip()
                        mask |= merged["Product Code"] == v
                    elif item.endswith("[BRAND]"):
                        v = item.replace("[BRAND]", "").strip()
                        mask |= merged["Brand"] == v
                    elif item.endswith("[SUPPLIER]"):
                        v = item.replace("[SUPPLIER]", "").strip()
                        mask |= merged["Supplier"] == v
                    elif item.endswith("[TAG]"):
                        v = item.replace("[TAG]", "").strip().lower()
                        mask |= merged["Tags Search Set"].apply(lambda s: v in s)
                show_df = merged[mask]
            else:
                show_df = merged
    
            # ======== Display ========
            st.dataframe(
                show_df[[
                    "Product Name", "Product Code", "Brand",
                    "Warehouse Qnty", "Store Qnty",
                    "Weeks on Sale", "Adj Avg Weekly Sold",
                    "Weeks Remaining", "Estimated Run-Out Date", "Status"
                    #"Tags"  # show normalized tags
                ]],
                use_container_width=True, height=800
            )
    
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
                    if all(col in df.columns for col in ['product', 'sku', 'received']):
                        df = df[['product', 'sku', 'received']]
                        dfs.append(df)
                    else:
                        st.warning(f"File {file.name} skipped: missing 'product', 'sku', or 'received' column.")
                except Exception as e:
                    st.error(f"File {file.name} could not be read. {e}")
        
            if dfs:
                all_data = pd.concat(dfs, ignore_index=True)
                # Group by product & sku, sum received
                all_data_grouped = all_data.groupby(['product', 'sku'], as_index=False)['received'].sum()
                all_data_grouped = all_data_grouped[all_data_grouped['received'] != 0]
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
        store_to_group_url = "https://raw.githubusercontent.com/keyurbhalala/Vapereport/main/store_to_group.xlsx"
        group_to_island_url = "https://raw.githubusercontent.com/keyurbhalala/Vapereport/main/group_to_island.xlsx"
        
        
        store_to_group_df = load_excel_from_github(store_to_group_url)
        group_to_island_df = load_excel_from_github(group_to_island_url)
        
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
        
        def stock_rotation_logic(
            df,
            warehouse_name="Warehouse",
            to_outlets=None,
            outlet_lookup=None
        ):
            suggestions = []
        
            for sku in df["SKU"].unique():
                sku_df = df[df["SKU"] == sku].copy()
                # 1. Outlets needing stock, ranked by most needed
                needs_stock = sku_df[
                    (sku_df["Closing Inventory"] == 0) & (sku_df["Items Sold"] > 0)
                ]
                if to_outlets:
                    needs_stock = needs_stock[needs_stock["Outlet"].isin(to_outlets)]
                needs_stock = needs_stock.sort_values(by="Items Sold", ascending=False)  # fill highest demand first
        
                # 2. Warehouse available
                warehouse_row = sku_df[
                    (sku_df["Outlet"] == warehouse_name) & (sku_df["Closing Inventory"] > 0)
                ]
                warehouse_remaining = (
                    warehouse_row.iloc[0]["Closing Inventory"] if not warehouse_row.empty else 0
                )
        
                # 3. Overstocked (not needed at all = not selling, has stock) - use as sources first
                overstocked = sku_df[
                    (sku_df["Outlet"] != warehouse_name)
                    & (sku_df["Closing Inventory"] > 0)
                    & (sku_df["Items Sold"] == 0)
                ]
                overstocked_remaining = {
                    over["Outlet"]: over["Closing Inventory"] for _, over in overstocked.iterrows()
                }
        
                # 4. Regular overstocked (selling, but has surplus) - classic rotation logic if you wish
                regular_overstocked = sku_df[
                    (sku_df["Outlet"] != warehouse_name)
                    & (sku_df["Closing Inventory"] > 0)
                    & (sku_df["Items Sold"] > 0)
                ]
                regular_overstocked_remaining = {
                    over["Outlet"]: over["Closing Inventory"] for _, over in regular_overstocked.iterrows()
                }
        
                for _, need in needs_stock.iterrows():
                    qty_needed = need["Items Sold"]
        
                    # A. Warehouse first
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
        
                    # B. Use overstocked (not needed at all) sources, prioritized
                    if outlet_lookup:
                        prioritized_sources = prioritize_sources(
                            need["Outlet"], list(overstocked_remaining.keys()), outlet_lookup
                        )
                    else:
                        prioritized_sources = list(overstocked_remaining.keys())
        
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
        
                    # C. (Optional) Use regular overstocked sources
                    if qty_needed > 0:
                        for outlet_name in regular_overstocked_remaining:
                            available = regular_overstocked_remaining[outlet_name]
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
                            regular_overstocked_remaining[outlet_name] -= qty
                            qty_needed -= qty
                            if qty_needed <= 0:
                                break
        
            return pd.DataFrame(suggestions)
        
        # =============================================================
        # ========================== UI SECTION =======================
        # =============================================================
        
        # --------- 1. MAIN INVENTORY UPLOAD -----------
        file = st.file_uploader("Upload inventory CSV or Excel file", type=["csv", "xlsx"])
        # --------- 2. MAPPING FILES UPLOAD -----------
        #st.sidebar.header("Upload Mapping Files")
        #store_to_group_file = st.sidebar.file_uploader("Store to Group Mapping (Excel)", type=["xlsx"])
        #group_to_island_file = st.sidebar.file_uploader("Group to Island Mapping (Excel)", type=["xlsx"])
        
        if file:
            # --- Load all files ---
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            df.columns = [c.strip() for c in df.columns]
        
            #store_to_group_df = load_excel(store_to_group_file)
            #group_to_island_df = load_excel(group_to_island_file)
            store_to_group_df = load_excel_from_github(store_to_group_url)
            group_to_island_df = load_excel_from_github(group_to_island_url)
        
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
                    help="Leave empty to allow suggestions for all stores",
                    key="to_outlets"
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











































