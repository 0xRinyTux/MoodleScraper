import asyncio
import os
import re
from dataclasses import asdict
from typing import List

import aiohttp
from bs4 import BeautifulSoup

from models import DownloadItem, Section
from utils import CACHE_FILE, load_json, sanitize, save_json

async def get_courses(session: aiohttp.ClientSession) -> list:
    async with session.get("https://elearning.informatica.unisa.it/el-platform/") as r:
        r.raise_for_status()
        html = await r.text()
    
    soup = BeautifulSoup(html, "lxml")
    search_form = soup.select_one("div.simplesearchform")
    if search_form:
        boundary = search_form.find_parent("div", class_="box") or search_form
        current = boundary
        while current and current.name != '[document]':
            for sib in current.find_next_siblings():
                sib.decompose()
            current = current.parent
        boundary.decompose()

    courses_dict = {}
    for a in soup.select("a[href*='course/view.php?id=']"):
        url = a["href"]
        m = re.search(r"id=(\d+)", url)
        if not m:
            continue
        course_id = m.group(1)
        if course_id == "1":
            continue

        name = " ".join(a.get_text(" ", strip=True).split())
        if not name:
            continue

        is_coursename_class = "coursename" in a.get("class", [])
        
        if course_id not in courses_dict:
            courses_dict[course_id] = {"id": course_id, "name": name, "url": url, "is_best": is_coursename_class}
        else:
            if is_coursename_class or (not courses_dict[course_id]["is_best"] and len(name) > len(courses_dict[course_id]["name"])):
                courses_dict[course_id] = {"id": course_id, "name": name, "url": url, "is_best": is_coursename_class}
    return list(courses_dict.values())

async def resolve_folder(session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, url: str, section_path: str, folder_prefix: str, folder_name: str) -> List[DownloadItem]:
    async with semaphore:
        try:
            async with session.get(url) as r:
                html = await r.text()
            soup = BeautifulSoup(html, "lxml")
            fm = soup.select_one("div.filemanager")
            if not fm:
                return []
            items = []
            indexed_folder_name = f"{folder_prefix} - {folder_name}"
            for file_idx, a in enumerate(fm.select("a[href*='pluginfile.php']"), 1):
                filename = sanitize(a.get_text(" ", strip=True))
                full_path = os.path.join(section_path, indexed_folder_name, f"{file_idx:02d} - {filename}")
                items.append(DownloadItem(
                    url=a["href"],
                    section_path=section_path,
                    file_prefix=f"{file_idx:02d}",
                    is_direct=True,
                    exact_path=full_path
                ))
            return items
        except Exception:
            return []

async def discover_course(session: aiohttp.ClientSession, course_url: str, semaphore: asyncio.Semaphore, use_cache: bool) -> List[Section]:
    cache_data = {}
    if use_cache:
        cache_data = load_json(CACHE_FILE) or {}
        if course_url in cache_data:
            return [Section(name=s["name"], downloads=[DownloadItem(**d) for d in s["downloads"]]) for s in cache_data[course_url]]

    async with session.get(course_url) as r:
        r.raise_for_status()
        html = await r.text()
        
    soup = BeautifulSoup(html, "lxml")
    sections_data = []
    tasks = []
    
    for s_idx, section_div in enumerate(soup.select("div.section-item"), 1):
        title_el = section_div.select_one("h3.sectionname a")
        if not title_el:
            continue
            
        indexed_section_name = f"{s_idx:02d} - {sanitize(title_el.get_text(strip=True))}"
        current_section_idx = len(sections_data)
        sections_data.append(Section(name=indexed_section_name, downloads=[]))
        
        for f_idx, activity in enumerate(section_div.select("li.activity"), 1):
            a = activity.select_one("a[href]")
            if not a:
                continue
            href = a["href"]
            raw_activity_name = sanitize(a.get_text(" ", strip=True).replace(" File", "").replace(" Cartella", ""))
            prefix = f"{f_idx:02d}"
            
            if "/mod/resource/" in href:
                # ZERO RICHIESTE HTTP QUI. Mappatura istantanea basata sull'HTML della home del corso.
                sections_data[current_section_idx].downloads.append(
                    DownloadItem(url=href, section_path=indexed_section_name, file_prefix=prefix, is_direct=False)
                )
            elif "/mod/folder/" in href:
                # Le cartelle richiedono un click di esplorazione interno per elencare i file contenuti.
                tasks.append((current_section_idx, resolve_folder(session, semaphore, href, indexed_section_name, prefix, raw_activity_name)))

    if tasks:
        resolved_results = await asyncio.gather(*(t[1] for t in tasks))
        for (section_idx, _), result in zip(tasks, resolved_results):
            if result:
                sections_data[section_idx].downloads.extend(result)
                    
    if use_cache:
        cache_data[course_url] = [asdict(s) for s in sections_data]
        save_json(CACHE_FILE, cache_data)

    return sections_data
