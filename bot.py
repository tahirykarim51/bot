"""
Bot LinkedIn Alternance Cybersécurité -> Notion
Version stable Railway sans Selenium

Variables d'environnement requises :
- NOTION_TOKEN        (token de l'intégration interne Notion)
- NOTION_DATABASE_ID  (id 32 caractères de la base)
"""

import requests
from bs4 import BeautifulSoup
import time
import os
import re
import random
from datetime import datetime

# ================== CONFIG ==================

CHECK_INTERVAL = 3600          # 1 h entre deux passes
F_TPR = "r7776000"             # 3 mois (90 j * 86400 s)
MAX_PAGES = 20                  # pages parcourues PAR requete (25 offres / page)
SEARCH_LOCATION = "France"

# Plusieurs requetes pour elargir la couverture : LinkedIn limite les resultats
# par requete, donc on multiplie les angles. Les doublons sont geres automatiquement.
SEARCH_QUERIES = [
    "alternance cybersécurité",
    "apprentissage cybersécurité",
    "alternance sécurité informatique",
    "alternance sécurité des systèmes d'information",
    "alternance analyste sécurité",
    "alternance SOC",
    "alternance pentest",
    "alternance RSSI",
    "alternance GRC sécurité",
    "alternance DevSecOps",
    "alternance sécurité réseaux",
    "alternance administrateur cybersécurité",
    "alternance ingénieur cybersécurité",
    "alternance threat intelligence",
    "alternance gouvernance risque conformité",
]

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"
}

# -------- Filtrage par mots-cles (regex avec frontieres de mots) --------
#
# ALTERNANCE : alternance, alternant(e), apprenti(e), apprentissage, apprentice (EN)
ALTERNANCE_REGEX = re.compile(
    r"\b(?:altern\w*|apprenti\w*|apprentissage)\b",
    re.IGNORECASE,
)

# CYBER : on utilise des frontieres de mots (\b) pour eviter les faux positifs
# comme "soc" dans "sociales"/"societe" ou "ids" dans un autre mot.
CYBER_PATTERNS = [
    r"cyber\w*",                 # cyber, cybersecurite, cyberdefense, cybersecurity
    r"s[ée]curi\w*",             # securite, securise, securisation...
    r"security", r"infosec", r"appsec",
    r"information security", r"it security",
    r"r[ée]seau\w*", r"network",
    r"ssi", r"rssi", r"pssi", r"iso\s?27001", r"nist", r"owasp",
    r"soc", r"siem", r"csirt", r"cert", r"noc",
    r"edr", r"xdr", r"dlp", r"waf", r"ids", r"ips",
    r"pentest\w*", r"red team", r"blue team", r"purple team",
    r"grc", r"conformit[ée]", r"risque\w*", r"risk",
    r"rgpd", r"gdpr", r"privacy", r"ebios", r"cnil", r"dora", r"pca", r"pra",
    r"iam", r"pam", r"active directory", r"zero trust",
    r"devsecops", r"forensic\w*", r"incident\w*", r"threat",
    r"vuln[ée]rabilit\w*", r"vulnerability",
    r"audit\w*", r"s[ûu]ret[ée]", r"r[ée]silience",
    r"malware", r"ransomware", r"bastion", r"cryptographie", r"chiffrement",
    r"monitoring", r"d[ée]tection", r"detection", r"endpoint",
    r"protection des donn[ée]es",
    r"protection de l.information",
    r"protection du secret",
]
CYBER_REGEX = re.compile(
    r"\b(?:" + "|".join(CYBER_PATTERNS) + r")\b",
    re.IGNORECASE,
)

# ============================================


