"""
Bot LinkedIn Alternance Cybersécurité
Version stable Railway sans Selenium

Variables d'environnement requises
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

import requests
from bs4 import BeautifulSoup
import time
import os
import json
import hashlib
import random
from datetime import datetime, timedelta

# ================== CONFIG ==================

CHECK_INTERVAL = 60
MAX_AGE_HOURS = 24
SEEN_FILE = "seen_jobs.json"

KEYWORDS_ALTERNANCE = [
    "alternance", "alternant", "apprenti", "apprenti(e)", "apprentissage"
]

KEYWORDS_CYBER = [
    "cyber", "cybersécurité", "cybersecurity",
    "security", "sécurité", "securite",
    "it security", "information security",
    "aws", "azure", "firewall", "pare-feu", "réseau", "réseaux", "network",
    "ssi", "pssi", "iso 27001",
    "soc", "siem", "csirt", "cert",
    "edr", "xdr", "dlp", "waf", "ids", "ips",
    "pentest", "pentester",
    "red team", "blue team",
    "grc", "gouvernance", "risque", "conformité",
    "rgpd", "gdpr", "ebios", "cnil", "dora", "pca", "pra",
    "iam", "pam", "active directory",
    "infrastructure sécurisée", "sécurisé", "sécurisées",
    "devsecops", "forensic", "incident", "threat", "vulnerability"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"
}

# ============================================


class LinkedInCyberBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not self.bot_token or not self.chat_id:
            raise RuntimeError("Variables TELEGRAM manquantes")

        self.seen_jobs = self.load_seen_jobs()

    # ── Utils ────────────────────────────────

    def load_seen_jobs(self):
        if os.path.exists(SEEN_FILE):
            try:
                with open(SEEN_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_seen_jobs(self):
        with open(SEEN_FILE, "w") as f:
            json.dump(self.seen_jobs, f)

    def check_keywords(self, text):
        t = text.lower()
        return (
            any(k in t for k in KEYWORDS_ALTERNANCE)
            and any(k in t for k in KEYWORDS_CYBER)
        )

    # ── LinkedIn scraping ────────────────────

    def scrape_jobs(self):
        print("🔍 Scraping LinkedIn guest API")

        base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        params = {
            "keywords": "alternance cybersécurité",
            "location": "France",
            "f_TPR": "r86400",
            "start": 0
        }

        r = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            print("❌ HTTP", r.status_code)
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.find_all("li")

        new_jobs = []

        for card in cards:
            try:
                title_el = card.find("h3")
                company_el = card.find("h4")
                link_el = card.find("a", href=True)

                if not title_el or not link_el:
                    continue

                title = title_el.text.strip()
                company = company_el.text.strip() if company_el else "N/A"

                url = "https://www.linkedin.com" + link_el["href"].split("?")[0]

                job_id = hashlib.sha256(url.encode()).hexdigest()

                if job_id in self.seen_jobs:
                    continue

                text_blob = f"{title} {company}"
                if not self.check_keywords(text_blob):
                    continue

                job = {
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "location": "France",
                    "url": url,
                    "found_at": datetime.now().isoformat()
                }

                self.seen_jobs[job_id] = job
                self.save_seen_jobs()
                new_jobs.append(job)

            except Exception as e:
                print("⚠️ Parse error", e)

        return new_jobs

    # ── Telegram ─────────────────────────────

    def send_telegram(self, job):
        dt = datetime.fromisoformat(job["found_at"]).strftime("%d/%m/%Y %H:%M")

        message = (
            "🚨 Nouvelle alternance cybersécurité\n\n"
            f"📋 Poste : {job['title']}\n"
            f"🏢 Entreprise : {job['company']}\n"
            f"📍 Lieu : {job['location']}\n\n"
            f"🔗 {job['url']}\n\n"
            f"⏰ Trouvée le {dt}"
        )

        r = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data={
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=10
        )

        if r.status_code == 200:
            print("✅ Notification envoyée")
        else:
            print("❌ Erreur Telegram", r.text)

    # ── Boucle principale ────────────────────

    def run(self):
        print("🚀 Bot LinkedIn Alternance Cybersécurité lancé")

        while True:
            try:
                jobs = self.scrape_jobs()

                if jobs:
                    print(f"🎉 {len(jobs)} nouvelle(s) offre(s)")
                    for job in jobs:
                        self.send_telegram(job)
                        time.sleep(1)
                else:
                    print("ℹ️ Aucune nouvelle offre")
                delay = CHECK_INTERVAL + random.randint(0, 60)
                time.sleep(delay)

            except Exception as e:
                print("💥 Erreur fatale", e)
                time.sleep(10)


if __name__ == "__main__":
    LinkedInCyberBot().run()
