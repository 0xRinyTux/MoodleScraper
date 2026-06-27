# 🚀 MoodleScraper

Un downloader asincrono ad alte prestazioni per Moodle, dotato di un'interfaccia terminale interattiva (TUI). Questo strumento automatizza il download dei materiali del corso superando la lentezza dei classici scraper sequenziali.

---

## ✨ Funzionalità principali

* ⚡ **Discovery Concorrente**: Risolve reindirizzamenti, risorse e strutture delle cartelle in parallelo usando `aiohttp` e `asyncio.gather`, riducendo i tempi di attesa da minuti a pochissimi secondi.
* 📦 **Smart Caching**: Salva la struttura del corso in un file JSON locale (`.moodle_cache.json`). Se riavvii lo script, la mappatura è istantanea.
* 🎨 **TUI Interattiva**: Seleziona visivamente quali sezioni del corso scaricare tramite caselle di controllo (`InquirerPy`) navigabili con le frecce della tastiera.
* 📊 **Dashboard in tempo reale**: Interfaccia grafica integrata nel terminale (`rich`) che mostra contemporaneamente la barra di avanzamento globale e un pannello auto-scorrimento con i log live dei file.
* 🛡️ **Ottimizzazione di Rete**: Gestione intelligente delle connessioni parallele tramite semafori configurabili per scaricare alla massima velocità consentita dalla tua banda.

---

## 🛠️ Requisiti e Installazione

Assicurati di avere **Python 3.10+** installato sul tuo sistema.

1. **Clona il repository**:
   ```bash
   git clone [https://github.com/0xRinyTux/MoodleScraper.git](https://github.com/0xRinyTux/MoodleScraper.git)
   cd MoodleScraper
   ```

2. **Crea e attiva un ambiente virtuale** (consigliato):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Su Windows usa: .venv\Scripts\activate
   ```

3. **Installa le dipendenze**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 Come usarlo

Esegui lo script principale dal terminale:

```bash
python moodle_dl.py
```

### 🔑 Come recuperare il cookie `MoodleSession`
Per accedere ai file del corso, lo script ha bisogno del tuo cookie di sessione (non memorizza le tue credenziali):
1. Apri il browser e vai sulla pagina del corso Moodle.
2. Premi `F12` (o tasto destro -> *Ispeziona*) per aprire i Developer Tools.
3. Vai alla scheda **Applicazione** (o **Archiviazione** / **Storage** a seconda del browser).
4. Nel menu a sinistra espandi la voce **Cookie** e seleziona l'URL di Moodle.
5. Cerca la riga con il nome **`MoodleSession`** e copia il suo valore (una stringa alfanumerica).
6. Incolla il valore nel terminale quando richiesto dallo script.

---

## ⚙️ Opzioni della riga di comando

Puoi personalizzare il comportamento dello script usando i seguenti flag:

| Flag | Descrizione | Default |
| :--- | :--- | :--- |
| `--workers <int>` | Numero di download simultanei da gestire in parallelo. | `32` |
| `--output <path>` | Cartella di destinazione in cui salvare i file ordinati. | `Corso` |
| `--refresh` | Ignora la cache JSON locale e forza una nuova discovery sul sito. | *Disattivato* |

*Esempio per scaricare con 64 connessioni simultanee in una cartella specifica:*
```bash
python scrapeCourseMoodle.py --workers 64 --output "Materiale_Universita"
```

---

## 📝 Licenza e Disclaimer

Questo progetto è stato sviluppato esclusivamente a scopo didattico e personale. L'autore non si assume alcuna responsabilità per un eventuale uso improprio dello strumento o per violazioni dei termini di servizio della piattaforma e-learning. Si prega di utilizzare il tool in modo responsabile per non sovraccaricare i server universitari.