class LinkedInNotionBot:
    def __init__(self):
        # .strip() au cas ou un espace / saut de ligne se serait glisse
        self.notion_token = (os.getenv("NOTION_TOKEN") or "").strip()
        self.database_id = (os.getenv("NOTION_DATABASE_ID") or "").strip()

        if not self.notion_token or not self.database_id:
            print("NOTION_TOKEN present       :", bool(self.notion_token))
            print("NOTION_DATABASE_ID present :", bool(self.database_id))
            print(">>> Le bot tourne dans :")
            print("    Projet        :", os.getenv("RAILWAY_PROJECT_NAME"))
            print("    Service       :", os.getenv("RAILWAY_SERVICE_NAME"))
            print("    Environnement :", os.getenv("RAILWAY_ENVIRONMENT_NAME"))
            raise RuntimeError("Variables NOTION manquantes")

        self.notion_headers = {
            "Authorization": "Bearer " + self.notion_token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json"
        }

        # Dedup : on charge les liens deja presents dans Notion
        self.seen_urls = self.load_existing_urls()
        print(str(len(self.seen_urls)) + " offre(s) deja dans Notion")

    # -- Notion : lecture de l'existant (dedup) --

    def _normalize(self, url):
        # repare l'ancien bug de prefixe duplique (liens deja en base)
        if url and url.startswith("https://www.linkedin.comhttps://"):
            url = url[len("https://www.linkedin.com"):]
        return url

    def load_existing_urls(self):
        urls = set()
        payload = {"page_size": 100}
        query_url = NOTION_API + "/databases/" + self.database_id + "/query"

        while True:
            r = requests.post(query_url, headers=self.notion_headers,
                              json=payload, timeout=15)
            if r.status_code != 200:
                print("Notion query error", r.status_code, r.text)
                break

            data = r.json()
            for page in data.get("results", []):
                prop = page.get("properties", {}).get("Lien", {})
                link = self._normalize(prop.get("url"))
                if link:
                    urls.add(link)

            if data.get("has_more"):
                payload["start_cursor"] = data["next_cursor"]
            else:
                break

        return urls

    # -- Notion : creation d'une offre --

    def add_to_notion(self, job):
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Offre": {
                    "title": [{"text": {"content": job["title"][:2000]}}]
                },
                "Entreprise": {
                    "rich_text": [{"text": {"content": job["company"][:2000]}}]
                },
                "Lien": {"url": job["url"]},
                "Lieu": {
                    "rich_text": [{"text": {"content": job["location"][:2000]}}]
                },
                "Statut": {"select": {"name": "À postuler"}},
                "Ajoutée le": {
                    "date": {"start": datetime.now().date().isoformat()}
                }
            }
        }

        r = requests.post(NOTION_API + "/pages",
                          headers=self.notion_headers,
                          json=payload, timeout=15)

        if r.status_code == 200:
            print("Ajoutee :", job["title"], "-", job["company"])
            self.seen_urls.add(job["url"])
        else:
            print("Erreur Notion", r.status_code, r.text)

    # -- Utils --

    def check_keywords(self, text):
        return bool(ALTERNANCE_REGEX.search(text)) and bool(CYBER_REGEX.search(text))

    # -- LinkedIn scraping --

    def scrape_jobs(self):
        print("Scraping LinkedIn guest API")
        base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        new_jobs = []

        for query in SEARCH_QUERIES:
            print("  Requete :", query)
            for page in range(MAX_PAGES):
                params = {
                    "keywords": query,
                    "location": SEARCH_LOCATION,
                    "f_TPR": F_TPR,
                    "start": page * 25
                }

                try:
                    r = requests.get(base_url, headers=HEADERS,
                                    params=params, timeout=15)
                except Exception as e:
                    print("  Requete echouee", e)
                    break

                if r.status_code != 200:
                    print("  HTTP", r.status_code, "page", page)
                    break

                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    break  # plus de resultats pour cette requete

                for card in cards:
                    try:
                        title_el = card.find("h3")
                        company_el = card.find("h4")
                        link_el = card.find("a", href=True)

                        if not title_el or not link_el:
                            continue

                        title = title_el.text.strip()
                        company = company_el.text.strip() if company_el else "N/A"

                        # L'API renvoie tantot une URL absolue, tantot relative
                        href = link_el["href"].split("?")[0]
                        if href.startswith("http"):
                            url = href
                        else:
                            url = "https://www.linkedin.com" + href

                        if url in self.seen_urls:
                            continue

                        text_blob = title + " " + company
                        if not self.check_keywords(text_blob):
                            continue

                        new_jobs.append({
                            "title": title,
                            "company": company,
                            "location": SEARCH_LOCATION,
                            "url": url
                        })
                        self.seen_urls.add(url)

                    except Exception as e:
                        print("  Parse error", e)

                time.sleep(10)  # pause entre chaque page

            time.sleep(60)  # pause entre chaque requete

        return new_jobs

    # -- Boucle principale --

    def run(self):
        print("Bot LinkedIn -> Notion lance")

        while True:
            try:
                jobs = self.scrape_jobs()

                if jobs:
                    print(str(len(jobs)) + " nouvelle(s) offre(s)")
                    for job in jobs:
                        self.add_to_notion(job)
                        time.sleep(0.4)  # limite ~3 req/s de Notion
                else:
                    print("Aucune nouvelle offre")

                delay = CHECK_INTERVAL + random.randint(0, 300)
                time.sleep(delay)

            except Exception as e:
                print("Erreur fatale", e)
                time.sleep(30)


if __name__ == "__main__":
    LinkedInNotionBot().run()
