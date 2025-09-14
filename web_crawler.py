#!/usr/bin/env python3
"""
Crawler web professionnel pour audit SEO/technique/artistique
Conforme aux spécifications pour christophevandon.com
"""

import os
import sys
import time
import json
import csv
import re
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Set, Optional, Tuple
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
import subprocess


@dataclass
class PageData:
    """Structure pour stocker les données d'une page"""
    url: str
    canonical: str = ""
    status: int = 0
    redirect_chain: List[str] = None
    content_type: str = ""
    size_bytes: int = 0
    load_ms: int = 0
    title: str = ""
    meta_description: str = ""
    meta_robots: str = ""
    og: Dict = None
    twitter: Dict = None
    jsonld: Dict = None
    h1: str = ""
    h2: List[str] = None
    first_paragraph: str = ""
    excerpt_500: str = ""
    images: List[Dict] = None
    internal_links: List[Dict] = None
    external_links: List[str] = None
    in_sitemap: bool = False
    has_viewport: bool = False
    seo_score: int = 0
    lighthouse_path: str = ""
    priority_score: float = 0.0
    depth: int = 0
    internal_link_count: int = 0
    
    def __post_init__(self):
        if self.redirect_chain is None:
            self.redirect_chain = []
        if self.og is None:
            self.og = {}
        if self.twitter is None:
            self.twitter = {}
        if self.jsonld is None:
            self.jsonld = {}
        if self.h2 is None:
            self.h2 = []
        if self.images is None:
            self.images = []
        if self.internal_links is None:
            self.internal_links = []
        if self.external_links is None:
            self.external_links = []


