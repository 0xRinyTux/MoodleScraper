import asyncio
import os
import re
from typing import List

import aiohttp
from rich import print as rprint
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TransferSpeedColumn

from models import DownloadItem
from utils import sanitize

async def download_worker(
    session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, item: DownloadItem, 
    output_dir: str, progress: Progress, task_id: TaskID, logs: list
) -> str:
    async with semaphore:
        final_path = ""
        if item.is_direct:
            final_path = os.path.join(output_dir, item.exact_path)
            if os.path.exists(final_path):
                logs.append(f"[yellow]Saltato (Esistente):[/yellow] {os.path.basename(final_path)}")
                progress.advance(task_id)
                return "skip"
        
        try:
            async with session.get(item.url, allow_redirects=True) as r:
                r.raise_for_status()
                
                if not item.is_direct:
                    # Risolviamo il nome file reale sfruttando la richiesta di download già in corso
                    cd = r.headers.get("Content-Disposition", "")
                    m = re.search(r'filename="?([^"]+)"?', cd)
                    filename = sanitize(m.group(1)) if m else sanitize(str(r.url).split("/")[-1].split("?")[0])
                    if not filename or filename.endswith(".php"):
                        filename = "documento.pdf"
                    
                    indexed_filename = f"{item.file_prefix} - {filename}"
                    final_path = os.path.join(output_dir, item.section_path, indexed_filename)
                    
                    # Controllo duplicati "on-the-fly"
                    if os.path.exists(final_path):
                        logs.append(f"[yellow]Saltato (Esistente):[/yellow] {os.path.basename(final_path)}")
                        progress.advance(task_id)
                        return "skip"
                
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                
                with open(final_path, "wb") as f:
                    async for chunk in r.content.iter_chunked(65536):
                        f.write(chunk)
                        
            logs.append(f"[green]✓ Completato:[/green] {os.path.basename(final_path)}")
            progress.advance(task_id)
            return "ok"
        except Exception as e:
            bname = os.path.basename(final_path) if final_path else "File"
            logs.append(f"[red]✗ Errore ({bname}):[/red] {str(e)}")
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
    
    def generate_layout():
        recent_logs = "\n".join(logs[-8:]) if logs else "In attesa..."
        return Group(
            Panel(recent_logs, title="Logs Live", height=10, style="dim"),
            Panel(progress, title="Progresso Globale")
        )

    async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:
        with Live(generate_layout(), refresh_per_second=10) as live:
            async def update_ui():
                while not progress.finished:
                    live.update(generate_layout())
                    await asyncio.sleep(0.1)
                live.update(generate_layout())

            ui_task = asyncio.create_task(update_ui())
            dl_tasks = [download_worker(session, semaphore, item, output_dir, progress, task_id, logs) for item in items]
            results = await asyncio.gather(*dl_tasks)
            await ui_task

    rprint("\n[bold green]Sincronizzazione completata![/bold green]")
    print(f"Scaricati: {sum(r == 'ok' for r in results)} | Saltati: {sum(r == 'skip' for r in results)} | Errori: {sum(r == 'err' for r in results)}\n")
