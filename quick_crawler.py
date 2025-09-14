#!/usr/bin/env python3
"""
Version rapide du crawler pour test (limite 20 pages)
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


class QuickCrawler:
    """Version rapide du crawler pour tests"""
    
    def __init__(self, base_url: str, max_pages: int = 20):
        self.base_url = base_url.rstrip('/')
        self.domain = urlparse(base_url).netloc
        self.max_pages = max_pages
        
        # Configuration des limites
        self.request_delay = 0.5  # Plus rapide pour les tests
        self.timeout = 10
        
        # User-Agent professionnel
        self.user_agent = "Mozilla/5.0 (compatible; AuditBot/1.0; +https://yourdomain.example/bot)"
        
        # Structures de données
        self.pages_data: Dict[str, PageData] = {}
        self.sitemap_urls: Set[str] = set()
        
        # Configuration logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Configuration session requests
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})
    
    def load_sitemap(self) -> Set[str]:
        """Charge le sitemap WordPress"""
        sitemap_urls = set()
        sitemap_url = urljoin(self.base_url, '/wp-sitemap.xml')
        
        try:
            response = self.session.get(sitemap_url, timeout=self.timeout)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespaces = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                if root.tag.endswith('sitemapindex'):
                    self.logger.info("Sitemap index détecté")
                    
                    for sitemap_elem in root.findall('.//sitemap:sitemap', namespaces):
                        loc_elem = sitemap_elem.find('sitemap:loc', namespaces)
                        if loc_elem is not None:
                            sub_sitemap_url = loc_elem.text.strip()
                            sub_urls = self.load_sub_sitemap(sub_sitemap_url)
                            sitemap_urls.update(sub_urls)
                
                self.logger.info(f"Sitemap chargé: {len(sitemap_urls)} URLs")
                self.sitemap_urls = sitemap_urls
                
        except Exception as e:
            self.logger.warning(f"Erreur sitemap: {e}")
        
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
                        urls.add(url)
                
        except Exception as e:
            self.logger.warning(f"Erreur sous-sitemap: {e}")
        
        return urls
    
    def analyze_page(self, url: str) -> PageData:
        """Analyse rapide d'une page"""
        start_time = time.time()
        page_data = PageData(url=url)
        
        try:
            time.sleep(self.request_delay)
            response = self.session.get(url, timeout=self.timeout)
            
            page_data.status = response.status_code
            page_data.content_type = response.headers.get('content-type', '')
            page_data.size_bytes = len(response.content)
            page_data.load_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Title
                title_tag = soup.find('title')
                page_data.title = title_tag.get_text().strip() if title_tag else ""
                
                # Meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                page_data.meta_description = meta_desc.get('content', '').strip() if meta_desc else ""
                
                # H1
                h1_tag = soup.find('h1')
                page_data.h1 = h1_tag.get_text().strip() if h1_tag else ""
                
                # H2
                h2_tags = soup.find_all('h2')
                page_data.h2 = [h2.get_text().strip() for h2 in h2_tags]
                
                # Premier paragraphe
                first_p = soup.find('p')
                if first_p:
                    text = first_p.get_text().strip()
                    page_data.first_paragraph = text[:300] if len(text) > 300 else text
                
                # Viewport
                viewport = soup.find('meta', attrs={'name': 'viewport'})
                page_data.has_viewport = viewport is not None
                
                # Images
                images = []
                for img in soup.find_all('img'):
                    src = img.get('src', '').strip()
                    if src:
                        images.append({
                            'url': urljoin(url, src),
                            'alt': img.get('alt', '').strip(),
                            'width': img.get('width'),
                            'height': img.get('height')
                        })
                page_data.images = images
                
                # Vérifier présence dans sitemap
                page_data.in_sitemap = url in self.sitemap_urls
                
                # Score SEO simple
                score = 0
                if page_data.title: score += 25
                if page_data.meta_description: score += 25
                if page_data.h1: score += 25
                if page_data.has_viewport: score += 25
                page_data.seo_score = score
            
        except Exception as e:
            self.logger.error(f"Erreur analyse {url}: {e}")
        
        return page_data
    
    def run_quick_crawl(self):
        """Lance un crawl rapide"""
        self.logger.info(f"Début du crawl rapide de {self.base_url}")
        
        # Charger le sitemap
        sitemap_urls = self.load_sitemap()
        
        # Prendre les premières URLs + page d'accueil
        urls_to_crawl = [self.base_url]
        urls_to_crawl.extend(list(sitemap_urls)[:self.max_pages-1])
        
        # Crawler les pages
        for i, url in enumerate(urls_to_crawl[:self.max_pages], 1):
            self.logger.info(f"Crawl {i}/{min(len(urls_to_crawl), self.max_pages)}: {url}")
            page_data = self.analyze_page(url)
            self.pages_data[url] = page_data
        
        # Générer les rapports
        self.generate_reports()
        
        self.logger.info(f"Crawl rapide terminé: {len(self.pages_data)} pages")
        return list(self.pages_data.keys())
    
    def generate_reports(self):
        """Génère les rapports de base"""
        
        # Routes JSON
        routes_data = []
        for url, page_data in self.pages_data.items():
            data_dict = asdict(page_data)
            routes_data.append(data_dict)
        
        os.makedirs('crawl-results', exist_ok=True)
        with open('crawl-results/routes.json', 'w', encoding='utf-8') as f:
            json.dump(routes_data, f, indent=2, ensure_ascii=False)
        
        # Routes CSV
        with open('crawl-results/routes.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'URL', 'title', 'meta_description', 'h1', 'status', 
                'size_bytes', 'load_ms', 'nb_images', 'seo_score'
            ])
            
            for url, page_data in self.pages_data.items():
                writer.writerow([
                    url, page_data.title, page_data.meta_description,
                    page_data.h1, page_data.status, page_data.size_bytes,
                    page_data.load_ms, len(page_data.images), page_data.seo_score
                ])
        
        # Rapport simple
        total_pages = len(self.pages_data)
        pages_200 = sum(1 for p in self.pages_data.values() if p.status == 200)
        avg_seo = sum(p.seo_score for p in self.pages_data.values()) / total_pages if total_pages > 0 else 0
        
        report = f"""# Rapport de crawl rapide - {self.domain}

## Statistiques
- **Pages crawlées**: {total_pages}
- **Pages 200 OK**: {pages_200}
- **Score SEO moyen**: {avg_seo:.1f}/100
- **URLs dans sitemap**: {len(self.sitemap_urls)}

## Pages analysées
"""
        
        for url, page_data in self.pages_data.items():
            report += f"- [{page_data.title or 'Sans titre'}]({url}) - SEO: {page_data.seo_score}/100\\n"
        
        with open('crawl-results/quick_report.md', 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"✅ Rapports générés dans crawl-results/")
        print(f"📊 {total_pages} pages analysées")
        print(f"📈 Score SEO moyen: {avg_seo:.1f}/100")


def main():
    if len(sys.argv) < 2:
        print("Usage: python quick_crawler.py <base_url> [max_pages]")
        sys.exit(1)
    
    base_url = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    crawler = QuickCrawler(base_url, max_pages)
    crawler.run_quick_crawl()


if __name__ == "__main__":
    main()