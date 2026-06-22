import streamlit as st
import pandas as pd
import numpy as np
from collections import Counter
import plotly.express as px

# Set konfigurasi halaman dashboard
st.set_page_config(page_title="Product Testing Market Research Dashboard", layout="wide")

st.title("📊 Product Testing & Benchmarking Dashboard")
st.markdown("Upload file database hasil product test untuk melihat analisis percentile norm secara otomatis.")

# ==========================================
# 1. PIPELINE FUNGSI
# ==========================================

def calculate_metrics(scores, scale):
    scores = scores.dropna()
    if len(scores) == 0:
        return pd.Series({"n": 0, "tb": None, "t2b": None, "t3b": None, "mean_score": None})
    
    top1 = scale
    top2 = scale - 1
    top3 = scale - 2

    tb = (scores == top1).mean() * 100
    t2b = (scores.isin([top1, top2])).mean() * 100
    t3b = (scores.isin([top1, top2, top3])).mean() * 100 if scale >= 7 else None

    return pd.Series({
        "n": len(scores),
        "tb": round(tb, 2),
        "t2b": round(t2b, 2),
        "t3b": round(t3b, 2) if t3b is not None else None,
        "mean_score": round(scores.mean(), 2)
    })

def clean_data(dfs):
    cleaned_dfs = {}
    for name, df in dfs.items():
        cols_to_drop = [col for col in df.columns if str(col).endswith(".1")]
        df = df.drop(columns=cols_to_drop, errors="ignore")
        
        df.columns = (
            df.columns.str.lower().str.strip()
            .str.replace(r"\boveral\b", "overall", regex=True)
            .str.replace(r"\bttaste\b", "taste", regex=True)
            .str.replace(r"aftert\\aste", "aftertaste", regex=True)
            .str.replace(r"5pcs\b", "5pts", regex=True)
            .str.replace(r"^purchase intent w/o price$", "purchase intent w/o price - 5pts", regex=True)
            .str.replace(r"^garlic & chili oil taste$", "garlic & chili oil taste - 5pts", regex=True)
            .str.replace(r"palm sugar / gula aren aroma", "palm sugar aroma", regex=True)
            .str.replace(r"palm sugar / gula aren taste", "palm sugar taste", regex=True)
            .str.replace(r"crunchiness / crispiness", "crispiness", regex=True)
            .str.replace(r"\s*-\s*", " - ", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip()
        )
        df = df.loc[:, ~df.columns.str.contains("^unnamed", case=False)]
        cleaned_dfs[name] = df
    return cleaned_dfs

def create_long_format(dfs):
    col_counter = Counter()
    for df in dfs.values():
        col_counter.update(df.columns)

    long_dfs = []
    for name, df in dfs.items():
        metadata_cols = [col for col, count in col_counter.items() if count == len(dfs)]
        parameter_cols = [col for col in df.columns if col not in metadata_cols]

        temp = df.melt(id_vars=metadata_cols, value_vars=parameter_cols, var_name="parameter", value_name="score")
        temp["sheet_name"] = name
        long_dfs.append(temp)

    return pd.concat(long_dfs, ignore_index=True)

def prepare_parameter(master_long_df):
    master_long_df["parameter"] = master_long_df["parameter"].str.replace(r"(\d+)\s*pts", r"\1pts", regex=True)
    master_long_df["scale"] = master_long_df["parameter"].str.extract(r"(\d+)pts")
    master_long_df["scale"] = pd.to_numeric(master_long_df["scale"], errors="coerce")
    master_long_df["parameter_clean"] = master_long_df["parameter"].str.replace(r"\s*-\s*\d+pts", "", regex=True).str.strip()
    return master_long_df

def calculate_percentile_norm(master_long_df):
    results = []
    for (param, scale), group in master_long_df.groupby(["parameter_clean", "scale"]):
        group = group.sort_values(by="score", ascending=False)
        n = len(group)
        
        top25_n = max(1, round(n * 0.25))
        mid50_n = max(1, round(n * 0.50))
        bot25_n = max(1, round(n * 0.25))

        top25 = group.iloc[:top25_n]
        mid50 = group.iloc[:mid50_n]
        bot25 = group.iloc[-bot25_n:]

        row = {"parameter_clean": param, "scale": scale}
        for prefix, data in [("top25", top25), ("mid50", mid50), ("bot25", bot25)]:
            metrics = calculate_metrics(data["score"], scale)
            for k, v in metrics.items():
                row[f"{prefix}_{k}"] = v
        results.append(row)
        
    return pd.DataFrame(results)

# ==========================================
# 2. INTERFACE PENGGUNA
# ==========================================

uploaded_file = st.file_uploader("Pilih file Excel database (.xlsx)", type=["xlsx"])

if uploaded_file is not None:
    with st.spinner("Sedang memproses pipeline data sesuai sintaks notebook, mohon tunggu..."):
        excel_file = pd.ExcelFile(uploaded_file)
        dfs = {sheet: pd.read_excel(uploaded_file, sheet_name=sheet, header=1) for sheet in excel_file.sheet_names}
        
        dfs = clean_data(dfs)
        master_long_df = create_long_format(dfs)
        master_long_df = prepare_parameter(master_long_df)
        percentile_norm = calculate_percentile_norm(master_long_df)
        
    st.success("🎉 Pipeline berhasil dijalankan!")
    
    tab1, tab2 = st.tabs(["🎯 Product Benchmarking", "📋 Percentile Norm Data"])
    
    with tab1:
        st.header("🔍 Product Benchmark Tool")
        col1, col2 = st.columns(2)
        with col1:
            list_produk = master_long_df["sheet_name"].unique()
            selected_product = st.selectbox("Pilih Produk (Product Name):", list_produk, index=0)
            
        with col2:
            available_params = master_long_df[master_long_df["sheet_name"] == selected_product]["parameter_clean"].unique()
            selected_param = st.selectbox("Pilih Parameter (Parameter Name):", available_params, index=0)
            
        product_data = master_long_df[
            (master_long_df["sheet_name"] == selected_product) & 
            (master_long_df["parameter_clean"] == selected_param)
        ]
        
        if len(product_data) > 0:
            scale = product_data["scale"].iloc[0]
            product_mean = round(product_data["score"].mean(), 2)
            
            norm_row = percentile_norm[
                (percentile_norm["parameter_clean"] == selected_param) & 
                (percentile_norm["scale"] == scale)
            ]
            
            st.subheader(f"Hasil Analisis Benchmark")
            c1, c2, c3 = st.columns(3)
            c1.metric(label="Product Name", value=selected_product)
            c2.metric(label="Parameter Clean", value=selected_param)
            c3.metric(label="Scale & Mean Score", value=f"{int(scale)} pts | Mean: {product_mean}")
            
            if not norm_row.empty:
                st.write("### 📈 Grafik Perbandingan Mean Score vs Percentile Norm")
                chart_data = pd.DataFrame({
                    'Kelompok': ['Bottom 25% Mean', 'Mid 50% Mean', 'Produk Kamu', 'Top 25% Mean'],
                    'Mean Score': [
                        norm_row["bot25_mean_score"].values[0],
                        norm_row["mid50_mean_score"].values[0],
                        product_mean,
                        norm_row["top25_mean_score"].values[0]
                    ]
                }).dropna()
                
                fig = px.bar(chart_data, x='Kelompok', y='Mean Score', color='Kelompok', text='Mean Score',
                             title=f"Posisi Score {selected_product} pada Parameter '{selected_param}'")
                st.plotly_chart(fig, use_container_width=True)
                
                st.write("### 📋 Detail Nilai Norma Parameter Terpilih")
                st.dataframe(norm_row, use_container_width=True)
            else:
                st.warning("Data norma percentile untuk kombinasi parameter ini tidak ditemukan.")
        else:
            st.error("Data tidak ditemukan.")
            
    with tab2:
        st.header("📋 Tabel Percentile Norm Lengkap")
        st.dataframe(percentile_norm, use_container_width=True)
        csv = percentile_norm.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Download Data Norm (CSV)", data=csv, file_name="percentile_norm_results.csv", mime="text/csv")

else:
    st.info("💡 Silakan upload file Excel database kamu (`DataDB.xlsx` atau sejenisnya) pada kotak di atas untuk menampilkan isi dashboard!")
