#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import List

import aiohttp
from bs4 import BeautifulSoup
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TransferSpeedColumn,
)

COURSE_URL = "https://elearning.informatica.unisa.it/el-platform/course/view.php?id=1175"
CACHE_FILE = ".moodle_cache.json"

@dataclass
class DownloadItem:
    url: str
    path: str
    filename: str = ""

@dataclass
class Section:
    name: str
    downloads: List[DownloadItem]

def sanitize(name: str) -> str:
    for c in '<>:"/\\|?*':
        name = name.replace(c, "_")
    return name.replace("\n", " ").strip()

def extract_filename(response: aiohttp.ClientResponse) -> str:
    cd = response.headers.get("Content-Disposition", "")
    m = re.search(r'filename="?([^"]+)"?', cd)
    if m:
        return sanitize(m.group(1))
    return sanitize(str(response.url).split("/")[-1].split("?")[0])

async def fetch_folder_items(session: aiohttp.ClientSession, folder_url: str, section_name: str, folder_name: str) -> List[DownloadItem]:
    try:
        async with session.get(folder_url) as r:
            r.raise_for_status()
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            fm = soup.select_one("div.filemanager")
            if not fm:
                return []
            
            items = []
            for a in fm.select("a[href*='pluginfile.php']"):
                href = a["href"]
                filename = sanitize(a.get_text(" ", strip=True))
                items.append(
                    DownloadItem(
                        url=href,
                        path=os.path.join(section_name, folder_name, filename),
                        filename=filename
                    )
                )
            return items
    except Exception:
        return []

async def resolve_resource(session: aiohttp.ClientSession, url: str, section_name: str) -> DownloadItem:
    try:
        # Stream=True equivalente asincrono per leggere solo gli header ed evitare il download completo in discovery
        async with session.get(url, allow_redirects=True) as r:
            filename = extract_filename(r)
            if not filename or filename.endswith(".php"):
                filename = "documento_sconosciuto.pdf"
            
            return DownloadItem(
                url=str(r.url),
                path=os.path.join(section_name, filename),
                filename=filename
            )
    except Exception:
        return None

async def discover_course(cookie: str) -> List[Section]:
    jar = aiohttp.CookieJar(unsafe=True)
    jar.update_cookies({"MoodleSession": cookie})
    
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        print("[*] Connessione a Moodle in corso...")
        async with session.get(COURSE_URL) as r:
            r.raise_for_status()
            html = await r.text()
            
        soup = BeautifulSoup(html, "html.parser")
        sections_data = []
        tasks = []
        
        print("[*] Mappatura risorse concorrente avviata...")
        
        for section_div in soup.select("div.section-item"):
            title_el = section_div.select_one("h3.sectionname a")
            if not title_el:
                continue
                
            section_name = sanitize(title_el.get_text(strip=True))
            current_section_idx = len(sections_data)
            sections_data.append(Section(name=section_name, downloads=[]))
            
            for activity in section_div.select("li.activity"):
                a = activity.select_one("a[href]")
                if not a:
                    continue
                    
                href = a["href"]
                activity_name = sanitize(a.get_text(" ", strip=True).replace(" File", "").replace(" Cartella", ""))
                
                if "/mod/resource/" in href:
                    tasks.append((current_section_idx, resolve_resource(session, href, section_name)))
                elif "/mod/folder/" in href:
                    tasks.append((current_section_idx, fetch_folder_items(session, href, section_name, activity_name)))

        # Risoluzione concorrente di tutti gli URL e redirect (il vero collo di bottiglia)
        resolved_results = await asyncio.gather(*(t[1] for t in tasks))
        
        for (section_idx, _), result in zip(tasks, resolved_results):
            if result:
                if isinstance(result, list):
                    sections_data[section_idx].downloads.extend(result)
                else:
                    sections_data[section_idx].downloads.append(result)
                    
        return sections_data

def load_cache() -> List[Section]:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Section(name=s["name"], downloads=[DownloadItem(**d) for d in s["downloads"]]) for s in data]
    except Exception:
        return None

def save_cache(sections: List[Section]):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump([asdict(s) for s in sections], f, indent=2)

