import getpass
import os
import re
import aiohttp
from bs4 import BeautifulSoup
from InquirerPy import inquirer
from InquirerPy.validator import NumberValidator
from .utils import SETTINGS_FILE, CREDS_FILE, load_json, save_json

async def handle_mfa(session: aiohttp.ClientSession, html: str) -> bool:
    """Handle MFA/OTP verification flow after login."""
    soup = BeautifulSoup(html, "lxml")
    
    # Check if we're on the MFA page
    if "tool-mfa-verify-container" not in html and "id_verificationcode" not in html:
        return False  # Not an MFA page
    
    print("[*] Rilevata autenticazione a più fattori (MFA). Richiesto codice OTP via email.")
    
    # Extract form data from MFA page
    form = soup.find("form", {"id": re.compile(r"mform1")}) or soup.find("form", {"action": re.compile(r"tool/mfa/auth")})
    if not form:
        print("[X] Errore: impossibile trovare il form MFA.")
        return False
    
    # Extract form fields (including hidden and alphaext types)
    payload = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            payload[name] = value
    
    # Verify required fields
    required_fields = ["factor", "sesskey", "_qf__tool_mfa_local_form_login_form"]
    for field in required_fields:
        if field not in payload:
            print(f"[X] Errore: campo obbligatorio '{field}' mancante nel form MFA.")
            return False
    
    # Prompt user for OTP code with validation (6 digits)
    try:
        otp = await inquirer.text(
            message="Inserisci il codice OTP a 6 cifre ricevuto via email:",
            validate=NumberValidator(message="Inserisci solo numeri"),
            filter=lambda x: x.strip(),
            invalid_message="Il codice deve essere di 6 cifre numeriche",
            multiline=False,
        ).execute_async()
        
        # Validate OTP is exactly 6 digits
        if not re.match(r"^\d{6}$", otp):
            print("[X] Codice OTP non valido: deve essere esattamente 6 cifre numeriche.")
            return False
            
    except KeyboardInterrupt:
        print("\n[X] Annullato dall'utente.")
        return False
    except Exception as e:
        print(f"[X] Errore durante l'inserimento OTP: {e}")
        return False
    
    # Add OTP to payload
    payload["verificationcode"] = otp
    payload["submitbutton"] = "Prosegui"
    
    # Submit MFA form
    mfa_url = "https://elearning.informatica.unisa.it/el-platform/admin/tool/mfa/auth.php"
    print("[*] Invio codice OTP...")
    
    try:
        async with session.post(mfa_url, data=payload, allow_redirects=True) as r:
            final_html = await r.text()
            
        # Check if MFA succeeded (no error messages, redirected away from MFA page)
        if "tool-mfa-verify-container" in final_html or "id_verificationcode" in final_html:
            # Check for error messages
            error_soup = BeautifulSoup(final_html, "lxml")
            error_elem = error_soup.find("div", class_="invalid-feedback") or error_soup.find("div", id="id_error_verificationcode")
            if error_elem and error_elem.get_text(strip=True):
                print(f"[X] OTP non valido: {error_elem.get_text(strip=True)}")
            else:
                print("[X] Codice OTP non valido o scaduto.")
            return False
            
        print("[+] Verifica MFA completata con successo!")
        return True
        
    except Exception as e:
        print(f"[X] Errore durante l'invio del codice OTP: {e}")
        return False


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
        
        # Check if MFA is required after successful credentials
        if "tool-mfa-verify-container" in final_html or "id_verificationcode" in final_html:
            mfa_success = await handle_mfa(session, final_html)
            if not mfa_success:
                print("[X] Verifica MFA fallita.")
                return False
            # After successful MFA, get the final page HTML
            async with session.get("https://elearning.informatica.unisa.it/el-platform/") as r:
                final_html = await r.text()
            
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
