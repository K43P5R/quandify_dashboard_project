# Quandify Leak Detection Analysis

## 1. Bakgrund och Affärscase
Quandify utvecklar smarta vattenmätare som installeras utanpå inkommande vattenledningar. Genom att mäta "Time of Flight" för ultraljudssignaler kan enheten detektera vattenflöden med hög precision utan ingrepp i rörsystemet.

### Det kommersiella värdet (Business Case)
Huvudsyftet är att minska kostnaderna för vattenskador, vilket skapar ett starkt incitament för försäkringsbolag.
* **Förebyggande skydd:** Enheterna fungerar som ett "brandlarm för vatten".
* **Ekonomisk nytta:** Genom att installera dessa enheter kan försäkringsbolag sänka premierna för hushållen, då risken för stora skadekostnader (som ofta uppgår till tusentals kr per incident) minskar drastiskt.
* **Teknisk begränsning idag:** Standardlarmet triggas vid ett flöde på >20 L/h i över 45 minuter. Mindre sprickor eller mikroläckor kan dock pågå länge utan att upptäckas av standardalgoritmen.

## 2. Projektbeskrivning och Mål
Syftet med detta projekt är att utveckla en sofistikerad algoritm för läckagedetektering baserat på termodynamik snarare än enbart flödeströsklar.

### Frågeställning
> "Hur kan man detektera läckor i ledningar genom att undersöka hur snabbt vattentemperaturen konvergerar mot den ambienta temperaturen?"

**Huvudmål:**
1. **Validering:** Utvärdera om temperaturkonvergens mot omgivningstemperatur kan användas som en pålitlig indikator för vattenflöde.
2. **Skalbarhet:** Skapa en robust datapipeline för bearbetning av stora mängder sensordata (>50 miljoner rader).
3. **Detektering:** Identifiera mikroläckor genom att sätta en baslinje för temperaturkonvergenshastighet med en feltolerans på ca 10 %.

## 3. Teknisk Stack
* **Språk:** Python
* **Datahantering:** DuckDB (in-memory SQL-processering), Apache Parquet (kolumnbaserad lagring)
* **Analys och Modellering:** Pandas, NumPy (linjär regression)
* **Visualisering:** Streamlit, Plotly

## 4. Sensordata och Dataflöde
Enheten samplar data 4 gånger per sekund och skickar upp medelvärden till molnet var fjärde sekund.

| Header | Beskrivning |
| :--- | :--- |
| **Time** | Datum och tidsstämpel. |
| **ambientTemperature** | Temperaturen i miljön runt röret. |
| **temperature** | Vattnets temperatur inuti röret. |
| **flowLph** | Vattenflöde i liter per timme (L/h). |
| **stDev** | Flödets standardavvikelse baserat på 16 datapunkter. |
| **signalStrength** | Installationskvalitet (värden < 100 exkluderas). |

## 5. Modellering: Newtons avsvalningslag
När vatten står stilla i ett rör kommer dess temperatur ($T$) att röra sig mot omgivningens temperatur ($T_{amb}$) enligt en differentiell avkylningsmodell.

### Matematiskt angreppssätt
Vi modellerar avsvalningen med följande ekvation:
$$T(t) = T_{ambient} + (T_0 - T_{ambient})e^{-kt}$$

Genom att logaritmera temperaturskillnaden kan vi använda linjär regression för att hitta avsvalningskonstanten $k$:
$$\ln(|T - T_{ambient}|) = -kt + \ln(\Delta T_0)$$

* **$k$:** Beskriver hur snabbt vattnet svalnar. Ett stabilt rör vid nollflöde bör ha ett konstant $k$-värde.
* **Avvikelse:** Om det faktiska $k$-värdet avviker signifikant (t.ex. >10 %) tyder det på att nytt vatten tillförs via en läcka, vilket stör den naturliga konvergensen.

## 6. Genomförda Steg och Pipeline

### 1. Ingestion och Rening (`clean_and_filter.py`)
Rådata (CSV) från mappen `2026 - Quandify` konverteras till Parquet med DuckDB för snabbare åtkomst.
* **Gles data:** Fyller i (forward/backward fill) värden för omgivningstemperatur och signalstyrka som ofta samplas mer sällan.
* **Rening:** 
    * Tar bort rader med låg signalstyrka (`signalStrength < 99`) samt närliggande datapunkter för att undvika brus.
    * Filtrerar bort orimliga vattentemperaturer (utanför intervallet 0.1 - 70°C).
* **Global Validering:** Förkastar hela filer där medeltemperaturen på vattnet är högre än omgivningen (vilket tyder på felaktig installation eller mätfel).
* **Export:** Sparar rensad data i `cleaned_data/`.

### 2. Analys och Visualisering (`dashboard.py`)
En interaktiv Streamlit-dashboard som utför analys i realtid.
* **Detektering:** Identifierar stabila perioder (nollflöde) och letar efter avvikelser där vattentemperaturen inte konvergerar mot omgivningen ("Thermal Leak").
* **K-Faktor Beräkning:** Använder linjär regression på logaritmerade temperaturskillnader för att automatiskt beräkna avsvalningskonstanten ($k$).
* **Läckagekalkylator:** Beräknar ett estimerat läckageflöde (L/h) baserat på den termiska modellen:
  $$\text{Flow} = k \cdot \frac{T_{ambient} - T_{pipe}}{T_{pipe} - T_{incoming}}$$

## 7. Instruktioner för körning
1. **Miljö:** Skapa och aktivera venv: `python -m venv venv` och `source venv/bin/activate`
2. **Installation:** `pip install -r requirements.txt` (Säkerställ att `duckdb`, `pandas`, `streamlit`, `plotly` och `pyarrow` finns med).
3. **Datahantering:** Kör rensningsskriptet för att förbereda data:
   ```bash
   python clean_and_filter.py
   ```
4. **Starta Dashboard:**
   ```bash
   streamlit run dashboard.py
   ```

---