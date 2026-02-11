"""
Bot de surveillance des offres d'alternance en cybersécurité sur LinkedIn
Version adaptée pour Railway.app

⚙️ Variables d'environnement à définir sur Railway :
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import requests
import subprocess
import shutil
import time
import os
from datetime import datetime, timedelta


# ── Détection dynamique des binaires Chrome/Chromium ─────────────────────────

def find_binary(*candidates):
    """Retourne le premier binaire trouvé dans la liste, ou None."""
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
        if os.path.isfile(name) and os.access(name, os.X_OK):
            return name
    return None

def detect_chrome():
    """Détecte le binaire Chrome/Chromium disponible sur le système."""
    # 1. Variable d'environnement (priorité maximale)
    env = os.getenv('GOOGLE_CHROME_BIN')
    if env and os.path.isfile(env):
        return env

    # 2. Candidats courants (Railway Nix, Debian/Ubuntu, Alpine)
    candidates = [
        'chromium', 'chromium-browser', 'google-chrome',
        'google-chrome-stable',
        '/nix/var/nix/profiles/default/bin/chromium',
        '/usr/bin/chromium', '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    ]
    found = find_binary(*candidates)
    if found:
        return found

    # 3. Recherche large (lente, dernier recours)
    try:
        result = subprocess.run(
            ['find', '/nix', '/usr', '/opt', '-name', 'chromium*', '-type', 'f'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if os.access(line, os.X_OK):
                return line
    except Exception:
        pass

    return None

def detect_chromedriver():
    """Détecte le binaire ChromeDriver disponible sur le système."""
    env = os.getenv('CHROMEDRIVER_PATH')
    if env and os.path.isfile(env):
        return env

    candidates = [
        'chromedriver',
        '/nix/var/nix/profiles/default/bin/chromedriver',
        '/usr/bin/chromedriver',
        '/usr/local/bin/chromedriver',
    ]
    return find_binary(*candidates)


# ── Bot ───────────────────────────────────────────────────────────────────────

class LinkedInCyberJobBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id   = os.getenv('TELEGRAM_CHAT_ID')
        self.seen_jobs = {}   # stockage en mémoire (pas de disque persistant sur Railway free)

        self.keywords_alternance = ['alternance', 'apprenti', 'apprentissage', 'alternant']
        self.keywords_cyber = [
            'cyber', 'cybersécurité', 'cybersecurity', 'soc', 'pentest',
            'red team', 'blue team', 'sécurité informatique', 'security',
            'siem', 'grc', 'analyste sécurité', 'devsecops', 'forensic',
            'threat', 'vulnerability', 'incident response',
        ]
        self.driver = None

    # ── Selenium ──────────────────────────────────────────────────────────────

    def setup_driver(self):
        chrome_bin    = detect_chrome()
        chromedriver  = detect_chromedriver()

        print(f"🔎 Chrome trouvé      : {chrome_bin}")
        print(f"🔎 ChromeDriver trouvé: {chromedriver}")

        if not chrome_bin:
            raise RuntimeError("❌ Aucun binaire Chrome/Chromium trouvé sur ce système.")
        if not chromedriver:
            raise RuntimeError("❌ Aucun binaire ChromeDriver trouvé sur ce système.")

        options = Options()
        options.binary_location = chrome_bin
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument(
            'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        service = Service(executable_path=chromedriver)
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'}
        )
        print("✅ Chrome headless démarré")

    # ── Scraping ──────────────────────────────────────────────────────────────

    def build_search_url(self):
        keywords = 'alternance+cybersécurité+OR+alternance+SOC+OR+apprenti+cyber+OR+alternance+pentest'
        return (
            f"https://www.linkedin.com/jobs/search/?"
            f"keywords={keywords}&location=France&f_TPR=r86400&position=1&pageNum=0"
        )

    def check_keywords(self, text: str) -> bool:
        t = text.lower()
        return (
            any(k in t for k in self.keywords_alternance) and
            any(k in t for k in self.keywords_cyber)
        )

    def scrape_jobs(self):
        try:
            url = self.build_search_url()
            print(f"🔍 Scraping...")
            self.driver.get(url)
            time.sleep(5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            job_cards = soup.find_all('div', class_='base-card')
            print(f"   {len(job_cards)} carte(s) trouvée(s)")

            new_jobs = []
            for card in job_cards:
                try:
                    title_elem    = card.find('h3', class_='base-search-card__title')
                    company_elem  = card.find('h4', class_='base-search-card__subtitle')
                    location_elem = card.find('span', class_='job-search-card__location')
                    link_elem     = card.find('a', class_='base-card__full-link')

                    if not title_elem or not link_elem:
                        continue

                    title    = title_elem.text.strip()
                    company  = company_elem.text.strip() if company_elem else "N/A"
                    location = location_elem.text.strip() if location_elem else "France"
                    job_url  = link_elem['href'].split('?')[0]
                    job_id   = job_url.split('/')[-1] or str(hash(job_url))

                    if not self.check_keywords(f"{title} {company}"):
                        continue
                    if job_id in self.seen_jobs:
                        continue

                    job = {
                        'id': job_id, 'title': title, 'company': company,
                        'location': location, 'url': job_url,
                        'found_at': datetime.now().isoformat()
                    }
                    self.seen_jobs[job_id] = job
                    new_jobs.append(job)

                except Exception as e:
                    print(f"⚠️ Erreur carte : {e}")

            return new_jobs

        except Exception as e:
            print(f"❌ Erreur scraping : {e}")
            return []

    # ── Telegram ──────────────────────────────────────────────────────────────

    def send_telegram(self, job):
        found_dt = datetime.fromisoformat(job['found_at']).strftime('%d/%m/%Y à %H:%M')
        message = (
            "🚨 *Nouvelle alternance cybersécurité !*\n\n"
            f"📋 *Poste :* {job['title']}\n"
            f"🏢 *Entreprise :* {job['company']}\n"
            f"📍 *Lieu :* {job['location']}\n"
            f"🔗 *Lien :* {job['url']}\n\n"
            f"⏰ Trouvée le {found_dt}"
        )
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data={'chat_id': self.chat_id, 'text': message,
                      'parse_mode': 'Markdown', 'disable_web_page_preview': False},
                timeout=10
            )
            if r.status_code == 200:
                print(f"✅ Notif envoyée : {job['title']}")
            else:
                print(f"❌ Échec notif : {r.text}")
        except Exception as e:
            print(f"❌ Erreur Telegram : {e}")

    # ── Nettoyage mémoire ─────────────────────────────────────────────────────

    def cleanup_old_jobs(self, days=3):
        cutoff = datetime.now() - timedelta(days=days)
        to_del = [jid for jid, j in self.seen_jobs.items()
                  if datetime.fromisoformat(j['found_at']) < cutoff]
        for jid in to_del:
            del self.seen_jobs[jid]
        if to_del:
            print(f"🧹 {len(to_del)} ancienne(s) offre(s) purgée(s)")

    # ── Boucle principale ─────────────────────────────────────────────────────

    def run(self, interval=60):
        print("🚀 Bot démarré sur Railway")
        print(f"⏱️  Intervalle : {interval}s")

        self.setup_driver()
        iteration = 0

        try:
            while True:
                iteration += 1
                print(f"\n{'='*55}")
                print(f"🔄 #{iteration} — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

                new_jobs = self.scrape_jobs()

                if new_jobs:
                    print(f"🎉 {len(new_jobs)} nouvelle(s) offre(s) !")
                    for job in new_jobs:
                        self.send_telegram(job)
                        time.sleep(1)
                else:
                    print("ℹ️  Aucune nouvelle offre")

                if iteration % 50 == 0:
                    self.cleanup_old_jobs()

                print(f"💤 Pause {interval}s...")
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n⛔ Arrêt manuel")
        except Exception as e:
            print(f"💥 Erreur fatale : {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
            print("👋 Chrome fermé")


if __name__ == '__main__':
    missing = [v for v in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID') if not os.getenv(v)]
    if missing:
        print(f"❌ Variable(s) manquante(s) : {', '.join(missing)}")
        exit(1)

    LinkedInCyberJobBot().run(interval=60)
