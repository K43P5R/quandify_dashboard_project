# Quandify Thermal Leak Analytics

## Projektets syfte
Att detektera mikroläckage i vattenledningar genom att analysera termodynamisk konvergens istället för enbart flödeströsklar. Genom att mäta hur snabbt vattentemperaturen rör sig mot omgivningens temperatur kan läckor under 20 L/h identifieras, vilket skapar stort värde för försäkringsbolag genom tidig upptäckt av vattenskador.

## Teknisk Stack & Modellering
*   **Data:** Effektiv hantering av >86 miljoner rader sensordata med **DuckDB** och **Apache Parquet**.
*   **Analys:** Python (Pandas, NumPy) för linjär regression och statistisk modellering.
*   **Termodynamik:** Baseras på Newtons avsvalningslag för att beräkna systemets avsvalningskonstant ($k$).
*   **Kvantifiering:** Läckageflöde beräknas dynamiskt baserat på $k$, temperaturskillnader och en rörvolym på 0.28 liter:
    $$\text{Flow} = (k \cdot 0.28) \cdot \frac{T_{ambient} - T_{pipe}}{T_{pipe} - T_{incoming}}$$

## Datapipeline
### 1. Rening (`clean_and_filter.py`)
Konverterar rådata till Parquet och utför avancerad filtrering:
*   Fyller i glesa sensordatavärden (ambient temperatur och signalstyrka).
*   Exkluderar perioder med låg signalstyrka ($<99$) och orimliga temperaturintervall.
*   Validerar installationer genom att jämföra medelvärden mellan vatten- och omgivningstemperatur.

### 2. Dashboard & Analys (`dashboard.py`)
En Streamlit-applikation för interaktiv analys av termiska trender:
*   **Konvergenshistorik:** Analyserar upp till 12 timmar bakåt för att hitta dynamiska startpunkter för termisk stabilisering.
*   **Automatiserad K-faktor:** Beräknar automatiskt avsvalningskonstanten via linjär regression på logaritmerad data.
*   **Detektering:** Skiljer mellan normaltillstånd och läckage genom att identifiera avvikelser i den termiska konvergensen.
