#!/usr/bin/env python3

import argparse
import asyncio
import os
import time

import aiohttp
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.validator import PathValidator

from .auth import load_or_perform_login
from .discovery import discover_course, get_courses
from .downloader import run_downloads
from .utils import SETTINGS_FILE, load_json, sanitize, save_json

async def main_async():
    parser = argparse.ArgumentParser(description="Moodle Fast Downloader Pro - Modular")
    parser.add_argument("--workers", type=int, default=32, help="Numero di download concorrenti")
    parser.add_argument("--output", default="", help="Cartella radice personalizzata da CLI")
    args = parser.parse_args()

    jar = aiohttp.CookieJar(unsafe=True)
    
    # Custom User-Agent to avoid "python3.12/aiohttp" in email notifications
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    async with aiohttp.ClientSession(cookie_jar=jar, headers=headers) as session:
        if not await load_or_perform_login(session):
            print("[!] Autenticazione fallita. Chiusura.")
            return

        settings = load_json(SETTINGS_FILE) or {}
        use_cache = settings.get("cache_courses", False)

        print("\n[*] Analisi della Home Page ed estrazione dei corsi caricati...")
        courses = await get_courses(session)
        
        if not courses:
            print("[!] Nessun corso iscritto rilevato.")
            return

        course_choices = [Choice(value="ALL", name="🌟 [SELEZIONA TUTTI I CORSI]")]
        course_choices.extend([Choice(value=idx, name=c["name"]) for idx, c in enumerate(courses)])

        selected_course_idx = await inquirer.fuzzy(
            message="Cerca e seleziona i corsi da elaborare:",
            choices=course_choices,
            multiselect=True,
            prompt="🔎 > ",
            instruction="(TAB = seleziona, INVIO = conferma)",
            border=True,
        ).execute_async()

        if not selected_course_idx:
            return

        if "ALL" in selected_course_idx:
            selected_course_idx = list(range(len(courses)))

        print(f"\n[⚡] Avvio Mappatura Parallela Asincrona per {len(selected_course_idx)} corsi...")
        
        # --- TIMER START ---
        start_time = time.perf_counter()
        
        discovery_semaphore = asyncio.Semaphore(15)
        mapping_tasks = [
            discover_course(session, courses[idx]["url"], discovery_semaphore, use_cache) 
            for idx in selected_course_idx
        ]
        results_per_course = await asyncio.gather(*mapping_tasks)
        
        # --- TIMER END ---
        elapsed = time.perf_counter() - start_time
        print(f"[⏱️] Mappatura completata in {elapsed:.2f} secondi.")

        # --- GESTIONE E SELEZIONE DEL PATH DI DESTINAZIONE (UNA VOLTA PER ESECUZIONE) ---
        base_download_dir = ""
        if args.output:
            base_download_dir = args.output
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            
            saved_path = settings.get("default_download_dir", "")
            always_ask_path = settings.get("always_ask_path", True)
            
            # Se c'è un path salvato e l'utente ha scelto di NON chiedere ogni volta, usalo direttamente
            if saved_path and not always_ask_path:
                base_download_dir = saved_path
                print(f"[⚙️] Utilizzo il path predefinito salvato: {base_download_dir}")
            else:
                print("\n[💡 SHORTCUT TERMINALE]")
                print(" -> Per saltare questo pop-up da CLI usa: python3 main.py --output /tuo/path")
                print(" -> Oppure imposta \"always_ask_path\": false dentro il file settings.json\n")
                
                choices = []
                if saved_path:
                    choices.append(Choice(value="saved", name=f"💾 Usa il path salvato nei settings ({saved_path})"))
                choices.extend([
                    Choice(value="parent", name=f"📁 Cartella superiore/padre ({parent_dir}/)"),
                    Choice(value="current", name=f"📍 Cartella corrente da cui esegui lo script ({os.getcwd()}/)"),
                    Choice(value="custom", name="✏️ Inserisci un percorso personalizzato..."),
                ])
                
                path_choice = await inquirer.select(
                    message="Dove desideri salvare i file dei corsi?",
                    choices=choices,
                    border=True
                ).execute_async()
                
                if path_choice == "saved":
                    base_download_dir = saved_path
                elif path_choice == "parent":
                    base_download_dir = parent_dir
                elif path_choice == "current":
                    base_download_dir = os.getcwd()
                else:
                    base_download_dir = await inquirer.text(
                        message="Digita il percorso personalizzato (relativo o assoluto):",
                        validate=PathValidator(is_dir=False, message="Il percorso inserito non è valido"),
                        default=saved_path if saved_path else (os.path.expanduser("~/Downloads") if os.path.exists(os.path.expanduser("~/Downloads")) else "")
                    ).execute_async()
                
                # Se il percorso selezionato è nuovo/diverso da quello salvato, offre di memorizzarlo
                if os.path.abspath(base_download_dir) != (os.path.abspath(saved_path) if saved_path else ""):
                    save_choice = await inquirer.confirm(
                        message="Vuoi salvare questo percorso come predefinito in settings.json?",
                        default=True
                    ).execute_async()
                    
                    if save_choice:
                        settings["default_download_dir"] = os.path.abspath(base_download_dir)
                        hide_popup = await inquirer.confirm(
                            message="Vuoi nascondere questo pop-up nelle prossime esecuzioni ed usare sempre questo path?",
                            default=False
                        ).execute_async()
                        settings["always_ask_path"] = not hide_popup
                        save_json(SETTINGS_FILE, settings)
                        print("[✓] Impostazioni salvate correttamente in settings.json!")

        base_download_dir = os.path.abspath(base_download_dir)

        moodle_cookie_str = ""
        for cookie in session.cookie_jar:
            if cookie.key == "MoodleSession":
                moodle_cookie_str = cookie.value
                break

        for original_idx, sections in zip(selected_course_idx, results_per_course):
            course = courses[original_idx]
            valid_sections = [s for s in sections if s.downloads]

            if not valid_sections:
                print(f"\n[!] Nessun file scaricabile trovato nel corso: {course['name']}")
                continue

            print(f"\n[{course['name']}]")
            section_choices = [Choice(value="ALL", name="🌟 [SELEZIONA TUTTI I FILE]")]
            section_choices.extend([Choice(value=s_idx, name=f"{s.name} ({len(s.downloads)} file)") for s_idx, s in enumerate(valid_sections)])
            
            selected_section_idx = await inquirer.fuzzy(
                message=f"Seleziona le sezioni da scaricare:",
                choices=section_choices,
                multiselect=True,
                prompt="🔎 > ",
                instruction="(TAB = seleziona, INVIO = conferma)",
                border=True,
            ).execute_async()

            if not selected_section_idx:
                continue

            if "ALL" in selected_section_idx:
                selected_section_idx = list(range(len(valid_sections)))

            items_to_download = []
            for s_idx in selected_section_idx:
                items_to_download.extend(valid_sections[s_idx].downloads)

            course_dir_name = sanitize(course["name"])
            course_dir = os.path.join(base_download_dir, course_dir_name)
            
            print(f"[*] I file verranno salvati in: {os.path.abspath(course_dir)}")
            print(f"[*] Avvio download di {len(items_to_download)} elementi per {course['name']}...")
            await run_downloads(items_to_download, moodle_cookie_str, course_dir, args.workers)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n[!] Operazione annullata dall'utente.")


if __name__ == "__main__":
    main()
