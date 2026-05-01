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

### 1. Ingestion och Rening (`convert_data.py`)
Rådata (CSV) konverteras till Parquet med DuckDB. 
* **Rening:** Filtrerar bort dåliga installationer (`signalStrength < 100`).
* **Typning:** Säkerställer att `Time` är TIMESTAMP och numeriska värden är FLOAT.
* **Flöde:** `flowLph` bibehålls med originalvärden (inga absolutbelopp) för att kunna identifiera felmonteringar eller backflöden.

### 2. Analys av Känd Läcka (`analyze_leak.py`)
Vi använder en specifik fil med en bekräftad läcka för att kalibrera modellen. 
* **Logik:** Identifierar nollflödesperioder (>40 min) och beräknar $k$ samt $R^2$ för varje fönster.
* **Resultat:** En god passform ($R^2 > 0.8$) bekräftar att Newtons lag är tillämpbar på systemet.

### 3. Skalning och Dashboard (`generate_dashboard_data.py` & `app.py`)
Processering av ca 8 000 nollflödesperioder över 49 enheter.
* **Master-fil:** Sammanställer $k$-värden och anomalier i `summary_stats.csv`.
* **Dashboard:** En Streamlit-applikation för interaktiv analys av trender och visualisering av rådata för specifika enheter.

## 7. Instruktioner för körning
1. **Miljö:** Skapa och aktivera venv: `python -m venv venv` och `source venv/bin/activate`
2. **Installation:** `pip install duckdb pandas streamlit matplotlib plotly`
3. **Konvertering:** `python convert_data.py`
4. **Analys:** `python generate_dashboard_data.py`
5. **Dashboard:** `streamlit run app.py`

---