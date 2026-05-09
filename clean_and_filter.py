import os
import pandas as pd
import duckdb
import numpy as np

def process_files():
    input_dir = "2026 - Quandify"
    output_dir = "cleaned_data"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    csv_files = sorted([f for f in os.listdir(input_dir) if f.endswith('.csv')])
    
    print(f"Hittade {len(csv_files)} filer. Påbörjar rensning...")
    
    summary = []
    # Globala räknare för de olika stegen
    total_stats = {
        "initial": 0,
        "removed_missing_cols": 0,
        "removed_signal": 0,
        "removed_temp_range": 0,
        "removed_global_val": 0,
        "kept": 0
    }

    for file in csv_files:
        input_path = os.path.join(input_dir, file)
        
        try:
            # 1. Läs in data
            con = duckdb.connect(':memory:')
            df = con.execute(f"SELECT * FROM read_csv_auto('{input_path}', all_varchar=true)").df()
            rows_before = len(df)
            total_stats["initial"] += rows_before
            
            # Kolumnnamn
            col_temp = 'temperature flowLogS'
            col_ambient = 'ambientTemperature flowLogS'
            col_signal = 'signalStrength flowLogS'
            col_flow = 'flowLph flowLogS'
            
            # Kontrollera att kolumner finns
            missing_cols = [c for c in [col_temp, col_ambient, col_signal, col_flow] if c not in df.columns]
            if missing_cols:
                print(f"❌ Skippar {file}: Saknar kolumner {missing_cols}")
                total_stats["removed_missing_cols"] += rows_before
                continue

            for col in [col_temp, col_ambient, col_signal, col_flow]:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            
            # --- FILTRERING ---
            
            # Steg 1: Signalstyrka
            low_signal_indices = df.index[df[col_signal] < 99].tolist()
            indices_to_remove = set()
            for idx in low_signal_indices:
                indices_to_remove.update([idx - 1, idx, idx + 1])
            
            indices_to_remove = [i for i in indices_to_remove if i in df.index]
            rows_before_signal = len(df)
            df = df.drop(index=indices_to_remove)
            removed_in_signal = rows_before_signal - len(df)
            total_stats["removed_signal"] += removed_in_signal
            
            # Steg 2: Vattentemperatur (0.1 till 70 grader)
            rows_before_temp = len(df)
            df = df[(df[col_temp] >= 0.1) & (df[col_temp] <= 70)]
            removed_in_temp = rows_before_temp - len(df)
            total_stats["removed_temp_range"] += removed_in_temp
            
            if df.empty:
                print(f"⚠ Filen {file} blev tom efter rad-filtrering.")
                continue

            # Steg 3: Global validering (Ambient vs Vatten)
            mean_ambient = df[col_ambient].ffill().bfill().mean()
            mean_water = df[col_temp].mean()
            
            if mean_ambient < mean_water:
                print(f"❌ FIL FÖRKASTAD: {file} (Ambient {mean_ambient:.2f} < Vatten {mean_water:.2f})")
                total_stats["removed_global_val"] += len(df)
                continue
            
            # --- SPARA ---
            output_filename = f"{len(summary) + 1:02d}_{file.replace('.csv', '.parquet')}"
            output_path = os.path.join(output_dir, output_filename)
            df.to_parquet(output_path)
            
            rows_after = len(df)
            total_stats["kept"] += rows_after
            
            pct_kept = (rows_after / rows_before) * 100
            print(f"✔ FIL GODKÄND: {output_filename} ({pct_kept:.1f}% behållet)")
            
            summary.append({"file": output_filename, "rows_after": rows_after})

        except Exception as e:
            print(f"❌ Fel vid bearbetning av {file}: {e}")

    # --- TOTAL RAPPORT ---
    print("\n" + "="*45)
    print("📊 TOTAL RAPPORT - DATARENSNING")
    print("="*45)
    
    ti = total_stats["initial"]
    if ti > 0:
        print(f"Totalt antal rader in:       {ti:12,}")
        print("-" * 45)
        
        rmc = total_stats["removed_missing_cols"]
        rs = total_stats["removed_signal"]
        rt = total_stats["removed_temp_range"]
        rg = total_stats["removed_global_val"]
        rk = total_stats["kept"]
        
        print(f"1. Saknade kolumner/data:    {rmc:12,} ({ (rmc/ti)*100:5.1f}%)")
        print(f"2. Signalstyrka:             {rs:12,} ({ (rs/ti)*100:5.1f}%)")
        print(f"3. Temperaturintervall:      {rt:12,} ({ (rt/ti)*100:5.1f}%)")
        print(f"4. Global validering:        {rg:12,} ({ (rg/ti)*100:5.1f}%)")
        print("-" * 45)
        print(f"TOTALT BEHÅLLNA RADER:       {rk:12,} ({ (rk/ti)*100:5.1f}%)")
        print(f"TOTALT BORTTAGNA RADER:      {ti-rk:12,} ({ ((ti-rk)/ti)*100:5.1f}%)")
        print("="*45)
        print(f"Antal godkända filer: {len(summary)}")
    else:
        print("Ingen data kunde bearbetas.")

if __name__ == "__main__":
    process_files()
