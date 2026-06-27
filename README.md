# 🎓 Moodle Fast Downloader Pro

Un tool a riga di comando (CLI) altamente ottimizzato per l'estrazione e il download asincrono del materiale didattico dalle piattaforme Moodle (ottimizzato per l'Università degli Studi di Salerno - UNISA). 

Progettato con un'architettura modulare, questo script riduce i tempi di interazione del 90% grazie al lazy-loading e massimizza l'efficienza di rete tramite download paralleli e controlli di ridondanza.

---

## ✨ Caratteristiche Principali

* 🚀 **Estremamente Veloce:** Implementa `aiohttp` e `asyncio` per mappare i corsi e scaricare i file in parallelo, sfruttando al massimo la larghezza di banda.
* 🧠 **Lazy-Loading & Zero-Spam:** Analizza la struttura dei corsi esclusivamente tramite il parsing del DOM HTML principale. Non effettua richieste HTTP superflue ai file prima dell'effettivo momento del download, prevenendo ban e sovraccarichi al server universitario.
* 🎯 **Interattivo e Selettivo:** Grazie a `InquirerPy`, offre un'interfaccia terminale per cercare (fuzzy-search) e selezionare in modo granulare i corsi e le specifiche sezioni da scaricare.
* ♻️ **Smart Caching (Idempotenza):** Controlla i percorsi di destinazione locali in tempo reale; se un file esiste già, viene automaticamente saltato per risparmiare tempo e dati.
* 🎨 **UI Terminale Moderna:** Utilizza `rich` per fornire barre di avanzamento grafiche, misurazione della velocità di trasferimento e un pannello di logging pulito.
* ⚙️ **Configurazione Flessibile:** Supporta la personalizzazione del percorso di download tramite CLI interattiva o in modo persistente nel file `settings.json`.

---

## 🛠️ Requisiti

* **Python 3.8+**
* Le dipendenze elencate nel file `requirements.txt`.

---

## 📦 Installazione

1. Clona la repository sul tuo ambiente locale:
   ```bash
   git clone [https://github.com/0xRinyTux/MoodleScraper.git](https://github.com/0xRinyTux/MoodleScraper.git)
   cd MoodleScraper
   ```

2. (Opzionale ma consigliato) Crea e attiva un ambiente virtuale:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Su Linux/macOS
   # .venv\Scripts\activate   # Su Windows
   ```

3. Installa le dipendenze richieste:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 Utilizzo

Per avviare lo strumento in modalità interattiva, esegui semplicemente:

```bash
python3 moodle_unisa_dl/main.py
```

Al primo avvio, ti verranno richieste le credenziali di accesso (che verranno salvate in locale in modo sicuro per le sessioni successive) e la cartella predefinita in cui salvare i file dei corsi.

### Argomenti CLI Avanzati

Puoi bypassare i menu interattivi e automatizzare l'esecuzione passando parametri espliciti da riga di comando:

| Argomento | Tipo | Default | Descrizione |
| :--- | :--- | :--- | :--- |
| `--workers` | Intero | `32` | Definisce il numero massimo di download concorrenti. |
| `--output` | Stringa | N/A | Imposta direttamente il path della cartella di destinazione, ignorando i prompt interattivi e il file di configurazione. |

**Esempio:**
```bash
python3 moodle_unisa_dl/main.py --workers 16 --output /percorso/personalizzato/esami
```

---

## 🏗️ Struttura del Progetto

Il progetto è suddiviso nei seguenti moduli per garantire scalabilità e pulizia del codice:

* `main.py` - Orchestratore principale e gestione degli argomenti/UI.
* `auth.py` - Gestione del login, cookie e sessioni persistenti.
* `discovery.py` - Scraping asincrono e parsing HTML per l'estrazione dei metadati di corsi, sezioni e file.
* `downloader.py` - Core asincrono per il download dei file, risoluzione degli header HTTP on-the-fly e gestione dell'UI grafica.
* `models.py` - Classi di dati strutturati (`DownloadItem`, `Section`).
* `utils.py` - Funzioni di supporto, sanificazione dei nomi dei file e gestione I/O dei file JSON.

---

## ⚠️ Disclaimer e Uso Responsabile

Questo strumento è stato creato a scopo puramente educativo e per facilitare l'organizzazione del materiale accademico agli studenti. 
Si prega di utilizzarlo in modo responsabile. **Non impostare un numero di workers esageratamente alto** per evitare di saturare i server dell'Università, comportandosi a tutti gli effetti come un attacco DoS. L'autore non si assume alcuna responsabilità per l'uso improprio dello script o per eventuali violazioni dei termini di servizio della piattaforma ospitante.