async def download_worker(
    session: aiohttp.ClientSession, 
    semaphore: asyncio.Semaphore, 
    item: DownloadItem, 
    output_dir: str, 
    progress: Progress, 
    task_id: TaskID,
    logs: List[str]
) -> str:
    async with semaphore:
        path = os.path.join(output_dir, item.path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        if os.path.exists(path):
            logs.append(f"[yellow]Saltato (Esistente):[/yellow] {item.filename}")
            progress.advance(task_id)
            return "skip"
            
        try:
            async with session.get(item.url) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('Content-Length', 0))
                
                with open(path, "wb") as f:
                    async for chunk in r.content.iter_chunked(65536):
                        f.write(chunk)
                        
            logs.append(f"[green]✓ Completato:[/green] {item.filename}")
            progress.advance(task_id)
            return "ok"
        except Exception as e:
            logs.append(f"[red]✗ Errore ({item.filename}):[/red] {str(e)}")
            progress.advance(task_id)
            return "err"

async def run_downloads(items: List[DownloadItem], cookie: str, output_dir: str, workers: int):
    semaphore = asyncio.Semaphore(workers)
    jar = aiohttp.CookieJar(unsafe=True)
    jar.update_cookies({"MoodleSession": cookie})
    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TextColumn("({task.completed}/{task.total})"),
        TransferSpeedColumn(),
    )
    
    task_id = progress.add_task("[cyan]Download in corso...", total=len(items))
    logs = []
    
    # Layout della UI
    def generate_layout():
        recent_logs = "\n".join(logs[-8:]) if logs else "In attesa..."
        log_panel = Panel(recent_logs, title="Logs (Ultimi eventi)", height=10, style="dim")
        progress_panel = Panel(progress, title="Progresso Download")
        return Group(log_panel, progress_panel)

    async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:
        # Usa rich.Live per aggiornare contemporaneamente log e barra di progresso
        with Live(generate_layout(), refresh_per_second=10) as live:
            
            # Aggiornamento UI asincrono
            async def update_ui():
                while not progress.finished:
                    live.update(generate_layout())
                    await asyncio.sleep(0.1)
                live.update(generate_layout())

            ui_task = asyncio.create_task(update_ui())
            
            dl_tasks = [
                download_worker(session, semaphore, item, output_dir, progress, task_id, logs)
                for item in items
            ]
            
            results = await asyncio.gather(*dl_tasks)
            await ui_task

    print("\n[bold green]Download Completato![/bold green]")
    print(f"Scaricati: {sum(r == 'ok' for r in results)}")
    print(f"Saltati:   {sum(r == 'skip' for r in results)}")
    print(f"Errori:    {sum(r == 'err' for r in results)}")

def main():
    parser = argparse.ArgumentParser(description="Moodle Fast Downloader")
    parser.add_argument("--workers", type=int, default=32, help="Numero di download concorrenti")
    parser.add_argument("--output", default="Corso", help="Cartella di output")
    parser.add_argument("--refresh", action="store_true", help="Forza il refresh della cache")
    args = parser.parse_args()

    # Controllo Cache
    sections = None
    if not args.refresh:
        sections = load_cache()
        if sections:
            print("[✓] Cache trovata e caricata correttamente.")

    if not sections:
        cookie = input("Inserisci il MoodleSession cookie: ").strip()
        sections = asyncio.run(discover_course(cookie))
        save_cache(sections)
        print("[✓] Discovery completata e salvata in cache.\n")
    else:
        # Se carica da cache, potrebbe non avere il cookie che servirà per il download
        cookie = input("Inserisci il MoodleSession cookie (per i download): ").strip()

    # Filtro sezioni vuote per la TUI
    valid_sections = [s for s in sections if s.downloads]
    
    if not valid_sections:
        print("Nessun file trovato in questo corso.")
        return

    # TUI per la selezione: Usiamo l'indice 'i' come 'value' invece dell'oggetto 's'
    choices = [
        Choice(value=i, name=f"{s.name} ({len(s.downloads)} file)") 
        for i, s in enumerate(valid_sections)
    ]
    
    selected_indices = inquirer.checkbox(
        message="Seleziona le sezioni da scaricare (Spazio: seleziona, Invio: conferma, A: seleziona tutto):",
        choices=choices,
        instruction="(Usa le frecce per muoverti)",
    ).execute()

    if not selected_indices:
        print("Nessuna sezione selezionata. Uscita.")
        return

    items_to_download = []
    # Recuperiamo gli oggetti usando gli indici selezionati
    for i in selected_indices:
        items_to_download.extend(valid_sections[i].downloads)

    print(f"\nHai selezionato {len(items_to_download)} file da scaricare.\n")

    # Avvio Download Concorrente
    asyncio.run(run_downloads(items_to_download, cookie, args.output, args.workers))

if __name__ == "__main__":
    main()