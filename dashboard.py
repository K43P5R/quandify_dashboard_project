import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import timedelta
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Quandify Thermal Analysis")

# Modern CSS
st.markdown("""
    <style>
    .pipe-container { background-color: #f0f2f6; padding: 40px; border-radius: 15px; text-align: center; margin: 20px 0; position: relative; }
    .pipe { height: 60px; background: linear-gradient(90deg, #3498db 0%, #ecf0f1 50%, #3498db 100%); border: 4px solid #2980b9; border-radius: 30px; display: flex; align-items: center; justify-content: center; font-weight: bold; }
    .label { position: absolute; font-size: 0.9rem; font-weight: 600; }
    .label-ambient { top: -25px; left: 50%; transform: translateX(-50%); color: #e67e22; }
    .label-incoming { left: 10px; bottom: -25px; color: #3498db; }
    .result-card { background: white; padding: 20px; border-radius: 10px; border-left: 5px solid #3498db; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

@st.cache_data
def load_and_analyze(file_path):
    df = pd.read_parquet(file_path)
    df['Time'] = pd.to_datetime(df['Time'])
    col_temp, col_ambient = 'temperature flowLogS', 'ambientTemperature flowLogS'
    
    # Modellering (Utjämning)
    df['amb_filled'] = df[col_ambient].ffill().bfill()
    df['temp_smoothed'] = df[col_temp].rolling(window=10, center=True).mean()
    df['amb_smoothed'] = df['amb_filled'].rolling(window=10, center=True).mean()
    
    # Kontinuitet
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

st.title("🌡️ Quandify: Termisk Analys")

data_dir = "cleaned_data"
all_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.parquet')])

# Använd session_state för att spara skanningsresultat så det inte laggar vid filbyte
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

scan_all = st.sidebar.toggle("Skanna alla enheter för kategorisering")

if scan_all:
    if st.session_state.scan_results is None:
        with st.spinner("Analyserar alla enheter..."):
            results = {"diff": [], "overlap": [], "none": []}
            for f in all_files:
                _, periods = load_and_analyze(os.path.join(data_dir, f))
                if not periods:
                    results["none"].append(f)
                elif any(p['has_total_diff'].iloc[0] for p in periods):
                    results["diff"].append(f)
                else:
                    results["overlap"].append(f)
            st.session_state.scan_results = results
    
    res = st.session_state.scan_results
    cat = st.sidebar.radio("Visa kategori:", [
        f"🔴 Tydlig Diff ({len(res['diff'])})", 
        f"🟢 Endast Överlapp ({len(res['overlap'])})", 
        f"⚪ Inga Perioder ({len(res['none'])})"
    ])
    
    list_key = "diff" if "🔴" in cat else "overlap" if "🟢" in cat else "none"
    selected_file = st.sidebar.selectbox("Välj enhet", res[list_key], key="file_selector")
else:
    st.session_state.scan_results = None # Reset om man stänger av
    selected_file = st.sidebar.selectbox("Välj enhet (Osorterad)", all_files)

if selected_file:
    file_path = os.path.join(data_dir, selected_file)
    df, periods = load_and_analyze(file_path)
    
    if not periods:
        st.warning(f"Inga stabila perioder i {selected_file}.")
        if st.checkbox("Visa hela temperaturförloppet"):
            fig = go.Figure()
            fig.add_trace(go.Scattergl(x=df['Time'], y=df['temperature flowLogS'], name="Vatten", line=dict(color='blue')))
            fig.add_trace(go.Scattergl(x=df['Time'], y=df['amb_filled'], name="Ambient", line=dict(color='orange', dash='dash')))
            st.plotly_chart(fig, width='stretch')
    else:
        diff_p = [p for p in periods if p['has_total_diff'].iloc[0]]
        overlap_p = [p for p in periods if not p['has_total_diff'].iloc[0]]
        
        # Återinför statistik i sidopanelen
        st.sidebar.divider()
        st.sidebar.subheader("Enhetsstatistik")
        st.sidebar.metric("Tydlig Diff", len(diff_p))
        st.sidebar.metric("Överlappande", len(overlap_p))
        
        tab1, tab2 = st.tabs([f"🔴 Tydlig Diff ({len(diff_p)})", f"🟢 Överlappande ({len(overlap_p)})"])
        
        def render_content(p_list, key):
            if not p_list: st.info("Inga perioder här."); return
            idx = st.selectbox("Välj period", range(len(p_list)), format_func=lambda x: f"Period {x+1}: {p_list[x]['Time'].min().strftime('%m-%d %H:%M')}", key=key)
            p = p_list[idx]
            
            fig = go.Figure()
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed']*1.02, mode='lines', line=dict(width=0), showlegend=False, visible='legendonly'))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed']*0.98, mode='lines', fill='tonexty', fillcolor='rgba(0,0,255,0.1)', line=dict(width=0), name="Vatten ±2%", visible='legendonly'))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['temp_smoothed'], mode='lines', line=dict(color='blue', width=2), name="Vattentemp"))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed']+0.25, mode='lines', line=dict(width=0), showlegend=False, visible='legendonly'))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed']-0.25, mode='lines', fill='tonexty', fillcolor='rgba(255,165,0,0.1)', line=dict(width=0), name="Ambient ±0.25°C", visible='legendonly'))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['amb_smoothed'], mode='lines', line=dict(color='orange', dash='dash'), name="Ambient"))
            fig.add_trace(go.Scattergl(x=p['Time'], y=p['flowLph flowLogS'], mode='lines', name="Flöde", yaxis="y2", line=dict(color='red', width=1), opacity=0.3))
            fig.update_layout(height=500, yaxis2=dict(overlaying='y', side='right'), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, width='stretch')

            st.divider()
            st.subheader("🧮 Flödeskalkylator")
            m_amb, m_pipe = p['amb_smoothed'].mean(), p['temperature flowLogS'].mean()
            c_calc, c_img = st.columns([1, 1.5])
            with c_calc:
                st.markdown('<div class="result-card">', unsafe_allow_html=True)
                k = st.number_input("K-faktor", value=1.0, min_value=0.1, step=0.1, key=f"k_{key}_{idx}")
                ta = st.number_input("Rumstemp", float(m_amb), step=0.1, key=f"ta_{key}_{idx}")
                tp = st.number_input("Rörtemp", float(m_pipe), step=0.1, key=f"tp_{key}_{idx}")
                ti = st.number_input("Inkommande", 8.0, step=0.1, key=f"ti_{key}_{idx}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            flow = k * ((ta - tp) / (tp - ti)) if (tp - ti) != 0 else 0.0
            with c_img:
                st.metric("Beräknat Flöde", f"{flow:.2f} L/h")
                st.markdown(f'<div class="pipe-container"><div class="label label-ambient">Rum: {ta:.1f}°C</div><div class="pipe">Uppmätt: {tp:.1f}°C</div><div class="label label-incoming">Inkommande: {ti:.1f}°C</div></div>', unsafe_allow_html=True)

        with tab1: render_content(diff_p, "t1")
        with tab2: render_content(overlap_p, "t2")
