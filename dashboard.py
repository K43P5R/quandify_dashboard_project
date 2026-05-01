import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import timedelta
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Quandify Thermal Analysis")

# Modern CSS för illustrationen och layouten
st.markdown("""
    <style>
    .pipe-container {
        background-color: #f0f2f6;
        padding: 40px;
        border-radius: 15px;
        text-align: center;
        margin: 20px 0;
        position: relative;
    }
    .pipe {
        height: 60px;
        background: linear-gradient(90deg, #3498db 0%, #3498db 20%, #ecf0f1 50%, #3498db 80%, #3498db 100%);
        border: 4px solid #2980b9;
        border-radius: 30px;
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #2c3e50;
        font-weight: bold;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    .label {
        position: absolute;
        font-size: 0.9rem;
        font-weight: 600;
        color: #555;
    }
    .label-ambient { top: -25px; left: 50%; transform: translateX(-50%); color: #e67e22; }
    .label-incoming { left: -10px; bottom: -25px; color: #3498db; }
    .label-measured { top: 70px; left: 50%; transform: translateX(-50%); color: #2c3e50; }
    .result-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #3498db;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data
def load_and_analyze(file_path):
    df = pd.read_parquet(file_path)
    df['Time'] = pd.to_datetime(df['Time'])
    col_temp = 'temperature flowLogS'
    col_ambient = 'ambientTemperature flowLogS'
    
    # Glidande medelvärden
    df['amb_filled'] = df[col_ambient].ffill().bfill()
    df['temp_smoothed'] = df[col_temp].rolling(window=10, center=True).mean()
    df['amb_smoothed'] = df['amb_filled'].rolling(window=10, center=True).mean()
    
    # Kontinuitet (5s)
    time_diffs = df['Time'].diff().dt.total_seconds()
    is_break = (time_diffs > 5) | (time_diffs.isna())
    df['cont_block'] = is_break.cumsum()
    
    all_stable_periods = []
    for _, block_df in df.groupby('cont_block'):
        if (block_df['Time'].max() - block_df['Time'].min()) < timedelta(minutes=60):
            continue
        
        block_df = block_df.reset_index(drop=True)
        temps = block_df['temp_smoothed'].values
        times = block_df['Time'].values
        i, n = 0, len(temps)
        
        while i < n - 900:
            start_temp = temps[i]
            if np.isnan(start_temp):
                i += 1
                continue
            
            tolerance = start_temp * 0.02
            remaining_temps = temps[i:]
            out_of_bounds = np.where(np.abs(remaining_temps - start_temp) > tolerance)[0]
            end_idx = i + out_of_bounds[0] if len(out_of_bounds) > 0 else n
            
            if (times[end_idx-1] - times[i]) >= np.timedelta64(60, 'm'):
                period = block_df.iloc[i:end_idx].copy()
                m_water = period['temp_smoothed'].mean(skipna=True)
                m_ambient = period['amb_smoothed'].mean(skipna=True)
                
                if not pd.isna(m_water) and not pd.isna(m_ambient) and m_water <= m_ambient:
                    p_temp, p_amb = period['temp_smoothed'].values, period['amb_smoothed'].values
                    v_low, v_high = p_temp * 0.98, p_temp * 1.02
                    a_low, a_high = p_amb - 0.25, p_amb + 0.25
                    overlap = (v_low <= a_high) & (v_high >= a_low)
                    valid_overlap = overlap[~np.isnan(overlap)]
                    
                    period['has_total_diff'] = not np.any(valid_overlap) if len(valid_overlap) > 0 else False
                    all_stable_periods.append(period)
                i = end_idx
            else:
                i += 1
                
    return df, all_stable_periods

@st.cache_data
def scan_all_units(data_dir, files):
    with_p, without_p = [], []
    for f in files:
        _, periods = load_and_analyze(os.path.join(data_dir, f))
        if periods:
            with_p.append(f)
        else:
            without_p.append(f)
    return with_p, without_p

st.title("🌡️ Quandify: Termisk Jämviktsanalys")

data_dir = "cleaned_data"
all_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.parquet')])

# Global skanning toggle
scan_all = st.sidebar.toggle("Skanna alla enheter")

if scan_all:
    with st.spinner("Kategoriserar enheter..."):
        with_p, without_p = scan_all_units(data_dir, all_files)
    
    st.sidebar.subheader("Enhetslistor")
    list_type = st.sidebar.radio("Visa lista:", ["✅ Med perioder", "❌ Utan perioder"])
    
    if list_type == "✅ Med perioder":
        selected_file = st.sidebar.selectbox(f"Enhet ({len(with_p)} st)", with_p)
    else:
        selected_file = st.sidebar.selectbox(f"Enhet ({len(without_p)} st)", without_p)
else:
    selected_file = st.sidebar.selectbox("Välj enhet", all_files)

if selected_file:
    file_path = os.path.join(data_dir, selected_file)
    df, periods = load_and_analyze(file_path)
    
    if not periods:
        st.warning(f"Filen **{selected_file}** har inga stabila perioder.")
        if st.checkbox("Visa hela förloppet"):
            fig = go.Figure()
            fig.add_trace(go.Scattergl(x=df['Time'], y=df['temperature flowLogS'], name="Vatten", line=dict(color='blue')))
            fig.add_trace(go.Scattergl(x=df['Time'], y=df['amb_filled'], name="Ambient", line=dict(color='orange', dash='dash')))
            st.plotly_chart(fig, width='stretch')
    else:
        diff_p = [p for p in periods if p['has_total_diff'].iloc[0]]
        overlap_p = [p for p in periods if not p['has_total_diff'].iloc[0]]
        
        st.sidebar.metric("Tydlig Diff", len(diff_p))
        st.sidebar.metric("Överlappande", len(overlap_p))

        tab1, tab2 = st.tabs(["🔴 Tydlig Diff", "🟢 Överlappande"])
        
        def render_content(p_list, key):
            if not p_list:
                st.info("Inga perioder i denna kategori.")
                return
                
            options = [f"Period {i+1}: {p['Time'].min().strftime('%m-%d %H:%M')}" for i, p in enumerate(p_list)]
            idx = st.selectbox("Välj period", range(len(p_list)), format_func=lambda x: options[x], key=f"sel_{key}")
            
            p = p_list[idx]
            duration = (p['Time'].max() - p['Time'].min()).total_seconds() / 60
            
            # Graf
            fig = go.Figure()
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed']*1.02, mode='lines', line=dict(width=0), showlegend=False))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed']*0.98, mode='lines', fill='tonexty', fillcolor='rgba(0,0,255,0.1)', name="Vatten ±2%"))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed'], mode='lines', line=dict(color='blue', width=2), name="Vatten (S)"))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed']+0.25, mode='lines', line=dict(width=0), showlegend=False))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed']-0.25, mode='lines', fill='tonexty', fillcolor='rgba(255,165,0,0.1)', name="Ambient ±0.25°C"))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed'], mode='lines', line=dict(color='orange', dash='dash'), name="Ambient (S)"))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['flowLph flowLogS'], mode='lines', name="Flöde", yaxis="y2", line=dict(color='red', width=1), opacity=0.3))
            fig.update_layout(height=500, yaxis2=dict(overlaying='y', side='right'), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, width='stretch')

            # --- FLÖDESKALKYLATOR ---
            st.divider()
            st.subheader("🧮 Flödeskalkylator (Termisk Jämvikt)")
            
            m_amb = p['amb_smoothed'].mean()
            m_pipe = p['temperature flowLogS'].mean()
            
            col_calc, col_img = st.columns([1, 1.5])
            with col_calc:
                st.markdown('<div class="result-card">', unsafe_allow_html=True)
                k_factor = st.number_input("K-faktor", value=1.00, step=0.1, key=f"k_{key}_{idx}")
                t_ambient = st.number_input("Rumstemperatur (°C)", value=float(m_amb), step=0.1, key=f"ta_{key}_{idx}")
                t_pipe = st.number_input("Uppmätt rörtemperatur (°C)", value=float(m_pipe), step=0.1, key=f"tp_{key}_{idx}")
                t_incoming = st.number_input("Inkommande vatten (°C)", value=8.0, step=0.1, key=f"ti_{key}_{idx}")
                st.markdown('</div>', unsafe_allow_html=True)
                
            diff_rum = t_ambient - t_pipe
            diff_ink = t_pipe - t_incoming
            flow_result = k_factor * (diff_rum / diff_ink) if diff_ink != 0 else 0.0

            with col_img:
                st.metric("Beräknat Flöde", f"{flow_result:.2f} L/h")
                st.markdown(f"""
                <div class="pipe-container">
                    <div class="label label-ambient">Rumstemperatur: {t_ambient:.1f}°C</div>
                    <div class="pipe">Uppmätt: {t_pipe:.1f}°C</div>
                    <div class="label label-incoming">Inkommande: {t_incoming:.1f}°C</div>
                    <div class="label label-measured">Vattnet värms upp av rummet</div>
                </div>
                """, unsafe_allow_html=True)
                st.write(f"**Diff Rum:** {diff_rum:.2f}°C | **Diff Inkommande:** {diff_ink:.2f}°C")

        with tab1: render_content(diff_p, "t1")
        with tab2: render_content(overlap_p, "t2")
