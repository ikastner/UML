#!/usr/bin/env python3
"""
Script pour générer des résumés Lighthouse lisibles
"""

import json
import os
import glob
from pathlib import Path


def generate_lighthouse_summary(json_path: str) -> str:
    """Génère un résumé lisible d'un rapport Lighthouse"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extraire les métriques principales
        categories = data.get('categories', {})
        audits = data.get('audits', {})
        
        # Scores principaux
        performance = categories.get('performance', {}).get('score', 0) * 100 if categories.get('performance', {}).get('score') else 0
        accessibility = categories.get('accessibility', {}).get('score', 0) * 100 if categories.get('accessibility', {}).get('score') else 0
        best_practices = categories.get('best-practices', {}).get('score', 0) * 100 if categories.get('best-practices', {}).get('score') else 0
        seo = categories.get('seo', {}).get('score', 0) * 100 if categories.get('seo', {}).get('score') else 0
        pwa = categories.get('pwa', {}).get('score', 0) * 100 if categories.get('pwa', {}).get('score') else 0
        
        # Métriques de performance détaillées
        metrics = {}
        metric_keys = [
            'first-contentful-paint',
            'largest-contentful-paint', 
            'first-meaningful-paint',
            'speed-index',
            'interactive',
            'total-blocking-time',
            'cumulative-layout-shift'
        ]
        
        for key in metric_keys:
            if key in audits:
                audit = audits[key]
                metrics[key] = {
                    'value': audit.get('displayValue', ''),
                    'score': audit.get('score', 0) * 100 if audit.get('score') else 0,
                    'numeric': audit.get('numericValue', 0)
                }
        
        # URL testée
        url = data.get('finalUrl', data.get('requestedUrl', ''))
        
        # Générer le résumé
        summary = f"""# Lighthouse Audit Summary - {url}

## Scores globaux
- **Performance**: {performance:.0f}/100
- **Accessibility**: {accessibility:.0f}/100  
- **Best Practices**: {best_practices:.0f}/100
- **SEO**: {seo:.0f}/100
- **PWA**: {pwa:.0f}/100

## Métriques de performance
"""
        
        # Ajouter les métriques détaillées
        metric_names = {
            'first-contentful-paint': 'First Contentful Paint',
            'largest-contentful-paint': 'Largest Contentful Paint',
            'first-meaningful-paint': 'First Meaningful Paint', 
            'speed-index': 'Speed Index',
            'interactive': 'Time to Interactive',
            'total-blocking-time': 'Total Blocking Time',
            'cumulative-layout-shift': 'Cumulative Layout Shift'
        }
        
        for key, metric in metrics.items():
            name = metric_names.get(key, key)
            value = metric['value']
            score = metric['score']
            summary += f"- **{name}**: {value} (score: {score:.0f}/100)\\n"
        
        # Recommandations principales
        summary += "\\n## Recommandations principales\\n"
        
        if performance < 90:
            summary += "- ⚠️ **Performance**: Optimiser les images, minifier CSS/JS, utiliser un CDN\\n"
        if accessibility < 90:
            summary += "- ⚠️ **Accessibilité**: Ajouter des attributs alt, améliorer les contrastes\\n"
        if best_practices < 90:
            summary += "- ⚠️ **Bonnes pratiques**: Utiliser HTTPS, corriger les erreurs console\\n"
        if seo < 90:
            summary += "- ⚠️ **SEO**: Ajouter meta descriptions, optimiser les titres\\n"
        
        if all(score >= 90 for score in [performance, accessibility, best_practices, seo]):
            summary += "- ✅ Excellent travail ! Toutes les catégories sont optimisées.\\n"
        
        return summary
        
    except Exception as e:
        return f"# Erreur lors de la génération du résumé\\n\\nErreur: {e}\\n"


def process_all_lighthouse_reports():
    """Traite tous les rapports Lighthouse et génère les résumés"""
    lighthouse_dir = Path('crawl-results/lighthouse')
    
    if not lighthouse_dir.exists():
        print("Dossier lighthouse/ non trouvé")
        return
    
    json_files = list(lighthouse_dir.glob('*-lighthouse.json'))
    
    if not json_files:
        print("Aucun rapport Lighthouse trouvé")
        return
    
    print(f"Traitement de {len(json_files)} rapports Lighthouse...")
    
    for json_file in json_files:
        summary = generate_lighthouse_summary(str(json_file))
        
        # Nom du fichier de résumé
        summary_file = json_file.with_name(json_file.stem + '-summary.md')
        
        # Sauvegarder le résumé
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"Résumé généré: {summary_file.name}")


if __name__ == "__main__":
    process_all_lighthouse_reports()