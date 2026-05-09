import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import timedelta
import plotly.graph_objects as go

# --- PAGE CONFIG ---
st.set_page_config(
    layout="wide", 
    page_title="Quandify | Thermal Analytics", 
    page_icon="🌡️"
)

# --- ROBUST CSS STYLING ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .header-box {
        padding: 1.5rem 0;
        margin-bottom: 2rem;
        border-bottom: 2px solid #2563eb;
    }
    .header-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        margin: 0;
    }

    [data-testid="stMetricValue"] {
        font-weight: 800 !important;
        color: #2563eb !important;
    }
    
    .calc-container {
        background-color: rgba(37, 99, 235, 0.05);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(37, 99, 235, 0.2);
        margin-bottom: 20px;
    }

    .pipe-viz {
        background-color: #0f172a;
        padding: 30px;
        border-radius: 12px;
        text-align: center;
        color: white !important;
    }
    .pipe-viz * { color: white !important; }
    
    .pipe-bar {
        height: 40px;
        background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #1e40af 100%);
        border-radius: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 800;
        border: 1px solid #60a5fa;
        margin: 10px 0;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data
def load_and_analyze(file_path):
    df = pd.read_parquet(file_path)
    df['Time'] = pd.to_datetime(df['Time'])
    col_temp, col_ambient = 'temperature flowLogS', 'ambientTemperature flowLogS'
    
    df['amb_filled'] = df[col_ambient].ffill().bfill()
    df['temp_smoothed'] = df[col_temp].rolling(window=10, center=True).mean()
    df['amb_smoothed'] = df['amb_filled'].rolling(window=10, center=True).mean()
    
    time_diffs = df['Time'].diff().dt.total_seconds()
    is_break = (time_diffs > 5) | (time_diffs.isna())
    df['cont_block'] = is_break.cumsum()
    
    all_periods = []
    for _, block_df in df.groupby('cont_block'):
        if (block_df['Time'].max() - block_df['Time'].min()) < timedelta(minutes=60):
            continue
        
        block_df = block_df.reset_index(drop=True)
        temps, times = block_df['temp_smoothed'].values, block_df['Time'].values
        i, n = 0, len(temps)
        
        while i < n - 900:
            start_temp = temps[i]
            if np.isnan(start_temp): i += 1; continue
            tolerance = start_temp * 0.02
            out_of_bounds = np.where(np.abs(temps[i:] - start_temp) > tolerance)[0]
            end_idx = i + out_of_bounds[0] if len(out_of_bounds) > 0 else n
            
            if (times[end_idx-1] - times[i]) >= np.timedelta64(60, 'm'):
                period = block_df.iloc[i:end_idx].copy()
                m_water = period['temp_smoothed'].mean(skipna=True)
                m_ambient = period['amb_smoothed'].mean(skipna=True)
                
                if not pd.isna(m_water) and not pd.isna(m_ambient) and m_water <= m_ambient:
                    p_temp, p_amb = period['temp_smoothed'].values, period['amb_smoothed'].values
                    overlap = (p_temp * 0.98 <= p_amb + 0.25) & (p_temp * 1.02 >= p_amb - 0.25)
                    period['has_total_diff'] = not np.any(overlap[~np.isnan(overlap)])
                    all_periods.append(period)
                i = end_idx
            else: i += 1
    return df, all_periods

# --- HEADER ---
st.markdown("""
    <div class="header-box">
        <div class="header-title">QUANDIFY <span style="color:#2563eb">ANALYTICS</span></div>
        <div style="opacity:0.7; font-weight:600;">Thermal Leak Detection System</div>
    </div>
""", unsafe_allow_html=True)

data_dir = "cleaned_data"
all_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.parquet')])

with st.sidebar:
    st.markdown("### ⚙️ Inställningar")
    scan_all = st.toggle("Global enhetsskanning")

if scan_all:
    if 'scan_results' not in st.session_state or st.session_state.scan_results is None:
        with st.spinner("Analyserar sensordata..."):
            res = {"diff": [], "overlap": [], "none": []}
            for f in all_files:
                _, periods = load_and_analyze(os.path.join(data_dir, f))
                if not periods: res["none"].append(f)
                elif any(p['has_total_diff'].iloc[0] for p in periods): res["diff"].append(f)
                else: res["overlap"].append(f)
            st.session_state.scan_results = res
    
    r = st.session_state.scan_results
    cat = st.sidebar.radio("Filtrera efter tillstånd:", [f"🔴 Läckage ({len(r['diff'])})", f"🟢 Normal ({len(r['overlap'])})", f"⚪ Inaktiv ({len(r['none'])})"])
    key = "diff" if "🔴" in cat else "overlap" if "🟢" in cat else "none"
    selected_file = st.sidebar.selectbox("Välj Enhet", r[key])
else:
    st.session_state.scan_results = None
    selected_file = st.sidebar.selectbox("Välj Enhet (Osorterad)", all_files)

if selected_file:
    df, periods = load_and_analyze(os.path.join(data_dir, selected_file))
    
    if not periods:
        st.info("Inga stabila analysperioder hittades för denna enhet.")
    else:
        diff_p = [p for p in periods if p['has_total_diff'].iloc[0]]
        overlap_p = [p for p in periods if not p['has_total_diff'].iloc[0]]
        
        with st.sidebar:
            st.divider()
            st.markdown("### 📊 Enhetsstatistik")
            c1, c2 = st.columns(2)
            c1.metric("Läckor", len(diff_p))
            c2.metric("Normal", len(overlap_p))
            st.write(f"Totalt: {len(diff_p) + len(overlap_p)} stabila perioder")
            st.divider()

        tab1, tab2 = st.tabs(["🔴 DETEKTERADE LÄCKOR", "🟢 NORMALTILLSTÅND"])
        
        def render_content(p_list, t_key):
            if not p_list: 
                st.write("Ingen data hittades i denna kategori.")
                return
            
            p_idx = st.selectbox("Välj tidsperiod", range(len(p_list)), format_func=lambda x: f"Mätning {x+1}: {p_list[x]['Time'].min().strftime('%Y-%m-%d %H:%M')}", key=t_key)
            p = p_list[p_idx]
            
            # --- CALCULATIONS (CONVERGENCE) ---
            p_start_time = p['Time'].min()
            p_start_idx = df[df['Time'] == p_start_time].index[0]
            all_before = df[df['Time'] < p_start_time]
            
            incoming_t, k_val, debug = 8.0, 1.0, "N/A"
            conv_df = pd.DataFrame()
            conv_type = "Stabil"

            if not all_before.empty:
                back_df = all_before.tail(10800).copy()
                flow_col, temp_col = 'flowLph flowLogS', 'temperature flowLogS'
                t_vals, idxs = back_df['temp_smoothed'].values[::-1], back_df.index[::-1]
                f_vals = back_df[flow_col].values[::-1]
                
                start_idx = back_df.index[0]
                for i in range(30, len(t_vals)):
                    if f_vals[i] > 5 or (not np.isnan(t_vals[i]) and not np.isnan(t_vals[i-30]) and abs(t_vals[i] - t_vals[i-30]) > 1.0):
                        start_idx = idxs[i]
                        break
                
                conv_df = df.loc[start_idx:p_start_idx]
                temp_start, temp_end = conv_df[temp_col].iloc[0], conv_df[temp_col].iloc[-1]
                if temp_end > temp_start + 0.5:
                    incoming_t, conv_type = float(conv_df[temp_col].min()), "Uppvärmning"
                else:
                    incoming_t, conv_type = 8.0, "Avkylning"
                
                if incoming_t > 20: incoming_t = 8.0
                
                try:
                    c = conv_df.dropna(subset=['temp_smoothed', 'amb_smoothed']).copy()
                    
                    # Om uppvärmning: Beräkna K endast från minimipunkten och framåt
                    if conv_type == "Uppvärmning":
                        min_time_idx = c[temp_col].idxmin()
                        c = c.loc[min_time_idx:]
                    
                    c['dT'] = np.abs(c['temp_smoothed'] - c['amb_smoothed'])
                    c = c[c['dT'] > 0.05]
                    
                    if len(c) > 20:
                        y, x = np.log(c['dT'].values), (c['Time'] - c['Time'].min()).dt.total_seconds().values
                        slope, _ = np.polyfit(x, y, 1)
                        k_val = max(0.1, min(20.0, (-slope) * 10000))
                        debug = f"Beräknat K: {k_val:.3f} ({conv_type})"
                    else: debug = f"Få punkter ({conv_type})"
                except: debug = "K-faktor Fel"

            # --- VISUALIZATION ---
            col_left, col_right = st.columns([2, 1])
            with col_left:
                st.subheader("📊 Temperaturanalys (Stabil)")
                fig = go.Figure()
                fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed'], name="Vatten", line=dict(color='#2563eb', width=3)))
                fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed'], name="Omgivning", line=dict(color='#f59e0b', dash='dash')))
                # Lägg till flöde (Grön färg)
                fig.add_trace(go.Scattergl(x=p['Time'], y=df.loc[p.index, flow_col], name="Flöde (L/h)", yaxis="y2", line=dict(color='#10b981', width=1.5), opacity=0.6))
                
                fig.update_layout(
                    height=400, 
                    margin=dict(t=20, b=20, l=0, r=0), 
                    legend=dict(orientation="h", y=1.1),
                    yaxis2=dict(overlaying='y', side='right', title="Flöde (L/h)", showgrid=False)
                )
                st.plotly_chart(fig, use_container_width=True)

                if not conv_df.empty and len(conv_df) > 10:
                    st.subheader(f"📈 Konvergenshistorik ({conv_type})")
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scattergl(x=conv_df['Time'], y=conv_df['temp_smoothed'], name="Vatten", line=dict(color='#2563eb', width=2.5)))
                    fig2.add_trace(go.Scattergl(x=conv_df['Time'], y=conv_df['amb_smoothed'], name="Omgivning", line=dict(color='#f59e0b', dash='dash')))
                    
                    # Markera minimipunkten med pil
                    min_idx = conv_df[temp_col].idxmin()
                    min_row = conv_df.loc[min_idx]
                    fig2.add_annotation(x=min_row['Time'], y=min_row[temp_col], text=f"MIN: {min_row[temp_col]:.1f}°C", showarrow=True, arrowhead=2, bgcolor="#2563eb", font=dict(color="white"), ay=-40)
                    fig2.update_layout(height=300, margin=dict(t=20, b=20, l=0, r=0), showlegend=False)
                    st.plotly_chart(fig2, use_container_width=True)

            with col_right:
                st.subheader("🧮 Kalkylator")
                st.markdown(f'<div style="font-size:0.85rem; color:#2563eb; font-weight:600; margin-bottom:10px;">Status: {debug}</div>', unsafe_allow_html=True)
                st.markdown('<div class="calc-container">', unsafe_allow_html=True)
                # Unika nycklar för varje mätning så att värdena uppdateras korrekt
                in_k = st.number_input("K-Faktor (Auto)", value=float(k_val), step=0.1, key=f"k{t_key}_{p_idx}")
                in_ta = st.number_input("Omgivning (°C)", float(p['amb_smoothed'].mean()), step=0.1, key=f"ta{t_key}_{p_idx}")
                in_tp = st.number_input("Rör (°C)", float(p['temp_smoothed'].mean()), step=0.1, key=f"tp{t_key}_{p_idx}")
                in_ti = st.number_input("Inkommande (°C)", float(incoming_t), step=0.1, key=f"ti{t_key}_{p_idx}")
                st.markdown('</div>', unsafe_allow_html=True)
                
                flow = in_k * ((in_ta - in_tp) / (in_tp - in_ti)) if (in_tp - in_ti) != 0 else 0.0
                st.metric("Beräknat Läckageflöde", f"{flow:.3f} L/h")
                
                st.markdown(f"""
                    <div class="pipe-viz">
                        <div style="font-size:0.75rem; margin-bottom:10px; font-weight:700;">VIRTUELL MÄTARE</div>
                        <div class="pipe-bar">{in_tp:.1f}°C</div>
                        <div style="font-size:0.85rem; margin-top:10px;">In: {in_ti:.1f}°C • Miljö: {in_ta:.1f}°C</div>
                    </div>
                """, unsafe_allow_html=True)

        with tab1: render_content(diff_p, "tab_leak")
        with tab2: render_content(overlap_p, "tab_norm")
