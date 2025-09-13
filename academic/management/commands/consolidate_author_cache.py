"""
Django management command to consolidate duplicate author cache entries
Merges entries that refer to the same person but have different normalized names
"""
import logging
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction

from academic.models import AuthorCache

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Consolidate duplicate author cache entries that refer to the same person'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be consolidated without making changes'
        )
        parser.add_argument(
            '--min-confidence',
            type=float,
            default=0.7,
            help='Minimum confidence score for merging (default: 0.7)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_confidence = options['min_confidence']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Find duplicates by Scopus ID
        scopus_duplicates = self.find_scopus_duplicates()
        
        # Find duplicates by ORCID ID  
        orcid_duplicates = self.find_orcid_duplicates()
        
        # Find potential name-based duplicates
        name_duplicates = self.find_name_duplicates(min_confidence)

        all_groups = scopus_duplicates + orcid_duplicates + name_duplicates
        
        if not all_groups:
            self.stdout.write("No duplicate entries found to consolidate")
            return

        self.stdout.write(f"Found {len(all_groups)} groups of duplicates to consolidate")
        
        consolidated_count = 0
        entries_merged = 0
        
        for group in all_groups:
            if len(group) < 2:
                continue
                
            result = self.consolidate_group(group, dry_run)
            if result:
                consolidated_count += 1
                entries_merged += len(group) - 1
                
                # Show what was merged
                names = [entry.normalized_name for entry in group]
                scopus_ids = [entry.scopus_id for entry in group if entry.scopus_id]
                primary_name = result.normalized_name
                
                self.stdout.write(f"Consolidated: {names} → '{primary_name}'")
                if scopus_ids:
                    self.stdout.write(f"  Scopus ID: {scopus_ids[0]}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== CONSOLIDATION SUMMARY ===\n"
                f"Groups consolidated: {consolidated_count}\n"
                f"Entries merged: {entries_merged}\n"
                f"Cache entries remaining: {AuthorCache.objects.count()}"
            )
        )

    def find_scopus_duplicates(self):
        """Find entries with the same Scopus ID"""
        groups = defaultdict(list)
        
        entries_with_scopus = AuthorCache.objects.exclude(scopus_id__isnull=True).exclude(scopus_id='')
        
        for entry in entries_with_scopus:
            groups[entry.scopus_id].append(entry)
        
        return [group for group in groups.values() if len(group) > 1]

    def find_orcid_duplicates(self):
        """Find entries with the same ORCID ID"""
        groups = defaultdict(list)
        
        entries_with_orcid = AuthorCache.objects.exclude(orcid_id__isnull=True).exclude(orcid_id='')
        
        for entry in entries_with_orcid:
            groups[entry.orcid_id].append(entry)
        
        return [group for group in groups.values() if len(group) > 1]

    def find_name_duplicates(self, min_confidence):
        """Find entries that likely refer to the same person based on names"""
        groups = []
        processed = set()
        
        # Group by surname for efficiency
        surname_groups = defaultdict(list)
        for entry in AuthorCache.objects.all():
            components = AuthorCache.extract_name_components(entry.normalized_name)
            surname = components.get('surname', '')
            if surname:
                surname_groups[surname].append(entry)
        
        # Within each surname group, find similar names
        for surname, entries in surname_groups.items():
            if len(entries) < 2:
                continue
                
            for i, entry1 in enumerate(entries):
                if entry1.id in processed:
                    continue
                    
                similar_group = [entry1]
                processed.add(entry1.id)
                
                for j, entry2 in enumerate(entries[i+1:], i+1):
                    if entry2.id in processed:
                        continue
                    
                    # Skip if they have different IDs (shouldn't be merged)
                    if (entry1.scopus_id and entry2.scopus_id and 
                        entry1.scopus_id != entry2.scopus_id):
                        continue
                    if (entry1.orcid_id and entry2.orcid_id and 
                        entry1.orcid_id != entry2.orcid_id):
                        continue
                    
                    # Calculate similarity
                    comp1 = AuthorCache.extract_name_components(entry1.normalized_name)
                    comp2 = AuthorCache.extract_name_components(entry2.normalized_name)
                    
                    similarity = AuthorCache._calculate_name_similarity(
                        comp1.get('initials', []), comp1.get('given_names', []),
                        comp2.get('initials', []), comp2.get('given_names', [])
                    )
                    
                    if similarity >= min_confidence:
                        similar_group.append(entry2)
                        processed.add(entry2.id)
                
                if len(similar_group) > 1:
                    groups.append(similar_group)
        
        return groups

    @transaction.atomic
    def consolidate_group(self, group, dry_run):
        """Consolidate a group of duplicate entries into one canonical entry"""
        if len(group) < 2:
            return None
        
        # Choose the best entry as the primary (highest confidence, most complete)
        primary = max(group, key=lambda x: (
            bool(x.scopus_id or x.orcid_id),  # Has an ID
            x.confidence_score,
            x.lookup_count,
            len(x.name_variations),
            len(x.normalized_name)
        ))
        
        if dry_run:
            return primary
        
        # Merge data from other entries into primary
        all_variations = set(primary.name_variations or [])
        all_affiliations = set(primary.affiliations or [])
        total_lookup_count = primary.lookup_count
        
        for entry in group:
            if entry.id == primary.id:
                continue
                
            # Merge name variations
            if entry.name_variations:
                all_variations.update(entry.name_variations)
                
            # Merge affiliations
            if entry.affiliations:
                all_affiliations.update(entry.affiliations)
                
            # Sum lookup counts
            total_lookup_count += entry.lookup_count
            
            # Update IDs if primary is missing them
            if entry.scopus_id and not primary.scopus_id:
                primary.scopus_id = entry.scopus_id
            if entry.orcid_id and not primary.orcid_id:
                primary.orcid_id = entry.orcid_id
                
            # Update names if primary is missing them
            if entry.given_name and not primary.given_name:
                primary.given_name = entry.given_name
            if entry.surname and not primary.surname:
                primary.surname = entry.surname
        
        # Update primary with merged data
        primary.name_variations = list(all_variations)
        primary.affiliations = list(all_affiliations)
        primary.lookup_count = total_lookup_count
        primary.confidence_score = min(1.0, primary.confidence_score + 0.1)  # Boost confidence
        primary.save()
        
        # Delete other entries
        for entry in group:
            if entry.id != primary.id:
                entry.delete()
        
        return primary