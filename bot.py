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
import time
import os
from datetime import datetime, timedelta

class LinkedInCyberJobBot:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')

        # ✅ Stockage en mémoire (Railway n'a pas de disque persistant sur le free plan)
        # Les offres sont gardées pour la durée de vie du process (redémarre proprement)
        self.seen_jobs = {}

        # Mots-clés
        self.keywords_alternance = ['alternance', 'apprenti', 'apprentissage', 'alternant']
        self.keywords_cyber = [
            'cyber', 'cybersécurité', 'cybersecurity', 'soc', 'pentest',
            'red team', 'blue team', 'sécurité informatique', 'security',
            'siem', 'grc', 'analyste sécurité', 'devsecops', 'forensic',
            'threat', 'vulnerability', 'incident response'
        ]

        self.driver = None

    # ── Selenium ──────────────────────────────────────────────────────────────

    def setup_driver(self):
        """
        Configure Chrome pour Railway (Linux, sans interface graphique).
        Railway installe Chromium via le buildpack heroku-buildpack-google-chrome.
        """
        options = Options()
        options.add_argument('--headless')
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

        # Sur Railway le binaire Chrome est mis dans le PATH par le buildpack
        chrome_bin = os.getenv('GOOGLE_CHROME_BIN', '/usr/bin/google-chrome')
        chromedriver_path = os.getenv('CHROMEDRIVER_PATH', '/usr/bin/chromedriver')

        options.binary_location = chrome_bin
        service = Service(executable_path=chromedriver_path)

        self.driver = webdriver.Chrome(service=service, options=options)
        # Masquer la propriété navigator.webdriver
        self.driver.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'}
        )
        print("✅ Chrome headless démarré")

    # ── Scraping ──────────────────────────────────────────────────────────────

    def build_search_url(self):
        keywords = "alternance cybersécurité OR alternance SOC OR apprenti cyber OR alternance pentest"
        params = {
            'keywords': keywords.replace(' ', '%20').replace('OR', 'OR'),
            'location': 'France',
            'f_TPR': 'r86400',   # dernières 24 h
            'position': '1',
            'pageNum': '0'
        }
        return "https://www.linkedin.com/jobs/search/?" + '&'.join(f"{k}={v}" for k, v in params.items())

    def check_keywords(self, text: str) -> bool:
        t = text.lower()
        return (
            any(k in t for k in self.keywords_alternance) and
            any(k in t for k in self.keywords_cyber)
        )

    def scrape_jobs(self):
        try:
            url = self.build_search_url()
            print(f"🔍 Scraping : {url}")
            self.driver.get(url)
            time.sleep(5)

            # Scroll pour déclencher le lazy-loading
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            job_cards = soup.find_all('div', class_='base-card')
            print(f"   {len(job_cards)} carte(s) trouvée(s)")

            new_jobs = []
            for card in job_cards:
                try:
                    title_elem   = card.find('h3', class_='base-search-card__title')
                    company_elem = card.find('h4', class_='base-search-card__subtitle')
                    location_elem = card.find('span', class_='job-search-card__location')
                    link_elem    = card.find('a', class_='base-card__full-link')

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
                        'id': job_id, 'title': title,
                        'company': company, 'location': location,
                        'url': job_url,
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
        """Purge les offres vieilles de plus de X jours pour éviter une fuite mémoire."""
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
