import getpass
import aiohttp
from bs4 import BeautifulSoup
from InquirerPy import inquirer
from utils import SETTINGS_FILE, CREDS_FILE, load_json, save_json

async def check_session_validity(session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get("https://elearning.informatica.unisa.it/el-platform/") as r:
            html = await r.text()
        if "Non sei collegato" not in html and "loginform" not in html:
            return True
    except Exception:
        pass
    return False

async def load_or_perform_login(session: aiohttp.ClientSession) -> bool:
    settings = load_json(SETTINGS_FILE)
    creds = load_json(CREDS_FILE) or {}
    
    cookie = creds.get("cookie")
    username = creds.get("username")
    password = creds.get("password")
    
    if cookie:
        session.cookie_jar.update_cookies({"MoodleSession": cookie})
        if await check_session_validity(session):
            print("[+] Sessione tramite Cookie salvato valida! Accesso eseguito.")
            return True
        else:
            print("[!] Il Cookie salvato è scaduto. Tento un nuovo login...")
            session.cookie_jar.clear()

    is_using_saved_creds = bool(username and password)
    if not is_using_saved_creds:
        print("\n--- Autenticazione Moodle Unisa ---")
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ").strip()

        if settings is None:
            print("\n[CONFIGURAZIONE INIZIALE]")
            save_creds_choice = await inquirer.confirm(message="Salvare le credenziali in locale?", default=True).execute_async()
            save_cookie_choice = await inquirer.confirm(message="Salvare il cookie di sessione per accessi futuri istantanei?", default=True).execute_async()
            save_cache_choice = await inquirer.confirm(message="Attivare la CACHE dei corsi (velocizza i riavvii ma usa spazio disco)?", default=False).execute_async()

            settings = {
                "save_credentials": save_creds_choice,
                "save_cookie": save_cookie_choice,
                "cache_courses": save_cache_choice
            }
            save_json(SETTINGS_FILE, settings)
            print(f"[*] Preferenze salvate in '{SETTINGS_FILE}'.\n")
    else:
        print(f"[*] Utilizzo le credenziali salvate per l'utente: {username}")
        if settings is None:
            settings = {"save_credentials": True, "save_cookie": True, "cache_courses": False}

    login_url = "https://elearning.informatica.unisa.it/el-platform/login/index.php"
    
    try:
        async with session.get(login_url) as r:
            r.raise_for_status()
            html = await r.text()
            
        soup = BeautifulSoup(html, "lxml")
        token_input = soup.find("input", {"name": "logintoken"})
        if not token_input:
            print("[X] Errore critico: impossibile trovare il 'logintoken'.")
            return False
            
        payload = {
            "username": username,
            "password": password,
            "logintoken": token_input.get("value", ""),
            "anchor": ""
        }
        
        async with session.post(login_url, data=payload, allow_redirects=True) as r:
            final_html = await r.text()
            
        if "loginform" in final_html or "login-form" in final_html:
            print("[X] Login fallito: Credenziali errate.")
            if is_using_saved_creds:
                creds.pop("username", None)
                creds.pop("password", None)
                save_json(CREDS_FILE, creds)
            return False
            
        moodle_cookie = ""
        for c in session.cookie_jar:
            if c.key == "MoodleSession":
                moodle_cookie = c.value
                break
                
        if moodle_cookie:
            print("[+] Login effettuato con successo!")
            
            if settings.get("save_credentials"):
                creds["username"] = username
                creds["password"] = password
            else:
                creds.pop("username", None)
                creds.pop("password", None)
                
            if settings.get("save_cookie"):
                creds["cookie"] = moodle_cookie
            else:
                creds.pop("cookie", None)
                
            if settings.get("save_credentials") or settings.get("save_cookie"):
                save_json(CREDS_FILE, creds)
            else:
                if os.path.exists(CREDS_FILE):
                    os.remove(CREDS_FILE)
            return True
        return False
            
    except Exception as e:
        print(f"[X] Errore imprevisto durante il login: {e}")
        return False
