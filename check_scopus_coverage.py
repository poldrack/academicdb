#!/usr/bin/env python
"""
Script to check Scopus ID coverage in the publication database
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'academicdb_web.settings')
django.setup()

from academic.models import Publication
from django.contrib.auth import get_user_model

User = get_user_model()

def analyze_scopus_coverage(user_id=2):
    """Analyze Scopus ID coverage for a user's publications"""
    
    try:
        user = User.objects.get(id=user_id)
        print(f"Analyzing publications for user: {user.display_name} (ID: {user_id})")
        print(f"User's Scopus ID: {user.scopus_id or 'Not set'}")
        print("="*80)
        
        # Get all publications
        publications = user.publications.all()
        total_pubs = publications.count()
        print(f"Total publications in database: {total_pubs}")
        
        # Analyze Scopus coverage
        pubs_with_scopus = 0
        pubs_without_scopus = 0
        authors_with_scopus = 0
        authors_without_scopus = 0
        
        # Track publications by source
        pubs_by_source = {}
        scopus_coverage_by_source = {}
        
        for pub in publications:
            source = pub.source or 'unknown'
            if source not in pubs_by_source:
                pubs_by_source[source] = 0
                scopus_coverage_by_source[source] = {'with': 0, 'without': 0}
            pubs_by_source[source] += 1
            
            has_scopus = False
            pub_authors_with = 0
            pub_authors_without = 0
            
            if pub.authors:
                for author in pub.authors:
                    if isinstance(author, dict):
                        if author.get('scopus_id'):
                            authors_with_scopus += 1
                            pub_authors_with += 1
                            has_scopus = True
                        else:
                            authors_without_scopus += 1
                            pub_authors_without += 1
            
            if has_scopus:
                pubs_with_scopus += 1
                scopus_coverage_by_source[source]['with'] += 1
            else:
                pubs_without_scopus += 1
                scopus_coverage_by_source[source]['without'] += 1
        
        # Print results
        print("\n" + "="*80)
        print("OVERALL STATISTICS")
        print("="*80)
        print(f"Publications with at least one Scopus ID: {pubs_with_scopus} ({pubs_with_scopus/total_pubs*100:.1f}%)")
        print(f"Publications without any Scopus IDs: {pubs_without_scopus} ({pubs_without_scopus/total_pubs*100:.1f}%)")
        print(f"Total authors with Scopus IDs: {authors_with_scopus}")
        print(f"Total authors without Scopus IDs: {authors_without_scopus}")
        if (authors_with_scopus + authors_without_scopus) > 0:
            print(f"Author Scopus ID coverage: {authors_with_scopus/(authors_with_scopus + authors_without_scopus)*100:.1f}%")
        
        print("\n" + "="*80)
        print("COVERAGE BY SOURCE")
        print("="*80)
        for source in sorted(pubs_by_source.keys()):
            total = pubs_by_source[source]
            with_scopus = scopus_coverage_by_source[source]['with']
            without_scopus = scopus_coverage_by_source[source]['without']
            coverage = with_scopus/total*100 if total > 0 else 0
            print(f"{source:15} - Total: {total:4d}, With Scopus: {with_scopus:4d} ({coverage:5.1f}%), Without: {without_scopus:4d}")
        
        # Check specifically Scopus-sourced publications without Scopus IDs
        print("\n" + "="*80)
        print("SCOPUS-SOURCED PUBLICATIONS WITHOUT SCOPUS IDS")
        print("="*80)
        scopus_pubs_no_ids = publications.filter(source='scopus')
        problem_count = 0
        for pub in scopus_pubs_no_ids[:10]:  # Check first 10
            has_any_scopus = False
            if pub.authors:
                for author in pub.authors:
                    if isinstance(author, dict) and author.get('scopus_id'):
                        has_any_scopus = True
                        break
            
            if not has_any_scopus:
                problem_count += 1
                print(f"- {pub.title[:80]}...")
                print(f"  Year: {pub.year}, DOI: {pub.doi or 'None'}")
                print(f"  Authors: {len(pub.authors) if pub.authors else 0}")
                if pub.authors and len(pub.authors) > 0:
                    print(f"  First author: {pub.authors[0]}")
        
        if problem_count == 0:
            print("All Scopus-sourced publications have at least one Scopus ID!")
        else:
            print(f"\nFound {problem_count} Scopus-sourced publications without any Scopus IDs")
            
    except User.DoesNotExist:
        print(f"User with ID {user_id} not found")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    analyze_scopus_coverage(user_id)