class WebCrawler:
    """Crawler web professionnel avec respect des robots.txt et limitations"""
    
    def __init__(self, base_url: str, max_pages: int = 1000, max_lighthouse: int = 200):
        self.base_url = base_url.rstrip('/')
        self.domain = urlparse(base_url).netloc
        self.max_pages = max_pages
        self.max_lighthouse = max_lighthouse
        
        # Configuration des limites
        self.request_delay = 1.0  # 1 seconde entre requêtes
        self.max_connections = 2
        self.timeout = 30
        self.max_redirects = 5
        
        # User-Agent professionnel
        self.user_agent = "Mozilla/5.0 (compatible; AuditBot/1.0; +https://yourdomain.example/bot)"
        
        # Structures de données
        self.pages_data: Dict[str, PageData] = {}
        self.discovered_urls: Set[str] = set()
        self.crawled_urls: Set[str] = set()
        self.sitemap_urls: Set[str] = set()
        self.robots_parser: Optional[RobotFileParser] = None
        
        # Configuration logging
        self.setup_logging()
        
        # Configuration session requests
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})
        
        # Configuration Selenium
        self.setup_selenium()
    
    def setup_logging(self):
        """Configure le logging détaillé"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('crawl-results/crawl.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_selenium(self):
        """Configure Selenium pour les captures d'écran"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1366,768')
        chrome_options.add_argument(f'--user-agent={self.user_agent}')
        
        # Tentative d'utilisation de chromium-browser
        try:
            # Essayer d'abord chromium
            if os.path.exists('/usr/bin/chromium-browser'):
                chrome_options.binary_location = '/usr/bin/chromium-browser'
            elif os.path.exists('/usr/bin/chromium'):
                chrome_options.binary_location = '/usr/bin/chromium'
            
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            self.logger.warning(f"Impossible d'initialiser Selenium: {e}")
            self.driver = None
    
    def load_robots_txt(self) -> bool:
        """Charge et parse robots.txt"""
        robots_url = urljoin(self.base_url, '/robots.txt')
        try:
            response = self.session.get(robots_url, timeout=self.timeout)
            if response.status_code == 200:
                # Sauvegarder robots.txt
                with open('crawl-results/robots.txt', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                
                # Parser robots.txt
                self.robots_parser = RobotFileParser()
                self.robots_parser.set_url(robots_url)
                self.robots_parser.read()
                
                self.logger.info(f"robots.txt chargé depuis {robots_url}")
                return True
        except Exception as e:
            self.logger.warning(f"Impossible de charger robots.txt: {e}")
        return False
    
    def can_fetch(self, url: str) -> bool:
        """Vérifie si l'URL peut être crawlée selon robots.txt"""
        if self.robots_parser:
            return self.robots_parser.can_fetch(self.user_agent, url)
        return True
    
    def load_sitemap(self) -> Set[str]:
        """Charge et parse sitemap.xml (gère les sitemap index)"""
        sitemap_urls = set()
        
        # Essayer d'abord le sitemap principal
        sitemap_candidates = [
            '/sitemap.xml',
            '/wp-sitemap.xml',
            '/sitemap_index.xml'
        ]
        
        for sitemap_path in sitemap_candidates:
            sitemap_url = urljoin(self.base_url, sitemap_path)
            
            try:
                response = self.session.get(sitemap_url, timeout=self.timeout)
                if response.status_code == 200:
                    # Sauvegarder sitemap.xml
                    with open('crawl-results/sitemap.xml', 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    
                    # Parser sitemap.xml
                    root = ET.fromstring(response.content)
                    
                    # Gérer les namespaces
                    namespaces = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                    
                    # Vérifier si c'est un sitemap index
                    if root.tag.endswith('sitemapindex'):
                        self.logger.info("Sitemap index détecté, chargement des sous-sitemaps...")
                        
                        # Extraire les URLs des sous-sitemaps
                        for sitemap_elem in root.findall('.//sitemap:sitemap', namespaces):
                            loc_elem = sitemap_elem.find('sitemap:loc', namespaces)
                            if loc_elem is not None:
                                sub_sitemap_url = loc_elem.text.strip()
                                sub_urls = self.load_sub_sitemap(sub_sitemap_url)
                                sitemap_urls.update(sub_urls)
                    else:
                        # Sitemap normal - extraire les URLs
                        for url_elem in root.findall('.//sitemap:url', namespaces):
                            loc_elem = url_elem.find('sitemap:loc', namespaces)
                            if loc_elem is not None:
                                url = loc_elem.text.strip()
                                if self.is_internal_url(url):
                                    sitemap_urls.add(url)
                    
                    break  # Sitemap trouvé, sortir de la boucle
                    
            except Exception as e:
                self.logger.warning(f"Impossible de charger {sitemap_url}: {e}")
                continue
        
        self.logger.info(f"Sitemap chargé: {len(sitemap_urls)} URLs trouvées")
        self.sitemap_urls = sitemap_urls
        return sitemap_urls
    
    def load_sub_sitemap(self, sitemap_url: str) -> Set[str]:
        """Charge un sous-sitemap"""
        urls = set()
        
        try:
            response = self.session.get(sitemap_url, timeout=self.timeout)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespaces = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                for url_elem in root.findall('.//sitemap:url', namespaces):
                    loc_elem = url_elem.find('sitemap:loc', namespaces)
                    if loc_elem is not None:
                        url = loc_elem.text.strip()
                        if self.is_internal_url(url):
                            urls.add(url)
                
                self.logger.info(f"Sous-sitemap {sitemap_url}: {len(urls)} URLs")
                
        except Exception as e:
            self.logger.warning(f"Erreur chargement sous-sitemap {sitemap_url}: {e}")
        
        return urls
    
    def is_internal_url(self, url: str) -> bool:
        """Vérifie si l'URL est interne au domaine"""
        parsed = urlparse(url)
        return parsed.netloc == self.domain or parsed.netloc == ''
    
    def normalize_url(self, url: str) -> str:
        """Normalise une URL"""
        parsed = urlparse(url)
        # Supprimer le fragment
        normalized = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, parsed.query, ''
        ))
        return normalized.rstrip('/')
    
    def extract_links(self, soup: BeautifulSoup, base_url: str) -> Tuple[List[str], List[str]]:
        """Extrait les liens internes et externes d'une page"""
        internal_links = []
        external_links = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            if not href or href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                continue
            
            absolute_url = urljoin(base_url, href)
            normalized_url = self.normalize_url(absolute_url)
            
            if self.is_internal_url(normalized_url):
                internal_links.append(normalized_url)
            else:
                external_links.append(normalized_url)
        
        return internal_links, external_links
    
    def extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extrait les informations des images"""
        images = []
        for img in soup.find_all('img'):
            src = img.get('src', '').strip()
            if not src:
                continue
            
            absolute_src = urljoin(base_url, src)
            alt = img.get('alt', '').strip()
            
            image_info = {
                'url': absolute_src,
                'alt': alt,
                'width': img.get('width'),
                'height': img.get('height')
            }
            
            # Convertir width/height en int si possible
            for dim in ['width', 'height']:
                if image_info[dim]:
                    try:
                        image_info[dim] = int(image_info[dim])
                    except (ValueError, TypeError):
                        image_info[dim] = None
            
            images.append(image_info)
        
        return images
    
    def extract_structured_data(self, soup: BeautifulSoup) -> Dict:
        """Extrait les données structurées JSON-LD"""
        structured_data = {}
        
        # JSON-LD
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                structured_data.update(data)
            except (json.JSONDecodeError, TypeError):
                continue
        
        return structured_data
    
    def extract_meta_tags(self, soup: BeautifulSoup) -> Tuple[Dict, Dict]:
        """Extrait les meta tags Open Graph et Twitter Card"""
        og_data = {}
        twitter_data = {}
        
        for meta in soup.find_all('meta'):
            property_attr = meta.get('property', '').lower()
            name_attr = meta.get('name', '').lower()
            content = meta.get('content', '').strip()
            
            if property_attr.startswith('og:'):
                key = property_attr.replace('og:', '')
                og_data[key] = content
            elif name_attr.startswith('twitter:'):
                key = name_attr.replace('twitter:', '')
                twitter_data[key] = content
        
        return og_data, twitter_data
    
    def calculate_seo_score(self, page_data: PageData) -> int:
        """Calcule un score SEO simple (0-100)"""
        score = 0
        
        # Title présent et non vide (20 points)
        if page_data.title.strip():
            score += 20
        
        # Meta description présente (15 points)
        if page_data.meta_description.strip():
            score += 15
        
        # H1 présent (15 points)
        if page_data.h1.strip():
            score += 15
        
        # Status 200 (10 points)
        if page_data.status == 200:
            score += 10
        
        # Viewport présent (10 points)
        if page_data.has_viewport:
            score += 10
        
        # Canonical présent (10 points)
        if page_data.canonical.strip():
            score += 10
        
        # Images avec alt (10 points max)
        if page_data.images:
            images_with_alt = sum(1 for img in page_data.images if img.get('alt'))
            alt_ratio = images_with_alt / len(page_data.images)
            score += int(10 * alt_ratio)
        else:
            score += 10  # Pas d'images = pas de problème
        
        # Pas de robots noindex (10 points)
        if 'noindex' not in page_data.meta_robots.lower():
            score += 10
        
        return min(score, 100)
    
    def analyze_page(self, url: str, response: requests.Response) -> PageData:
        """Analyse complète d'une page"""
        start_time = time.time()
        
        page_data = PageData(url=url)
        page_data.status = response.status_code
        page_data.content_type = response.headers.get('content-type', '')
        page_data.size_bytes = len(response.content)
        
        if response.status_code != 200:
            return page_data
        
        try:
            soup = BeautifulSoup(response.content, 'lxml')
        except Exception:
            soup = BeautifulSoup(response.content, 'html.parser')
        
        # Title
        title_tag = soup.find('title')
        page_data.title = title_tag.get_text().strip() if title_tag else ""
        
        # Meta tags
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        page_data.meta_description = meta_desc.get('content', '').strip() if meta_desc else ""
        
        meta_robots = soup.find('meta', attrs={'name': 'robots'})
        page_data.meta_robots = meta_robots.get('content', '').strip() if meta_robots else ""
        
        # Viewport
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        page_data.has_viewport = viewport is not None
        
        # Canonical
        canonical = soup.find('link', rel='canonical')
        page_data.canonical = canonical.get('href', '').strip() if canonical else ""
        
        # H1 et H2
        h1_tag = soup.find('h1')
        page_data.h1 = h1_tag.get_text().strip() if h1_tag else ""
        
        h2_tags = soup.find_all('h2')
        page_data.h2 = [h2.get_text().strip() for h2 in h2_tags]
        
        # Premier paragraphe
        first_p = soup.find('p')
        if first_p:
            text = first_p.get_text().strip()
            page_data.first_paragraph = text[:300] if len(text) > 300 else text
        
        # Extrait de 500 caractères
        body_text = soup.get_text()
        clean_text = ' '.join(body_text.split())
        page_data.excerpt_500 = clean_text[:500] if len(clean_text) > 500 else clean_text
        
        # Open Graph et Twitter
        page_data.og, page_data.twitter = self.extract_meta_tags(soup)
        
        # Données structurées
        page_data.jsonld = self.extract_structured_data(soup)
        
        # Images
        page_data.images = self.extract_images(soup, url)
        
        # Liens
        internal_links, external_links = self.extract_links(soup, url)
        page_data.external_links = list(set(external_links))
        
        # Traiter les liens internes
        page_data.internal_links = []
        for link in set(internal_links):
            link_status = self.pages_data[link].status if link in self.pages_data else 0
            page_data.internal_links.append({
                'url': link,
                'status': link_status
            })
        
        # Vérifier présence dans sitemap
        page_data.in_sitemap = url in self.sitemap_urls
        
        # Calculer le score SEO
        page_data.seo_score = self.calculate_seo_score(page_data)
        
        # Temps de chargement
        page_data.load_ms = int((time.time() - start_time) * 1000)
        
        return page_data
    
    def fetch_page(self, url: str, retry_count: int = 0) -> Optional[requests.Response]:
        """Récupère une page avec gestion des erreurs et retry"""
        if not self.can_fetch(url):
            self.logger.warning(f"URL interdite par robots.txt: {url}")
            return None
        
        try:
            time.sleep(self.request_delay)  # Respect du délai
            response = self.session.get(
                url, 
                timeout=self.timeout, 
                allow_redirects=True,
                stream=False
            )
            return response
            
        except requests.exceptions.RequestException as e:
            if retry_count < 1 and ('429' in str(e) or '5' in str(e)[:3]):
                # Retry avec backoff exponentiel
                wait_time = 2 ** retry_count
                self.logger.warning(f"Retry {retry_count + 1} pour {url} dans {wait_time}s")
                time.sleep(wait_time)
                return self.fetch_page(url, retry_count + 1)
            else:
                self.logger.error(f"Erreur lors de la récupération de {url}: {e}")
                return None
    
    def take_screenshot(self, url: str, filename: str) -> bool:
        """Prend une capture d'écran de la page"""
        if not self.driver:
            return False
        
        try:
            self.driver.get(url)
            # Attendre que la page soit chargée
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)  # Attendre le rendu complet
            
            screenshot_path = f"crawl-results/screenshots/{filename}.png"
            self.driver.save_screenshot(screenshot_path)
            self.logger.info(f"Screenshot sauvé: {screenshot_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur screenshot pour {url}: {e}")
            return False
    
    def run_lighthouse(self, url: str, filename: str) -> bool:
        """Lance un audit Lighthouse mobile"""
        try:
            output_path = f"crawl-results/lighthouse/{filename}-lighthouse.json"
            
            # Commande Lighthouse
            cmd = [
                'lighthouse', url,
                '--output=json',
                f'--output-path={output_path}',
                '--chrome-flags="--headless --no-sandbox --disable-dev-shm-usage"',
                '--emulated-form-factor=mobile',
                '--throttling-method=simulate',
                '--quiet'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                self.logger.info(f"Lighthouse audit terminé: {output_path}")
                return True
            else:
                self.logger.error(f"Erreur Lighthouse pour {url}: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution Lighthouse pour {url}: {e}")
            return False
    
    def calculate_priority_score(self, url: str, depth: int, internal_link_count: int, in_sitemap: bool) -> float:
        """Calcule un score de priorité pour une URL"""
        score = 0.0
        
        # Profondeur (plus proche de la racine = plus prioritaire)
        score += (10 - min(depth, 9)) * 10  # 10-100 points
        
        # Nombre de liens internes pointant vers cette page
        score += min(internal_link_count, 20) * 2  # 0-40 points
        
        # Présence dans sitemap
        if in_sitemap:
            score += 20
        
        # Page d'accueil
        if url.rstrip('/') == self.base_url:
            score += 50
        
        return score
    
    def discover_urls(self) -> List[str]:
        """Découvre toutes les URLs du site"""
        self.logger.info("Début de la découverte des URLs...")
        
        # Charger robots.txt et sitemap
        self.load_robots_txt()
        sitemap_urls = self.load_sitemap()
        
        # Initialiser avec l'URL de base et le sitemap
        to_crawl = deque([(self.base_url, 0)])  # (url, depth)
        discovered = {self.base_url}
        
        # Ajouter les URLs du sitemap
        for sitemap_url in sitemap_urls:
            if sitemap_url not in discovered:
                to_crawl.append((sitemap_url, 1))
                discovered.add(sitemap_url)
        
        crawled_count = 0
        internal_link_counts = defaultdict(int)
        
        # Découverte récursive
        with tqdm(desc="Découverte URLs", unit="pages") as pbar:
            while to_crawl and len(discovered) < self.max_pages:
                url, depth = to_crawl.popleft()
                
                if url in self.crawled_urls:
                    continue
                
                self.crawled_urls.add(url)
                crawled_count += 1
                pbar.update(1)
                pbar.set_description(f"Découverte URLs (trouvées: {len(discovered)})")
                
                # Récupérer la page
                response = self.fetch_page(url)
                if not response:
                    continue
                
                # Analyser la page
                page_data = self.analyze_page(url, response)
                page_data.depth = depth
                
                # Compter les liens internes pour cette page
                for link_info in page_data.internal_links:
                    internal_link_counts[link_info['url']] += 1
                
                self.pages_data[url] = page_data
                
                # Découvrir de nouveaux liens internes
                if depth < 5:  # Limiter la profondeur
                    for link_info in page_data.internal_links:
                        link_url = link_info['url']
                        if link_url not in discovered and len(discovered) < self.max_pages:
                            to_crawl.append((link_url, depth + 1))
                            discovered.add(link_url)
        
        # Calculer les scores de priorité
        for url, page_data in self.pages_data.items():
            page_data.internal_link_count = internal_link_counts[url]
            page_data.priority_score = self.calculate_priority_score(
                url, page_data.depth, page_data.internal_link_count, page_data.in_sitemap
            )
        
        # Trier par priorité
        sorted_urls = sorted(
            self.pages_data.keys(),
            key=lambda u: self.pages_data[u].priority_score,
            reverse=True
        )
        
        self.logger.info(f"Découverte terminée: {len(sorted_urls)} URLs trouvées")
        return sorted_urls
    
    def generate_slug(self, url: str) -> str:
        """Génère un slug pour les noms de fichiers"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if not path:
            return 'index'
        
        # Remplacer les caractères non-alphanumériques
        slug = re.sub(r'[^a-zA-Z0-9\-_]', '-', path)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:100] if slug else 'page'
    
    def run_crawl(self):
        """Lance le crawl complet"""
        self.logger.info(f"Début du crawl de {self.base_url}")
        start_time = time.time()
        
        # Découverte des URLs
        sorted_urls = self.discover_urls()
        
        # Prendre des screenshots pour toutes les pages
        self.logger.info("Prise de screenshots...")
        for url in tqdm(sorted_urls, desc="Screenshots"):
            slug = self.generate_slug(url)
            self.take_screenshot(url, slug)
        
        # Audits Lighthouse pour les pages prioritaires
        lighthouse_urls = sorted_urls[:self.max_lighthouse]
        self.logger.info(f"Audits Lighthouse pour {len(lighthouse_urls)} pages...")
        
        for url in tqdm(lighthouse_urls, desc="Lighthouse"):
            slug = self.generate_slug(url)
            if self.run_lighthouse(url, slug):
                self.pages_data[url].lighthouse_path = f"./lighthouse/{slug}-lighthouse.json"
        
        # Générer les rapports
        self.generate_reports()
        
        # Fermer le driver Selenium
        if self.driver:
            self.driver.quit()
        
        total_time = time.time() - start_time
        self.logger.info(f"Crawl terminé en {total_time:.2f} secondes")
        
        return sorted_urls
    
    def generate_reports(self):
        """Génère tous les rapports de sortie"""
        self.logger.info("Génération des rapports...")
        
        # Routes JSON
        routes_data = []
        for url, page_data in self.pages_data.items():
            data_dict = asdict(page_data)
            routes_data.append(data_dict)
        
        with open('crawl-results/routes.json', 'w', encoding='utf-8') as f:
            json.dump(routes_data, f, indent=2, ensure_ascii=False)
        
        # Routes CSV
        with open('crawl-results/routes.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'URL', 'title', 'meta_description', 'h1', 'status', 
                'size_bytes', 'load_ms', 'nb_images', 'nb_internal_links'
            ])
            
            for url, page_data in self.pages_data.items():
                writer.writerow([
                    url, page_data.title, page_data.meta_description,
                    page_data.h1, page_data.status, page_data.size_bytes,
                    page_data.load_ms, len(page_data.images), len(page_data.internal_links)
                ])
        
        # Pages individuelles
        for url, page_data in self.pages_data.items():
            slug = self.generate_slug(url)
            self.generate_page_report(url, page_data, slug)
        
        # Rapport global
        self.generate_global_report()
        
        # README
        self.generate_readme()
        
        # Sitemap découvert
        self.generate_discovered_sitemap()
    
    def generate_page_report(self, url: str, page_data: PageData, slug: str):
        """Génère le rapport individuel d'une page"""
        content = f"""# Analyse de la page: {page_data.title or url}

## Métadonnées
- **URL**: {url}
- **Status**: {page_data.status}
- **Taille**: {page_data.size_bytes} bytes
- **Temps de chargement**: {page_data.load_ms} ms
- **Score SEO**: {page_data.seo_score}/100
- **Dans sitemap**: {'Oui' if page_data.in_sitemap else 'Non'}
- **Profondeur**: {page_data.depth}
- **Liens internes entrants**: {page_data.internal_link_count}

## Structure HTML
- **Title**: {page_data.title}
- **Meta description**: {page_data.meta_description}
- **H1**: {page_data.h1}
- **H2** ({len(page_data.h2)}): {', '.join(page_data.h2[:5])}
- **Viewport**: {'Présent' if page_data.has_viewport else 'Manquant'}
- **Canonical**: {page_data.canonical}

## Contenu
### Premier paragraphe
{page_data.first_paragraph}

### Extrait (500 caractères)
{page_data.excerpt_500}

## Images ({len(page_data.images)})
"""
        
        for i, img in enumerate(page_data.images[:10]):  # Limiter à 10
            alt_status = "✓" if img.get('alt') else "✗"
            content += f"- {alt_status} {img['url']} (alt: '{img.get('alt', '')}')\\n"
        
        if len(page_data.images) > 10:
            content += f"... et {len(page_data.images) - 10} autres images\\n"
        
        content += f"""
## Liens internes ({len(page_data.internal_links)})
"""
        
        for i, link in enumerate(page_data.internal_links[:10]):
            status_icon = "✓" if link.get('status') == 200 else "✗" if link.get('status') else "?"
            content += f"- {status_icon} {link['url']}\\n"
        
        if len(page_data.internal_links) > 10:
            content += f"... et {len(page_data.internal_links) - 10} autres liens\\n"
        
        # Recommandations SEO
        content += "\\n## Recommandations SEO\\n"
        recommendations = []
        
        if not page_data.title:
            recommendations.append("⚠️ Ajouter un titre à la page")
        if not page_data.meta_description:
            recommendations.append("⚠️ Ajouter une meta description")
        if not page_data.h1:
            recommendations.append("⚠️ Ajouter un H1 à la page")
        if not page_data.has_viewport:
            recommendations.append("⚠️ Ajouter une balise viewport pour le mobile")
        if not page_data.canonical:
            recommendations.append("⚠️ Ajouter une URL canonique")
        
        images_without_alt = [img for img in page_data.images if not img.get('alt')]
        if images_without_alt:
            recommendations.append(f"⚠️ Ajouter des attributs alt à {len(images_without_alt)} images")
        
        if page_data.status != 200:
            recommendations.append(f"🚨 Corriger le status HTTP {page_data.status}")
        
        if recommendations:
            for rec in recommendations:
                content += f"- {rec}\\n"
        else:
            content += "✅ Aucune recommandation critique\\n"
        
        # Sauvegarder
        with open(f'crawl-results/pages/{slug}.md', 'w', encoding='utf-8') as f:
            f.write(content)
    
    def generate_global_report(self):
        """Génère le rapport global"""
        total_pages = len(self.pages_data)
        pages_200 = sum(1 for p in self.pages_data.values() if p.status == 200)
        pages_4xx = sum(1 for p in self.pages_data.values() if 400 <= p.status < 500)
        pages_5xx = sum(1 for p in self.pages_data.values() if 500 <= p.status < 600)
        pages_with_lighthouse = sum(1 for p in self.pages_data.values() if p.lighthouse_path)
        
        # Top pages par liens internes
        top_pages = sorted(
            self.pages_data.items(),
            key=lambda x: x[1].internal_link_count,
            reverse=True
        )[:20]
        
        # Issues critiques
        issues = []
        for url, page_data in self.pages_data.items():
            if not page_data.title:
                issues.append(f"Titre manquant: {url}")
            if not page_data.meta_description:
                issues.append(f"Meta description manquante: {url}")
            if page_data.status != 200:
                issues.append(f"Erreur HTTP {page_data.status}: {url}")
            if not page_data.h1:
                issues.append(f"H1 manquant: {url}")
        
        content = f"""# Rapport d'audit web - {self.domain}

## Résumé exécutif
Audit complet du site {self.base_url} réalisé le {datetime.now(timezone.utc).isoformat()}. 
{total_pages} pages analysées avec identification des problèmes SEO et techniques prioritaires.

## Statistiques générales
- **Pages crawlées**: {total_pages}
- **Pages 200 OK**: {pages_200}
- **Pages 4xx**: {pages_4xx} 
- **Pages 5xx**: {pages_5xx}
- **Pages auditées Lighthouse**: {pages_with_lighthouse}
- **Pages dans sitemap**: {sum(1 for p in self.pages_data.values() if p.in_sitemap)}

## Top 20 pages par liens internes
"""
        
        for i, (url, page_data) in enumerate(top_pages, 1):
            content += f"{i}. [{page_data.title or 'Sans titre'}]({url}) - {page_data.internal_link_count} liens\\n"
        
        content += f"""
## Top 10 issues critiques
"""
        
        for i, issue in enumerate(issues[:10], 1):
            content += f"{i}. {issue}\\n"
        
        content += f"""
## Priorités d'action

### A: Critique
- Corriger les erreurs HTTP 4xx/5xx ({pages_4xx + pages_5xx} pages)
- Ajouter les titres manquants
- Corriger les meta descriptions manquantes

### B: Important  
- Optimiser les images sans attribut alt
- Ajouter les balises H1 manquantes
- Implémenter les URLs canoniques

### C: Amélioration
- Optimiser les temps de chargement
- Améliorer les scores Lighthouse
- Structurer les données schema.org

## Recommandations techniques
- Implémenter la mise en cache appropriée
- Optimiser les images (format, taille)
- Minifier CSS/JS
- Utiliser un CDN

## Recommandations SEO
- Standardiser les titres et meta descriptions
- Implémenter les données structurées
- Optimiser la structure des URLs
- Améliorer le maillage interne

## Annexes
- Logs détaillés: crawl.log
- Données complètes: routes.json
- Screenshots: dossier screenshots/
- Audits Lighthouse: dossier lighthouse/
"""
        
        with open('crawl-results/report.md', 'w', encoding='utf-8') as f:
            f.write(content)
    
    def generate_readme(self):
        """Génère le README avec la méthodologie"""
        content = f"""# Audit Web - {self.domain}

## Méthodologie

### Paramètres du crawl
- **Date/heure**: {datetime.now(timezone.utc).isoformat()}
- **Domaine**: {self.base_url}
- **Limite pages**: {self.max_pages}
- **Limite Lighthouse**: {self.max_lighthouse}
- **User-Agent**: {self.user_agent}
- **Délai entre requêtes**: {self.request_delay}s
- **Timeout**: {self.timeout}s

### Formule score SEO (0-100)
- Title présent: 20 points
- Meta description: 15 points  
- H1 présent: 15 points
- Status 200: 10 points
- Viewport: 10 points
- Canonical: 10 points
- Images avec alt: 10 points (prorata)
- Pas de noindex: 10 points

### Calcul priorité pages
- Profondeur (10-100 points): plus proche racine = prioritaire
- Liens internes entrants (0-40 points): max 20 liens comptés
- Présence sitemap: +20 points
- Page d'accueil: +50 points

### Structure des fichiers
```
crawl-results/
├── crawl.log                    # Log détaillé
├── robots.txt                   # Copie robots.txt
├── sitemap.xml                  # Copie sitemap.xml  
├── sitemap_discovered.xml       # Sitemap généré
├── routes.json                  # Données complètes
├── routes.csv                   # Tableau synthétique
├── report.md                    # Rapport global
├── README.md                    # Ce fichier
├── pages/                       # Rapports par page
├── screenshots/                 # Captures 1366x768
└── lighthouse/                  # Audits Lighthouse mobile
```

### Limitations
- Crawl limité à {self.max_pages} pages pour performance
- Lighthouse sur {self.max_lighthouse} pages prioritaires seulement
- Respecte robots.txt et délais (1req/s)
- Screenshots desktop uniquement (1366x768)

### Reproduction
```bash
python3 web_crawler.py {self.base_url}
```

### Technologies utilisées
- Python 3.13+ avec requests, BeautifulSoup4, Selenium
- Lighthouse CLI pour audits performance
- Chromium pour screenshots
"""
        
        with open('crawl-results/README.md', 'w', encoding='utf-8') as f:
            f.write(content)
    
    def generate_discovered_sitemap(self):
        """Génère un sitemap XML des URLs découvertes"""
        root = ET.Element("urlset")
        root.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
        
        for url, page_data in self.pages_data.items():
            if page_data.status == 200:
                url_elem = ET.SubElement(root, "url")
                loc_elem = ET.SubElement(url_elem, "loc")
                loc_elem.text = url
                
                priority_elem = ET.SubElement(url_elem, "priority")
                # Calculer priorité basée sur le score
                priority = min(0.5 + (page_data.priority_score / 1000), 1.0)
                priority_elem.text = f"{priority:.1f}"
        
        tree = ET.ElementTree(root)
        tree.write('crawl-results/sitemap_discovered.xml', encoding='utf-8', xml_declaration=True)


def main():
    """Point d'entrée principal"""
    if len(sys.argv) < 2:
        print("Usage: python web_crawler.py <base_url>")
        sys.exit(1)
    
    base_url = sys.argv[1]
    
    # Paramètres par défaut ou depuis arguments
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    max_lighthouse = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    
    crawler = WebCrawler(base_url, max_pages, max_lighthouse)
    
    try:
        urls = crawler.run_crawl()
        print(f"\\n✅ Crawl terminé avec succès!")
        print(f"📊 {len(urls)} pages analysées")
        print(f"📁 Résultats dans: crawl-results/")
        
    except KeyboardInterrupt:
        print("\\n⏹️ Crawl interrompu par l'utilisateur")
        if crawler.driver:
            crawler.driver.quit()
    except Exception as e:
        print(f"\\n❌ Erreur lors du crawl: {e}")
        if crawler.driver:
            crawler.driver.quit()
        raise


if __name__ == "__main__":
    main()