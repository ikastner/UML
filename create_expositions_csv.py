#!/usr/bin/env python3
"""
Script pour extraire les expositions du site et créer expositions.csv
"""

import json
import csv
import re
from datetime import datetime
from urllib.parse import urlparse


def extract_expositions_from_routes():
    """Extrait les expositions depuis routes.json"""
    try:
        with open('crawl-results/routes.json', 'r', encoding='utf-8') as f:
            routes = json.load(f)
        
        expositions = []
        
        for route in routes:
            url = route.get('url', '')
            title = route.get('title', '')
            h1 = route.get('h1', '')
            excerpt = route.get('first_paragraph', '')
            
            # Détecter les pages d'exposition (basé sur les patterns observés)
            is_exposition = False
            date_found = None
            
            # Patterns pour détecter les expositions (plus larges)
            exposition_keywords = [
                'exposition', 'galerie', 'musée', 'jeu de paume', 'mep', 
                'grand palais', 'centre pompidou', 'palais de tokyo',
                'festival', 'biennale', 'salon', 'penn', 'pataut',
                'rheims', 'orlan', 'circulations', 'centquatre'
            ]
            
            title_lower = title.lower()
            h1_lower = h1.lower()
            url_lower = url.lower()
            
            for keyword in exposition_keywords:
                if keyword in title_lower or keyword in h1_lower or keyword in url_lower:
                    is_exposition = True
                    break
            
            # Détecter aussi les pages qui semblent être des articles d'exposition
            if not is_exposition and ('/' in title or 'grand palais' in title_lower or 'mep' in title_lower):
                is_exposition = True
            
            # Chercher des dates dans le titre ou H1
            date_patterns = [
                r'(\d{4})',  # Année seule
                r'(\w+\s+\d{4})',  # Mois Année
                r'(\d{1,2}/\d{4})',  # MM/YYYY
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, title + ' ' + h1)
                if match:
                    date_found = match.group(1)
                    break
            
            if is_exposition:
                # Nettoyer le titre
                clean_title = re.sub(r'\s*–\s*Christophe Vandon$', '', title)
                clean_title = re.sub(r'\s*/\s*\d+\.?\s*$', '', clean_title)
                
                expositions.append({
                    'titre': clean_title,
                    'date': date_found or 'Non spécifiée',
                    'url': url
                })
        
        return expositions
        
    except Exception as e:
        print(f"Erreur lors de l'extraction: {e}")
        return []


def create_expositions_csv():
    """Crée le fichier expositions.csv"""
    expositions = extract_expositions_from_routes()
    
    if not expositions:
        print("Aucune exposition trouvée")
        return
    
    # Trier par date (les plus récentes en premier)
    expositions.sort(key=lambda x: x['date'], reverse=True)
    
    with open('crawl-results/expositions.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['titre', 'date', 'url'])
        
        for expo in expositions:
            writer.writerow([expo['titre'], expo['date'], expo['url']])
    
    print(f"✅ {len(expositions)} expositions sauvées dans expositions.csv")
    
    # Afficher quelques exemples
    print("\nExemples d'expositions trouvées:")
    for i, expo in enumerate(expositions[:10]):
        print(f"{i+1}. {expo['titre']} ({expo['date']})")


if __name__ == "__main__":
    create_expositions_csv()