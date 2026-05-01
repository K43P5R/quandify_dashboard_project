import os
import pandas as pd
import duckdb
import numpy as np

def process_files():
    input_dir = "2026 - Quandify"
    output_dir = "cleaned_data"
    
    csv_files = [f for f in os.listdir(input_dir) if f.endswith('.csv')]
    
    print(f"Hittade {len(csv_files)} filer. Påbörjar rensning...")
    
    summary = []

    for file in csv_files:
        input_path = os.path.join(input_dir, file)
        
        try:
            # 1. Läs in data med DuckDB (snabbt och korrekt typat)
            con = duckdb.connect(':memory:')
            df = con.execute(f"SELECT * FROM read_csv_auto('{input_path}', all_varchar=true)").df()
            
            # Konvertera relevanta kolumner till numeriska värden
            col_temp = 'temperature flowLogS'
            col_ambient = 'ambientTemperature flowLogS'
            col_signal = 'signalStrength flowLogS'
            col_flow = 'flowLph flowLogS'
            
            for col in [col_temp, col_ambient, col_signal, col_flow]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            
            # --- FILTRERING ---
            
            # 2. Signalstyrka: Ta bort < 100 samt raden före och efter
            # Hitta index för rader med signal < 100
            low_signal_indices = df.index[df[col_signal] < 100].tolist()
            
            # Skapa ett set av index att ta bort (index, index-1, index+1)
            indices_to_remove = set()
            for idx in low_signal_indices:
                indices_to_remove.update([idx - 1, idx, idx + 1])
            
            # Ta bort dessa index (filtrera bort de som hamnar utanför df.index)
            indices_to_remove = [i for i in indices_to_remove if i in df.index]
            df = df.drop(index=indices_to_remove)
            
            # 3. Vattentemperatur: 0.1 till 70 grader
            df = df[(df[col_temp] >= 0.1) & (df[col_temp] <= 70)]
            
            if df.empty:
                print(f"⚠ Filen {file} blev tom efter rad-filtrering. Skippar.")
                continue

            # 4. Global validering: Medelvärde Ambient vs Vattentemp
            # Vi fyller i ambient temporärt för att få ett rättvist medelvärde över hela filen
            mean_ambient = df[col_ambient].ffill().bfill().mean()
            mean_water = df[col_temp].mean()
            
            if mean_ambient < mean_water:
                print(f"❌ FIL FÖRKASTAD: {file} (Ambient {mean_ambient:.2f} < Vatten {mean_water:.2f})")
                continue
            
            # --- SPARA ---
            output_path = os.path.join(output_dir, file.replace('.csv', '.parquet'))
            df.to_parquet(output_path)
            print(f"✔ FIL GODKÄND: {file} ({len(df)} rader kvar)")
            summary.append({"file": file, "status": "Cleaned", "rows": len(df)})

        except Exception as e:
            print(f"❌ Fel vid bearbetning av {file}: {e}")

    print("\n--- Rensning klar ---")
    print(f"Totalt antal godkända filer: {len(summary)}")

if __name__ == "__main__":
    process_files()
