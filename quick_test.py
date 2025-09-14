#!/usr/bin/env python3
"""
Test rapide du crawler pour valider le fonctionnement
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import json

def test_site_access():
    """Test d'accès basique au site"""
    url = "http://christophevandon.com"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"✅ Site accessible: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Taille: {len(response.content)} bytes")
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.find('title')
        print(f"Title: {title.get_text().strip() if title else 'N/A'}")
        
        # Compter les liens
        links = soup.find_all('a', href=True)
        internal_links = []
        for link in links:
            href = link.get('href')
            if href and not href.startswith(('http', 'mailto:', 'tel:', '#')):
                full_url = urljoin(url, href)
                if 'christophevandon.com' in full_url:
                    internal_links.append(full_url)
        
        unique_links = list(set(internal_links))
        print(f"Liens internes trouvés: {len(unique_links)}")
        for i, link in enumerate(unique_links[:10]):
            print(f"  {i+1}. {link}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def test_sitemap():
    """Test du chargement du sitemap"""
    base_url = "http://christophevandon.com"
    
    # Test sitemap principal
    sitemap_url = urljoin(base_url, '/wp-sitemap.xml')
    
    try:
        response = requests.get(sitemap_url, timeout=10)
        if response.status_code == 200:
            print(f"✅ Sitemap trouvé: {sitemap_url}")
            
            root = ET.fromstring(response.content)
            print(f"Root tag: {root.tag}")
            
            if root.tag.endswith('sitemapindex'):
                print("📋 Sitemap index détecté")
                
                namespaces = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                sitemaps = root.findall('.//sitemap:sitemap', namespaces)
                print(f"Sous-sitemaps trouvés: {len(sitemaps)}")
                
                all_urls = set()
                for sitemap_elem in sitemaps[:3]:  # Limiter à 3 pour le test
                    loc_elem = sitemap_elem.find('sitemap:loc', namespaces)
                    if loc_elem is not None:
                        sub_url = loc_elem.text.strip()
                        print(f"  Chargement: {sub_url}")
                        
                        sub_response = requests.get(sub_url, timeout=10)
                        if sub_response.status_code == 200:
                            sub_root = ET.fromstring(sub_response.content)
                            urls = sub_root.findall('.//sitemap:url', namespaces)
                            for url_elem in urls:
                                loc = url_elem.find('sitemap:loc', namespaces)
                                if loc is not None:
                                    all_urls.add(loc.text.strip())
                
                print(f"URLs totales trouvées: {len(all_urls)}")
                for i, url in enumerate(list(all_urls)[:10]):
                    print(f"  {i+1}. {url}")
                
                return all_urls
        else:
            print(f"❌ Sitemap non accessible: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Erreur sitemap: {e}")
    
    return set()

def test_robots():
    """Test du robots.txt"""
    robots_url = "http://christophevandon.com/robots.txt"
    
    try:
        response = requests.get(robots_url, timeout=10)
        if response.status_code == 200:
            print(f"✅ robots.txt trouvé")
            print("Contenu:")
            print(response.text)
        else:
            print(f"❌ robots.txt non accessible: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Erreur robots.txt: {e}")

if __name__ == "__main__":
    print("🔍 Test rapide du site christophevandon.com\n")
    
    print("=== Test d'accès ===")
    test_site_access()
    
    print("\n=== Test robots.txt ===")
    test_robots()
    
    print("\n=== Test sitemap ===")
    sitemap_urls = test_sitemap()
    
    print(f"\n✅ Test terminé - {len(sitemap_urls)} URLs dans sitemap")