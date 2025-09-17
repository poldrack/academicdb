from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse, FileResponse
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.management import call_command
from django.utils import timezone
import logging
import threading
import time
import json
import os
from pathlib import Path
from io import StringIO
import sys
from .models import Publication, Funding, Teaching, Talk, Conference, ProfessionalActivity, Link

logger = logging.getLogger(__name__)

# Global progress tracking for sync operations
sync_progress = {}


class HomeView(TemplateView):
    """
    Landing page for the academic database web interface
    """
    template_name = 'academic/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Academic Database'
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard for authenticated users
    """
    template_name = 'academic/dashboard.html'
    login_url = '/accounts/login/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Dashboard'
        context['user'] = self.request.user
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    """
    User profile view and edit
    """
    template_name = 'academic/profile.html'
    login_url = '/accounts/login/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Profile'
        context['user'] = self.request.user
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle profile update form submission"""
        user = request.user

        # Update basic profile fields
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')

        # Handle email change with validation
        new_email = request.POST.get('email', '').strip()
        if new_email and new_email != user.email:
            # Check if email is already in use
            from django.contrib.auth import get_user_model
            User = get_user_model()
            if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                messages.error(request, f'Email address "{new_email}" is already in use by another account.')
                return redirect('academic:profile')
            user.email = new_email

        user.institution = request.POST.get('institution', '')
        user.department = request.POST.get('department', '')
        user.scopus_id = request.POST.get('scopus_id', '')
        user.pubmed_query = request.POST.get('pubmed_query', '')
        user.skip_dois = request.POST.get('skip_dois', '')
        
        # Handle research areas (comma-separated string to list)
        research_areas_str = request.POST.get('research_areas', '')
        if research_areas_str:
            user.research_areas = [area.strip() for area in research_areas_str.split(',') if area.strip()]
        else:
            user.research_areas = []
        
        # Handle personal information
        user.middle_name = request.POST.get('middle_name', '')

        # Handle address fields
        user.address1 = request.POST.get('address1', '')
        user.address2 = request.POST.get('address2', '')
        user.city = request.POST.get('city', '')
        user.state = request.POST.get('state', '')
        user.zip_code = request.POST.get('zip_code', '')
        user.country = request.POST.get('country', '')

        # Handle contact information
        user.phone = request.POST.get('phone', '')

        # Handle websites (JSON field)
        websites_data = []
        # Get all website entries (we'll look for pairs of label_ and url_ fields)
        for key in request.POST:
            if key.startswith('website_label_'):
                index = key.replace('website_label_', '')
                label = request.POST.get(f'website_label_{index}', '').strip()
                url = request.POST.get(f'website_url_{index}', '').strip()
                if label and url:
                    websites_data.append({'label': label, 'url': url})
        user.websites = websites_data

        # Handle settings
        user.preferred_citation_style = request.POST.get('citation_style', 'apa')
        user.email_notifications = 'email_notifications' in request.POST
        
        try:
            user.save()
            messages.success(request, 'Profile updated successfully!')
        except Exception as e:
            messages.error(request, f'Failed to update profile: {str(e)}')
        
        return redirect('academic:profile')


class OrcidConnectedView(LoginRequiredMixin, TemplateView):
    """
    Handle ORCID authentication callback
    """
    template_name = 'academic/orcid_connected.html'
    login_url = '/accounts/login/'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'ORCID Connected'
        context['user'] = self.request.user
        
        # Check if user has ORCID connection
        if self.request.user.is_orcid_connected:
            messages.success(self.request, 'Your ORCID account is successfully connected!')
        else:
            messages.warning(self.request, 'ORCID connection not complete. Please try again.')
            
        return context


class PublicationListView(LoginRequiredMixin, ListView):
    """
    List all publications for the current user
    """
    model = Publication
    template_name = 'academic/publication_list.html'
    context_object_name = 'publications'
    paginate_by = 20
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Filter publications to show only those owned by the current user"""
        queryset = Publication.objects.filter(owner=self.request.user)

        # Handle search functionality
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            # Use the database-agnostic search method from the Publication model
            queryset = Publication.search(search_query, user=self.request.user)

        # Include all publications (both ignored and non-ignored)
        return queryset.order_by('-year', 'title')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'My Publications'
        context['publication_count'] = self.get_queryset().count()
        # Count ignored and non-ignored publications separately
        context['ignored_count'] = self.get_queryset().filter(is_ignored=True).count()
        context['active_count'] = self.get_queryset().filter(is_ignored=False).count()
        # Pass search query to template
        context['search_query'] = self.request.GET.get('search', '').strip()

        # Add link counts for each publication
        for pub in context['publications']:
            link_count = Link.objects.filter(owner=self.request.user, doi=pub.doi).count()
            pub.link_count = link_count

        return context


class PublicationDetailView(LoginRequiredMixin, DetailView):
    """
    Display details of a single publication
    """
    model = Publication
    template_name = 'academic/publication_detail.html'
    context_object_name = 'publication'
    login_url = '/accounts/login/'

    def get_queryset(self):
        """Ensure users can only view their own publications"""
        return Publication.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        """Add links from Link model to context"""
        context = super().get_context_data(**kwargs)

        # Get links associated with this publication
        context['external_links'] = Link.get_links_for_publication(self.object)

        return context


class PublicationCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new publication manually
    """
    model = Publication
    template_name = 'academic/publication_form.html'
    fields = ['title', 'year', 'publication_date', 'publication_name',
              'publication_type', 'doi', 'authors', 'is_ignored', 'ignore_reason']
    success_url = reverse_lazy('academic:publication_list')
    login_url = '/accounts/login/'
    
    def form_valid(self, form):
        """Set the owner to the current user and mark as manual entry"""
        form.instance.owner = self.request.user
        form.instance.source = 'manual'
        
        # Parse authors if provided as string
        if isinstance(form.cleaned_data.get('authors'), str):
            authors_str = form.cleaned_data['authors']
            form.instance.authors = [
                {'name': author.strip()} 
                for author in authors_str.split(',') if author.strip()
            ]
        
        messages.success(self.request, 'Publication added successfully!')
        return super().form_valid(form)


class PublicationUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing publication
    """
    model = Publication
    template_name = 'academic/publication_form.html'
    fields = ['title', 'year', 'publication_date', 'publication_name',
              'publication_type', 'doi', 'is_ignored', 'ignore_reason']
    success_url = reverse_lazy('academic:publication_list')
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only edit their own publications"""
        return Publication.objects.filter(owner=self.request.user)
    
    def form_valid(self, form):
        """Track manual edits"""
        # Get changed fields
        changed_fields = form.changed_data
        
        if changed_fields:
            # Use the save_with_edit_protection method
            obj = form.save(commit=False)
            obj.save_with_edit_protection(
                user_edit=True,
                edited_fields=changed_fields
            )
            messages.success(self.request, 'Publication updated successfully!')
            return redirect(self.success_url)
        
        return super().form_valid(form)


class PublicationDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete a publication with confirmation
    """
    model = Publication
    template_name = 'academic/publication_confirm_delete.html'
    success_url = reverse_lazy('academic:publication_list')
    login_url = '/accounts/login/'

    def get_queryset(self):
        """Ensure users can only delete their own publications"""
        return Publication.objects.filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):
        """Add success message when deleting"""
        obj = self.get_object()
        messages.success(request, f'Publication "{obj.title}" has been deleted successfully.')
        return super().delete(request, *args, **kwargs)


class OrcidSyncView(LoginRequiredMixin, View):
    """
    Handle ORCID synchronization requests
    """
    login_url = '/accounts/login/'
    
    def post(self, request):
        """Handle sync request"""
        user = request.user
        
        # Check if user has ORCID connection
        if not user.is_orcid_connected:
            messages.error(request, 'ORCID account not connected. Please connect your ORCID account first.')
            return redirect('academic:profile')
        
        try:
            # Call the sync management command for this specific user
            messages.info(request, 'Starting ORCID sync...')
            
            # Use call_command to run the sync_orcid management command
            # We'll capture the output and show it to the user
            from io import StringIO
            import sys
            
            # Capture output
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                call_command('sync_orcid', user_id=user.id, verbosity=1)
                output = captured_output.getvalue()
                
                # Check if sync was successful based on output
                synced_publications = 'Synced' in output and 'publications' in output
                synced_funding = 'Synced' in output and 'funding records' in output
                
                if synced_publications or synced_funding:
                    sync_items = []
                    if synced_publications:
                        sync_items.append('publications')
                    if synced_funding:
                        sync_items.append('funding records')
                    items_text = ' and '.join(sync_items)
                    messages.success(request, f'ORCID sync completed successfully! Check your {items_text}.')
                elif 'No publications' in output or 'Found 0 publications' in output:
                    if synced_funding:
                        messages.success(request, 'ORCID sync completed successfully! Check your funding records.')
                    else:
                        messages.warning(request, 'ORCID sync completed, but no new publications were found.')
                else:
                    messages.info(request, 'ORCID sync completed.')
                
                logger.info(f"ORCID sync for user {user.id}: {output}")
                
            except Exception as e:
                messages.error(request, f'ORCID sync failed: {str(e)}')
                logger.error(f"ORCID sync error for user {user.id}: {str(e)}")
            finally:
                sys.stdout = old_stdout
        
        except Exception as e:
            messages.error(request, f'Failed to start ORCID sync: {str(e)}')
            logger.error(f"Failed to start ORCID sync for user {user.id}: {str(e)}")
        
        # Redirect back to the appropriate page
        next_page = request.POST.get('next', 'academic:profile')
        if 'publication' in next_page:
            return redirect('academic:publication_list')
        else:
            return redirect('academic:profile')


class ScopusSyncView(LoginRequiredMixin, View):
    """
    Handle Scopus synchronization requests
    """
    login_url = '/accounts/login/'
    
    def post(self, request):
        """Handle Scopus sync request"""
        user = request.user
        
        # Check if user has Scopus ID
        if not user.has_scopus_id:
            messages.error(request, 'Scopus ID not set. Please set your Scopus ID in your profile first.')
            return redirect('academic:profile')
        
        try:
            # Call the sync management command for this specific user
            messages.info(request, 'Starting Scopus sync...')
            
            # Use call_command to run the sync_scopus management command
            from io import StringIO
            import sys
            
            # Capture output
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                call_command('sync_scopus', user_id=user.id, verbosity=1)
                output = captured_output.getvalue()
                
                # Check if sync was successful based on output
                if 'completed successfully' in output:
                    messages.success(request, 'Scopus sync completed successfully! Check your publications.')
                elif 'No publications found' in output:
                    messages.warning(request, 'Scopus sync completed, but no publications were found.')
                else:
                    messages.info(request, 'Scopus sync completed.')
                
                logger.info(f"Scopus sync for user {user.id}: {output}")
                
            except Exception as e:
                messages.error(request, f'Scopus sync failed: {str(e)}')
                logger.error(f"Scopus sync error for user {user.id}: {str(e)}")
            finally:
                sys.stdout = old_stdout
        
        except Exception as e:
            messages.error(request, f'Failed to start Scopus sync: {str(e)}')
            logger.error(f"Failed to start Scopus sync for user {user.id}: {str(e)}")
        
        # Redirect back to the appropriate page
        next_page = request.POST.get('next', 'academic:profile')
        if 'publication' in next_page:
            return redirect('academic:publication_list')
        else:
            return redirect('academic:profile')


class PubMedSyncView(LoginRequiredMixin, View):
    """
    Handle PubMed synchronization requests
    """
    login_url = "/accounts/login/"
    
    def post(self, request):
        """Handle PubMed sync request"""
        user = request.user
        
        # Check if user has PubMed query
        if not user.has_pubmed_query:
            messages.error(request, "PubMed query not set. Please set your PubMed query in your profile first.")
            return redirect("academic:profile")
        
        try:
            # Call the sync management command for this specific user
            messages.info(request, "Starting PubMed sync...")
            
            # Use call_command to run the sync_pubmed management command
            from io import StringIO
            import sys
            
            # Capture output
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                call_command("sync_pubmed", user_id=user.id, verbosity=1)
                output = captured_output.getvalue()
                
                # Check if sync was successful based on output
                if "completed successfully" in output:
                    messages.success(request, "PubMed sync completed successfully! Check your publications.")
                elif "No publications found" in output:
                    messages.warning(request, "PubMed sync completed, but no publications were found.")
                else:
                    messages.info(request, "PubMed sync completed.")
                
                logger.info(f"PubMed sync for user {user.id}: {output}")
                
            except Exception as e:
                messages.error(request, f"PubMed sync failed: {str(e)}")
                logger.error(f"PubMed sync error for user {user.id}: {str(e)}")
            finally:
                sys.stdout = old_stdout
        
        except Exception as e:
            messages.error(request, f"Failed to start PubMed sync: {str(e)}")
            logger.error(f"Failed to start PubMed sync for user {user.id}: {str(e)}")
        
        # Redirect back to the appropriate page
        next_page = request.POST.get("next", "academic:profile")
        if "publication" in next_page:
            return redirect("academic:publication_list")
        else:
            return redirect("academic:profile")


def run_comprehensive_sync_background(user_id, sync_id):
    """
    Run comprehensive sync in background thread with progress tracking
    """
    import uuid
    from django.contrib.auth import get_user_model

    User = get_user_model()

    # Get existing progress tracking (already initialized by the view)
    if sync_id not in sync_progress:
        # Fallback initialization if somehow missing
        sync_progress[sync_id] = {
            'status': 'starting',
            'phase': 'Initialization',
            'current_step': 'Starting sync...',
            'progress': 0,
            'total_steps': 100,
            'start_time': time.time(),
            'messages': [],
            'publications_added': 0,
            'errors': []
        }
    
    try:
        user = User.objects.get(id=user_id)
        progress = sync_progress[sync_id]

        logger.info(f"Starting comprehensive sync for user {user_id} with sync_id {sync_id}")
        
        # Phase 1: Database Synchronization
        progress.update({
            'status': 'running',
            'phase': 'Database Synchronization',
            'current_step': 'Checking ORCID connection...',
            'progress': 10
        })
        
        # Check sync sources and estimate steps
        sources = []
        if user.is_orcid_connected:
            sources.append('ORCID')
        if user.has_pubmed_query:
            sources.append('PubMed')
        if user.has_scopus_id:
            sources.append('Scopus')
            
        if not sources:
            progress.update({
                'status': 'error',
                'current_step': 'No sync sources configured',
                'progress': 100
            })
            return sync_id
        
        steps_per_source = 30
        enrichment_steps = 20
        postprocessing_steps = 15
        total_estimated_steps = len(sources) * steps_per_source + enrichment_steps + postprocessing_steps
        progress['total_steps'] = total_estimated_steps
        current_step = 10
        
        initial_count = user.publications.count()
        
        # Run syncs for each source
        for i, source in enumerate(sources):
            progress.update({
                'current_step': f'Syncing {source}...',
                'progress': current_step
            })
            
            try:
                if source == 'ORCID':
                    call_command('sync_orcid', user_id=user.id, verbosity=0)
                    progress['messages'].append(f'✓ ORCID sync completed')
                elif source == 'PubMed':
                    call_command('sync_pubmed', user_id=user.id, verbosity=0)
                    progress['messages'].append(f'✓ PubMed sync completed')
                elif source == 'Scopus':
                    call_command('sync_scopus', user_id=user.id, verbosity=0)
                    progress['messages'].append(f'✓ Scopus sync completed')
                    
                current_step += steps_per_source
                progress['progress'] = current_step
                
            except Exception as e:
                progress['errors'].append(f'{source} sync failed: {str(e)}')
                progress['messages'].append(f'✗ {source} sync failed')
        
        # Phase 2: Data Enrichment
        progress.update({
            'phase': 'Data Enrichment',
            'current_step': 'Enriching publications with CrossRef...',
            'progress': current_step
        })

        try:
            call_command('enrich_crossref', user_id=user.id, verbosity=0)
            progress['messages'].append('✓ CrossRef enrichment completed')
        except Exception as e:
            progress['errors'].append(f'CrossRef enrichment failed: {str(e)}')
            progress['messages'].append('✗ CrossRef enrichment failed')

        current_step += enrichment_steps
        progress['progress'] = current_step
        
        # Phase 3: Post-Processing
        progress.update({
            'phase': 'Post-Processing',
            'current_step': 'Running post-processing tasks...',
            'progress': current_step
        })
        
        postprocessing_tasks = [
            ('lookup_pmc_ids', 'PMC ID lookup'),
            ('enrich_scopus_authors', 'DOI-based Scopus author ID enrichment'),
        ]

        steps_per_postprocess = postprocessing_steps // len(postprocessing_tasks)  # Distribute remaining steps evenly

        for command_name, description in postprocessing_tasks:
            try:
                progress['current_step'] = f'Running {description}...'
                progress['progress'] = current_step
                call_command(command_name, user_id=user.id, verbosity=0)
                progress['messages'].append(f'✓ {description} completed')
                current_step += steps_per_postprocess
                progress['progress'] = current_step
            except Exception as e:
                progress['errors'].append(f'{description} failed: {str(e)}')
                progress['messages'].append(f'✗ {description} failed')
                current_step += steps_per_postprocess  # Still advance progress even on error
        
        # Final statistics
        final_count = user.publications.count()
        publications_added = final_count - initial_count
        progress['publications_added'] = publications_added
        
        # Complete
        progress.update({
            'status': 'completed',
            'phase': 'Completed',
            'current_step': f'Sync completed! Added {publications_added} publications.',
            'progress': 100,
            'end_time': time.time()
        })

        if progress['errors']:
            progress['status'] = 'completed_with_errors'

        # Schedule cleanup of old progress entries (after 5 minutes)
        def cleanup_old_progress():
            time.sleep(300)  # Wait 5 minutes
            current_time = time.time()
            to_remove = []
            for sid, data in sync_progress.items():
                if data.get('end_time') and (current_time - data['end_time']) > 300:  # 5 minutes old
                    to_remove.append(sid)
            for sid in to_remove:
                sync_progress.pop(sid, None)

        cleanup_thread = threading.Thread(target=cleanup_old_progress, daemon=True)
        cleanup_thread.start()
            
    except Exception as e:
        progress.update({
            'status': 'error',
            'current_step': f'Sync failed: {str(e)}',
            'progress': 100,
            'end_time': time.time()
        })
        progress['errors'].append(str(e))

        # Schedule cleanup for error case too
        def cleanup_old_progress():
            time.sleep(300)  # Wait 5 minutes
            current_time = time.time()
            to_remove = []
            for sid, data in sync_progress.items():
                if data.get('end_time') and (current_time - data['end_time']) > 300:  # 5 minutes old
                    to_remove.append(sid)
            for sid in to_remove:
                sync_progress.pop(sid, None)

        cleanup_thread = threading.Thread(target=cleanup_old_progress, daemon=True)
        cleanup_thread.start()
    
    return sync_id


class ComprehensiveSyncView(LoginRequiredMixin, View):
    """
    Handle comprehensive synchronization requests - one button to sync everything
    """
    login_url = '/accounts/login/'
    
    def post(self, request):
        """Start comprehensive sync in background and return sync ID"""
        user = request.user
        
        # Check if user has at least one sync source configured
        has_orcid = user.is_orcid_connected
        has_pubmed = user.has_pubmed_query
        has_scopus = user.has_scopus_id
        
        if not (has_orcid or has_pubmed or has_scopus):
            messages.error(
                request, 
                'No sync sources configured. Please connect ORCID, set PubMed query, or add Scopus ID in your profile.'
            )
            return redirect('academic:profile')
        
        # Check if user already has a sync running
        active_syncs = [sid for sid, data in sync_progress.items()
                       if sid.startswith(f'sync_{user.id}_') and data['status'] in ['starting', 'running']]
        
        if active_syncs:
            messages.warning(request, 'A sync is already in progress. Please wait for it to complete.')
            return redirect('academic:dashboard')
        
        # Start background sync
        try:
            # Generate sync_id before starting thread
            sync_id = f"sync_{user.id}_{int(time.time())}"

            # Pre-initialize progress tracking to avoid race conditions
            sync_progress[sync_id] = {
                'status': 'starting',
                'phase': 'Initialization',
                'current_step': 'Starting sync...',
                'progress': 0,
                'total_steps': 100,
                'start_time': time.time(),
                'messages': [],
                'publications_added': 0,
                'errors': []
            }

            sync_thread = threading.Thread(
                target=run_comprehensive_sync_background,
                args=(user.id, sync_id),
                daemon=True
            )
            sync_thread.start()

            # Store sync info in session for frontend tracking
            if 'sync_ids' not in request.session:
                request.session['sync_ids'] = []

            request.session['sync_ids'].append(sync_id)
            request.session.modified = True
            
            # Inform user what will be synced
            sync_sources = []
            if has_orcid:
                sync_sources.append('ORCID')
            if has_pubmed:
                sync_sources.append('PubMed')
            if has_scopus:
                sync_sources.append('Scopus')
            
            sources_str = ', '.join(sync_sources)

            # Return appropriate response based on request type
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                # AJAX request - return JSON response
                return JsonResponse({
                    'success': True,
                    'message': f'Started comprehensive sync from: {sources_str}',
                    'sync_id': sync_id
                })
            else:
                # Regular form submission - redirect with message
                messages.success(request, f'Started comprehensive sync from: {sources_str}. Check progress on your dashboard.')
                return redirect('academic:dashboard')

        except Exception as e:
            error_msg = f'Failed to start comprehensive sync: {str(e)}'
            logger.error(f"Failed to start comprehensive sync for user {user.id}: {str(e)}")

            # Return appropriate error response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                })
            else:
                messages.error(request, error_msg)
                return redirect('academic:dashboard')


class SyncStatusView(LoginRequiredMixin, View):
    """
    AJAX endpoint to check sync status and provide progress updates
    """
    login_url = '/accounts/login/'
    
    def get(self, request):
        """Return sync status for the current user"""
        user = request.user
        
        # Check for active sync progress
        user_syncs = {sid: data for sid, data in sync_progress.items()
                     if sid.startswith(f'sync_{user.id}_')}
        
        # Find most recent sync
        active_sync = None
        if user_syncs:
            latest_sync_id = max(user_syncs.keys(), 
                               key=lambda x: user_syncs[x].get('start_time', 0))
            active_sync = user_syncs[latest_sync_id]
            active_sync['sync_id'] = latest_sync_id
        
        # Check last sync times and general status
        sync_status = {
            'orcid_connected': user.is_orcid_connected,
            'pubmed_configured': user.has_pubmed_query,
            'scopus_configured': user.has_scopus_id,
            'last_sync': user.last_orcid_sync.isoformat() if user.last_orcid_sync else None,
            'publication_count': user.publications.count() if hasattr(user, 'publications') else 0,
            'sync_sources': [],
            'active_sync': active_sync
        }
        
        # Build list of available sync sources
        if user.is_orcid_connected:
            sync_status['sync_sources'].append('ORCID')
        if user.has_pubmed_query:
            sync_status['sync_sources'].append('PubMed')  
        if user.has_scopus_id:
            sync_status['sync_sources'].append('Scopus')
            
        return JsonResponse(sync_status)


class SyncProgressStreamView(LoginRequiredMixin, View):
    """
    Server-Sent Events endpoint for real-time sync progress updates
    """
    login_url = '/accounts/login/'
    
    def get(self, request):
        """Stream sync progress updates using Server-Sent Events"""
        user = request.user
        
        def event_stream():
            # Find active sync for this user
            user_syncs = {sid: data for sid, data in sync_progress.items()
                         if sid.startswith(f'sync_{user.id}_')}

            logger.info(f"Progress stream requested for user {user.id}, found syncs: {list(user_syncs.keys())}")

            if not user_syncs:
                logger.warning(f"No active sync found for user {user.id}")
                yield f"data: {json.dumps({'error': 'No active sync found'})}\n\n"
                return

            # Get most recent sync
            latest_sync_id = max(user_syncs.keys(),
                               key=lambda x: user_syncs[x].get('start_time', 0))

            logger.info(f"Streaming progress for sync {latest_sync_id}")

            last_progress = -1
            start_time = time.time()
            max_duration = 600  # 10 minutes maximum

            while True:
                # Check for timeout to prevent infinite connections
                if time.time() - start_time > max_duration:
                    yield f"data: {json.dumps({'error': 'Progress stream timeout'})}\n\n"
                    break

                if latest_sync_id in sync_progress:
                    progress_data = sync_progress[latest_sync_id].copy()
                    current_progress = progress_data.get('progress', 0)

                    # Only send update if progress changed
                    if current_progress != last_progress:
                        yield f"data: {json.dumps(progress_data)}\n\n"
                        last_progress = current_progress

                    # Stop streaming if completed or failed
                    if progress_data.get('status') in ['completed', 'completed_with_errors', 'error']:
                        yield f"data: {json.dumps(progress_data)}\n\n"
                        break

                else:
                    # Sync not found - maybe it completed already
                    yield f"data: {json.dumps({'status': 'completed', 'message': 'Sync completed'})}\n\n"
                    break

                time.sleep(2)  # Poll every 2 seconds to reduce load
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
        return response


class ClearPublicationsView(LoginRequiredMixin, View):
    """
    Handle clearing all publications for the current user
    """
    login_url = '/accounts/login/'
    
    def post(self, request):
        """Clear all publications for the current user"""
        user = request.user
        
        # Security check - require confirmation parameter
        confirmation = request.POST.get('confirmation', '').lower()
        if confirmation != 'delete all publications':
            messages.error(
                request, 
                'Invalid confirmation. You must type "delete all publications" exactly to confirm.'
            )
            return redirect('academic:dashboard')
        
        try:
            # Count publications before deletion for reporting
            pub_count = user.publications.count() if hasattr(user, 'publications') else 0
            
            if pub_count == 0:
                messages.warning(request, 'No publications found to delete.')
                return redirect('academic:dashboard')
            
            # Delete all publications for this user
            deleted_count = user.publications.all().delete()[0]
            
            # Log the action
            logger.info(f"User {user.id} ({user.username}) cleared {deleted_count} publications")
            
            # Update user's last sync time to reflect the change
            user.last_orcid_sync = timezone.now()
            user.save(update_fields=['last_orcid_sync'])
            
            messages.success(
                request,
                f'Successfully deleted {deleted_count} publications from your database. '
                f'You can re-sync from your external sources using the sync button.'
            )
            
        except Exception as e:
            messages.error(request, f'Failed to clear publications: {str(e)}')
            logger.error(f"Error clearing publications for user {user.id}: {str(e)}")
        
        return redirect('academic:dashboard')


class FundingListView(LoginRequiredMixin, ListView):
    """
    List all funding for the current user
    """
    model = Funding
    template_name = 'academic/funding_list.html'
    context_object_name = 'funding_list'
    paginate_by = 20
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Filter funding to show only those owned by the current user"""
        return Funding.objects.filter(owner=self.request.user).order_by('-start_date', 'title')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'My Funding'
        context['funding_count'] = self.get_queryset().count()
        return context


class FundingDetailView(LoginRequiredMixin, DetailView):
    """
    Display details of a single funding record
    """
    model = Funding
    template_name = 'academic/funding_detail.html'
    context_object_name = 'funding'
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only view their own funding"""
        return Funding.objects.filter(owner=self.request.user)


class FundingCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new funding record manually
    """
    model = Funding
    template_name = 'academic/funding_form.html'
    fields = ['title', 'agency', 'grant_number', 'amount', 'currency', 
              'start_date', 'end_date', 'role', 'status']
    success_url = reverse_lazy('academic:funding_list')
    login_url = '/accounts/login/'
    
    def form_valid(self, form):
        """Set the owner to the current user and mark as manual entry"""
        form.instance.owner = self.request.user
        form.instance.source = 'manual'
        
        messages.success(self.request, 'Funding record added successfully!')
        return super().form_valid(form)


class FundingUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing funding record
    """
    model = Funding
    template_name = 'academic/funding_form.html'
    fields = ['title', 'agency', 'grant_number', 'amount', 'currency', 
              'start_date', 'end_date', 'role', 'status']
    success_url = reverse_lazy('academic:funding_list')
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only edit their own funding"""
        return Funding.objects.filter(owner=self.request.user)
    
    def form_valid(self, form):
        """Track manual edits"""
        # Get changed fields
        changed_fields = form.changed_data
        
        if changed_fields:
            # Use the save_with_edit_protection method
            obj = form.save(commit=False)
            obj.save_with_edit_protection(
                user_edit=True,
                edited_fields=changed_fields
            )
            messages.success(self.request, 'Funding record updated successfully!')
            return redirect(self.success_url)
        
        return super().form_valid(form)


class ClearFundingView(LoginRequiredMixin, View):
    """
    Handle clearing all funding records for the current user
    """
    login_url = '/accounts/login/'
    
    def post(self, request):
        """Clear all funding records for the current user"""
        user = request.user
        
        # Security check - require confirmation parameter
        confirmation = request.POST.get('confirmation', '').lower()
        if confirmation != 'delete all funding':
            messages.error(
                request, 
                'Invalid confirmation. You must type "delete all funding" exactly to confirm.'
            )
            return redirect('academic:funding_list')
        
        try:
            # Count funding records before deletion for reporting
            funding_count = user.funding.count() if hasattr(user, 'funding') else 0
            
            if funding_count == 0:
                messages.warning(request, 'No funding records found to delete.')
                return redirect('academic:funding_list')
            
            # Delete all funding records for this user
            deleted_count = user.funding.all().delete()[0]
            
            # Log the action
            logger.info(f"User {user.id} cleared {deleted_count} funding records via web interface")
            
            # Success message
            messages.success(
                request, 
                f'Successfully deleted {deleted_count} funding records. You can re-sync from ORCID or add new funding manually.'
            )
            
            return redirect('academic:funding_list')
            
        except Exception as e:
            logger.error(f"Error clearing funding for user {user.id}: {str(e)}")
            messages.error(
                request, 
                'An error occurred while deleting funding records. Please try again.'
            )
            return redirect('academic:funding_list')


# Teaching Views
class TeachingListView(LoginRequiredMixin, ListView):
    """
    List all teaching activities for the current user
    """
    model = Teaching
    template_name = 'academic/teaching_list.html'
    context_object_name = 'teaching_list'
    paginate_by = 20
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Filter teaching to show only those owned by the current user"""
        return Teaching.objects.filter(owner=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'My Teaching'
        context['teaching_count'] = self.get_queryset().count()
        return context


class TeachingDetailView(LoginRequiredMixin, DetailView):
    """
    Display details of a single teaching activity
    """
    model = Teaching
    template_name = 'academic/teaching_detail.html'
    context_object_name = 'teaching'
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only view their own teaching"""
        return Teaching.objects.filter(owner=self.request.user)


class TeachingCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new teaching activity
    """
    model = Teaching
    template_name = 'academic/teaching_form.html'
    fields = ['name', 'level', 'course_number', 'semester', 'year', 
              'institution', 'enrollment']
    success_url = reverse_lazy('academic:teaching_list')
    login_url = '/accounts/login/'
    
    def form_valid(self, form):
        """Set the owner to the current user and mark as manual entry"""
        form.instance.owner = self.request.user
        form.instance.source = 'manual'
        
        messages.success(self.request, 'Teaching activity added successfully!')
        return super().form_valid(form)


class TeachingUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing teaching activity
    """
    model = Teaching
    template_name = 'academic/teaching_form.html'
    fields = ['name', 'level', 'course_number', 'semester', 'year', 
              'institution', 'enrollment']
    success_url = reverse_lazy('academic:teaching_list')
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only edit their own teaching"""
        return Teaching.objects.filter(owner=self.request.user)
    
    def form_valid(self, form):
        """Track manual edits"""
        changed_fields = form.changed_data
        
        if changed_fields:
            obj = form.save(commit=False)
            # Mark fields as manually edited
            for field_name in changed_fields:
                obj.manual_edits[field_name] = True
            obj.save()
            messages.success(self.request, 'Teaching activity updated successfully!')
            return redirect(self.success_url)
        
        return super().form_valid(form)


# Talk Views
class TalkListView(LoginRequiredMixin, ListView):
    """
    List all talks for the current user
    """
    model = Talk
    template_name = 'academic/talk_list.html'
    context_object_name = 'talk_list'
    paginate_by = 20
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Filter talks to show only those owned by the current user"""
        return Talk.objects.filter(owner=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'My Talks'
        context['talk_count'] = self.get_queryset().count()
        return context


class TalkDetailView(LoginRequiredMixin, DetailView):
    """
    Display details of a single talk
    """
    model = Talk
    template_name = 'academic/talk_detail.html'
    context_object_name = 'talk'
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only view their own talks"""
        return Talk.objects.filter(owner=self.request.user)


class TalkCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new talk
    """
    model = Talk
    template_name = 'academic/talk_form.html'
    fields = ['year', 'place', 'title', 'date', 'invited', 'virtual']
    success_url = reverse_lazy('academic:talk_list')
    login_url = '/accounts/login/'
    
    def form_valid(self, form):
        """Set the owner to the current user and mark as manual entry"""
        form.instance.owner = self.request.user
        form.instance.source = 'manual'
        
        messages.success(self.request, 'Talk added successfully!')
        return super().form_valid(form)


class TalkUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing talk
    """
    model = Talk
    template_name = 'academic/talk_form.html'
    fields = ['year', 'place', 'title', 'date', 'invited', 'virtual']
    success_url = reverse_lazy('academic:talk_list')
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only edit their own talks"""
        return Talk.objects.filter(owner=self.request.user)
    
    def form_valid(self, form):
        """Track manual edits"""
        changed_fields = form.changed_data
        
        if changed_fields:
            obj = form.save(commit=False)
            # Mark fields as manually edited
            for field_name in changed_fields:
                obj.manual_edits[field_name] = True
            obj.save()
            messages.success(self.request, 'Talk updated successfully!')
            return redirect(self.success_url)
        
        return super().form_valid(form)


# Conference Views
class ConferenceListView(LoginRequiredMixin, ListView):
    """
    List all conference presentations for the current user
    """
    model = Conference
    template_name = 'academic/conference_list.html'
    context_object_name = 'conference_list'
    paginate_by = 20
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Filter conferences to show only those owned by the current user"""
        return Conference.objects.filter(owner=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'My Conference Presentations'
        context['conference_count'] = self.get_queryset().count()
        return context


class ConferenceDetailView(LoginRequiredMixin, DetailView):
    """
    Display details of a single conference presentation
    """
    model = Conference
    template_name = 'academic/conference_detail.html'
    context_object_name = 'conference'
    login_url = '/accounts/login/'

    def get_queryset(self):
        """Ensure users can only view their own conferences"""
        return Conference.objects.filter(owner=self.request.user)


class ProfessionalActivityListView(LoginRequiredMixin, ListView):
    """
    List all professional activities for the current user
    """
    model = ProfessionalActivity
    template_name = 'academic/professional_activity_list.html'
    context_object_name = 'professional_activities'
    paginate_by = 20
    login_url = '/accounts/login/'

    def get_queryset(self):
        """Filter professional activities to show only those owned by the current user"""
        return ProfessionalActivity.objects.filter(owner=self.request.user).order_by('-is_current', '-start_date', 'title')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Professional Activities'
        context['activity_count'] = self.get_queryset().count()

        # Get counts by activity type
        activities_by_type = {}
        for activity in self.get_queryset():
            activity_type = activity.get_activity_type_display()
            activities_by_type[activity_type] = activities_by_type.get(activity_type, 0) + 1

        context['activities_by_type'] = activities_by_type
        return context


class ConferenceCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new conference presentation
    """
    model = Conference
    template_name = 'academic/conference_form.html'
    fields = ['title', 'authors', 'year', 'location', 'month', 
              'conference_name', 'presentation_type', 'link', 'abstract']
    success_url = reverse_lazy('academic:conference_list')
    login_url = '/accounts/login/'
    
    def form_valid(self, form):
        """Set the owner to the current user and mark as manual entry"""
        form.instance.owner = self.request.user
        form.instance.source = 'manual'
        
        messages.success(self.request, 'Conference presentation added successfully!')
        return super().form_valid(form)


class ConferenceUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing conference presentation
    """
    model = Conference
    template_name = 'academic/conference_form.html'
    fields = ['title', 'authors', 'year', 'location', 'month', 
              'conference_name', 'presentation_type', 'link', 'abstract']
    success_url = reverse_lazy('academic:conference_list')
    login_url = '/accounts/login/'
    
    def get_queryset(self):
        """Ensure users can only edit their own conferences"""
        return Conference.objects.filter(owner=self.request.user)
    
    def form_valid(self, form):
        """Track manual edits"""
        changed_fields = form.changed_data
        
        if changed_fields:
            obj = form.save(commit=False)
            # Mark fields as manually edited
            for field_name in changed_fields:
                obj.manual_edits[field_name] = True
            obj.save()
            messages.success(self.request, 'Conference presentation updated successfully!')
            return redirect(self.success_url)

        return super().form_valid(form)


# Spreadsheet Views
class TeachingSpreadsheetView(LoginRequiredMixin, TemplateView):
    """Teaching spreadsheet view"""
    template_name = 'academic/teaching_spreadsheet.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = 'Teaching'
        context['container_id'] = 'teaching-spreadsheet-container'
        context['list_view_url'] = 'academic:teaching_list'
        return context


class TeachingSpreadsheetIframeView(LoginRequiredMixin, TemplateView):
    """Teaching spreadsheet iframe view - isolated from Django CSS"""
    template_name = 'academic/spreadsheet_iframe.html'
    login_url = '/accounts/login/'

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Allow this view to be displayed in an iframe from the same origin
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response


class TalksSpreadsheetView(LoginRequiredMixin, TemplateView):
    """Talks spreadsheet view"""
    template_name = 'academic/talks_spreadsheet.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = 'Talks'
        context['container_id'] = 'talks-spreadsheet-container'
        context['list_view_url'] = 'academic:talk_list'
        return context


class ConferencesSpreadsheetView(LoginRequiredMixin, TemplateView):
    """Conferences spreadsheet view"""
    template_name = 'academic/conferences_spreadsheet.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['model_name'] = 'Conferences'
        context['container_id'] = 'conferences-spreadsheet-container'
        context['list_view_url'] = 'academic:conference_list'
        return context


class TalksSpreadsheetIframeView(LoginRequiredMixin, TemplateView):
    """Talks spreadsheet iframe view - isolated from Django CSS"""
    template_name = 'academic/spreadsheet_iframe.html'
    login_url = '/accounts/login/'

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Allow this view to be displayed in an iframe from the same origin
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response


class ConferencesSpreadsheetIframeView(LoginRequiredMixin, TemplateView):
    """Conferences spreadsheet iframe view - isolated from Django CSS"""
    template_name = 'academic/spreadsheet_iframe.html'
    login_url = '/accounts/login/'

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Allow this view to be displayed in an iframe from the same origin
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response


# Admin Views for Tools and Administration

class AdminPanelView(LoginRequiredMixin, TemplateView):
    """
    Main admin/tools panel providing access to various administrative functions
    """
    template_name = 'academic/admin_panel.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Tools & Administration'

        # Count user's data for stats
        user = self.request.user
        context['stats'] = {
            'publications': user.publications.count() if hasattr(user, 'publications') else 0,
            'funding': user.funding.count() if hasattr(user, 'funding') else 0,
            'teaching': user.teaching.count() if hasattr(user, 'teaching') else 0,
            'talks': user.talks.count() if hasattr(user, 'talks') else 0,
            'conferences': user.conferences.count() if hasattr(user, 'conferences') else 0,
            'professional_activities': user.professional_activities.count() if hasattr(user, 'professional_activities') else 0,
        }

        # Check backup directory status
        backup_root = Path('/app/backups/json')
        context['backup_stats'] = {
            'backup_dir_exists': backup_root.exists(),
            'backup_count': len(list(backup_root.glob('backup_*'))) if backup_root.exists() else 0,
        }

        # API Cache statistics (user-specific)
        from .models import APIRecordCache, Publication
        from django.db.models import Q

        # Get DOIs from user's publications
        user_dois = list(Publication.objects.filter(
            owner=user,
            doi__isnull=False
        ).exclude(doi='').values_list('doi', flat=True))

        # Get PMIDs from user's publications
        user_pmids = []
        for pub in Publication.objects.filter(owner=user):
            if pub.identifiers and 'pmid' in pub.identifiers:
                user_pmids.append(str(pub.identifiers['pmid']))

        # Build query for user's cache records
        cache_query = Q()
        if user_dois:
            normalized_dois = [doi.lower() for doi in user_dois]
            cache_query |= Q(doi__in=normalized_dois)
        if user_pmids:
            cache_query |= Q(pmid__in=user_pmids)

        # Get user-specific cache stats
        if cache_query:
            user_cache = APIRecordCache.objects.filter(cache_query)
            context['cache_stats'] = {
                'total_records': user_cache.count(),
                'scopus_records': user_cache.filter(api_source='scopus').count(),
                'pubmed_records': user_cache.filter(api_source='pubmed').count(),
                'crossref_records': user_cache.filter(api_source='crossref').count(),
            }
        else:
            context['cache_stats'] = {
                'total_records': 0,
                'scopus_records': 0,
                'pubmed_records': 0,
                'crossref_records': 0,
            }

        return context


class AdminBackupView(LoginRequiredMixin, TemplateView):
    """
    Admin interface for database backup and restore
    """
    template_name = 'admin/backup_restore.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Database Backup & Restore'

        # List existing backup directories
        backup_root = Path('/app/backups/json')
        backups = []

        if backup_root.exists():
            for backup_dir in sorted(backup_root.glob('backup_*'), reverse=True):
                if backup_dir.is_dir():
                    info_file = backup_dir / 'backup_info.json'
                    if info_file.exists():
                        try:
                            with open(info_file, 'r') as f:
                                backup_info = json.load(f)

                            # Calculate backup size
                            total_size = sum(f.stat().st_size for f in backup_dir.rglob('*.json'))
                            size_mb = total_size / (1024 * 1024)

                            backups.append({
                                'name': backup_dir.name,
                                'path': str(backup_dir),
                                'date': backup_info.get('backup_date', 'Unknown'),
                                'users': backup_info.get('total_users', 'Unknown'),
                                'format': backup_info.get('backup_format', 'Unknown'),
                                'size_mb': round(size_mb, 2),
                                'stats': backup_info.get('stats', {}),
                                'files': len(backup_info.get('files', [])) + 1  # +1 for backup_info.json
                            })
                        except (json.JSONDecodeError, OSError):
                            # Invalid backup, skip
                            continue

        context['backups'] = backups
        return context


class AdminBackupCreateView(LoginRequiredMixin, View):
    """
    Handle backup creation requests from admin
    """
    login_url = '/accounts/login/'

    def post(self, request):
        """Create a new backup"""
        backup_format = request.POST.get('format', 'separate')
        exclude_cache = 'exclude_cache' in request.POST
        user_id = request.POST.get('user_id')

        # Capture command output
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            # Build command arguments
            args = ['--format', backup_format, '--output-dir', 'backups/json']
            if exclude_cache:
                args.append('--exclude-cache')
            if user_id and user_id.strip():
                args.extend(['--user-id', user_id])

            call_command('backup_data', *args, verbosity=1)
            output = captured_output.getvalue()

            # Parse the output to get backup directory
            backup_dir = None
            for line in output.split('\n'):
                if 'Directory:' in line:
                    backup_dir = line.split('Directory:')[1].strip()
                    break

            if backup_dir:
                messages.success(request, f'Backup created successfully in: {backup_dir}')
            else:
                messages.success(request, 'Backup created successfully!')

            logger.info(f"Admin backup created by user {request.user.id}: {output}")

        except Exception as e:
            messages.error(request, f'Backup failed: {str(e)}')
            logger.error(f"Admin backup failed for user {request.user.id}: {str(e)}")
        finally:
            sys.stdout = old_stdout

        return redirect('academic:admin_backup')


class AdminBackupRestoreView(LoginRequiredMixin, View):
    """
    Handle restore requests from admin
    """
    login_url = '/accounts/login/'

    def post(self, request):
        """Restore from a backup"""
        backup_dir = request.POST.get('backup_dir')
        merge = 'merge' in request.POST
        exclude_users = 'exclude_users' in request.POST
        exclude_cache = 'exclude_cache' in request.POST
        user_id = request.POST.get('user_id')

        if not backup_dir:
            messages.error(request, 'No backup directory specified')
            return redirect('academic:admin_backup')

        # Safety check
        confirmation = request.POST.get('confirmation', '').lower()
        if confirmation != 'restore database':
            messages.error(request, 'Invalid confirmation. You must type "restore database" exactly to confirm.')
            return redirect('academic:admin_backup')

        # Capture command output
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            # Build command arguments
            args = ['--backup-dir', backup_dir]
            if merge:
                args.append('--merge')
            if exclude_users:
                args.append('--exclude-users')
            if exclude_cache:
                args.append('--exclude-cache')
            if user_id and user_id.strip():
                args.extend(['--user-id', user_id])

            call_command('restore_data', *args, verbosity=1)
            output = captured_output.getvalue()

            if 'Restore completed!' in output:
                messages.success(request, 'Database restored successfully!')
            else:
                messages.success(request, 'Restore operation completed.')

            logger.info(f"Admin restore performed by user {request.user.id}: {output}")

        except Exception as e:
            messages.error(request, f'Restore failed: {str(e)}')
            logger.error(f"Admin restore failed for user {request.user.id}: {str(e)}")
        finally:
            sys.stdout = old_stdout

        return redirect('academic:admin_backup')


class AdminBackupDownloadView(LoginRequiredMixin, View):
    """
    Download backup files from admin interface
    """
    login_url = '/accounts/login/'

    def get(self, request, backup_name):
        """Download a backup as zip file"""
        backup_dir = Path('/app/backups/json') / backup_name

        if not backup_dir.exists() or not backup_dir.is_dir():
            messages.error(request, f'Backup {backup_name} not found')
            return redirect('academic:admin_backup')

        # Create zip file in memory
        import zipfile
        from django.http import HttpResponse

        response = HttpResponse(content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{backup_name}.zip"'

        with zipfile.ZipFile(response, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in backup_dir.rglob('*.json'):
                zip_file.write(file_path, file_path.relative_to(backup_dir))

        return response


class AdminBackupDeleteView(LoginRequiredMixin, View):
    """
    Delete backup from admin interface
    """
    login_url = '/accounts/login/'

    def post(self, request, backup_name):
        """Delete a backup directory"""
        backup_dir = Path('/app/backups/json') / backup_name

        if not backup_dir.exists():
            messages.error(request, f'Backup {backup_name} not found')
            return redirect('academic:admin_backup')

        # Safety check
        confirmation = request.POST.get('confirmation', '').lower()
        if confirmation != 'delete backup':
            messages.error(request, 'Invalid confirmation. You must type "delete backup" exactly to confirm.')
            return redirect('academic:admin_backup')

        try:
            # Remove the backup directory and all its contents
            import shutil
            shutil.rmtree(backup_dir)

            messages.success(request, f'Backup {backup_name} deleted successfully')
            logger.info(f"Admin deleted backup {backup_name} by user {request.user.id}")

        except Exception as e:
            messages.error(request, f'Failed to delete backup: {str(e)}')
            logger.error(f"Failed to delete backup {backup_name} by user {request.user.id}: {str(e)}")

        return redirect('academic:admin_backup')


class CVView(LoginRequiredMixin, View):
    """
    Generate and download CV in LaTeX or PDF format
    """
    login_url = '/accounts/login/'

    def get(self, request, format_type='tex'):
        """
        Handle CV generation requests

        Args:
            format_type: 'tex' for LaTeX source, 'pdf' for compiled PDF
        """
        from .cv_renderer import generate_cv_latex, compile_latex_to_pdf

        user = request.user
        exclude_dois = request.GET.get('exclude_dois', '').split(',') if request.GET.get('exclude_dois') else None
        exclude_preprints = request.GET.get('exclude_preprints', '').lower() in ['true', '1', 'on']

        try:
            # Generate LaTeX content
            latex_content = generate_cv_latex(user, exclude_dois, exclude_preprints)

            if format_type == 'tex':
                # Return LaTeX source
                response = HttpResponse(latex_content, content_type='text/plain')
                response['Content-Disposition'] = f'attachment; filename="cv_{user.username}.tex"'
                return response

            elif format_type == 'pdf':
                # Compile to PDF
                compilation_result = compile_latex_to_pdf(latex_content)

                if compilation_result['success']:
                    # Return PDF file
                    with open(compilation_result['pdf_path'], 'rb') as pdf_file:
                        response = HttpResponse(pdf_file.read(), content_type='application/pdf')
                        response['Content-Disposition'] = f'attachment; filename="cv_{user.username}.pdf"'

                    # Clean up temporary files
                    try:
                        import shutil
                        shutil.rmtree(compilation_result['output_dir'])
                    except:
                        pass

                    return response
                else:
                    # PDF compilation failed - log the error and return LaTeX with error message
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f'PDF compilation failed for user {user.username}: {compilation_result["error"]}')
                    logger.debug(f'LaTeX log: {compilation_result.get("log", "No log available")}')

                    messages.error(request, f'PDF compilation failed: {compilation_result["error"]}')
                    messages.info(request, 'You can download the LaTeX source and compile it manually.')

                    # Still offer the LaTeX file
                    response = HttpResponse(latex_content, content_type='text/plain')
                    response['Content-Disposition'] = f'attachment; filename="cv_{user.username}.tex"'
                    return response

            else:
                # Unknown format
                messages.error(request, f'Unknown format: {format_type}')
                return redirect('academic:dashboard')

        except Exception as e:
            logger.error(f"CV generation failed for user {user.id}: {str(e)}")
            messages.error(request, f'CV generation failed: {str(e)}')
            return redirect('academic:dashboard')


class CVPreviewView(LoginRequiredMixin, TemplateView):
    """
    Preview CV generation interface
    """
    template_name = 'academic/cv_preview.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Generate CV'
        context['user'] = self.request.user

        # Get counts for sections
        user = self.request.user
        context['stats'] = {
            'publications': Publication.objects.filter(owner=user, is_ignored=False).count(),
            'funding': Funding.objects.filter(owner=user).count(),
            'teaching': Teaching.objects.filter(owner=user).count(),
            'talks': Talk.objects.filter(owner=user).count(),
            'conferences': Conference.objects.filter(owner=user).count(),
            'employment': ProfessionalActivity.objects.filter(owner=user, activity_type='employment').count(),
            'education': ProfessionalActivity.objects.filter(owner=user, activity_type='education').count(),
        }

        return context


class ClearAPICacheView(LoginRequiredMixin, View):
    """
    Handle clearing all API cache records (Scopus, PubMed, CrossRef)
    Users can clear cache records related to their own publications
    """
    login_url = '/accounts/login/'

    def post(self, request):
        """Clear all API cache records for the current user's publications"""
        user = request.user

        # Security check - require confirmation parameter
        if request.POST.get('confirm') != 'DELETE':
            messages.error(request, 'Confirmation required to clear API cache.')
            return redirect('academic:admin_panel')

        try:
            from .models import APIRecordCache, Publication

            # Get DOIs from user's publications
            user_dois = list(Publication.objects.filter(
                owner=user,
                doi__isnull=False
            ).exclude(doi='').values_list('doi', flat=True))

            # Get PMIDs from user's publications
            user_pmids = []
            for pub in Publication.objects.filter(owner=user):
                if pub.identifiers and 'pmid' in pub.identifiers:
                    user_pmids.append(str(pub.identifiers['pmid']))

            # Build query to find cache records related to user's publications
            from django.db.models import Q
            query = Q()

            # Add DOI-based filtering
            if user_dois:
                # Normalize DOIs for comparison
                normalized_dois = [doi.lower() for doi in user_dois]
                query |= Q(doi__in=normalized_dois)

            # Add PMID-based filtering
            if user_pmids:
                query |= Q(pmid__in=user_pmids)

            # Get cache records related to user's publications
            records_to_delete = APIRecordCache.objects.filter(query) if query else APIRecordCache.objects.none()

            # Count by source before deletion
            scopus_records = records_to_delete.filter(api_source='scopus').count()
            pubmed_records = records_to_delete.filter(api_source='pubmed').count()
            crossref_records = records_to_delete.filter(api_source='crossref').count()
            total_records = records_to_delete.count()

            if total_records == 0:
                messages.info(request, 'No cache records found for your publications.')
                return redirect('academic:admin_panel')

            # Delete the cache records
            deleted_count = records_to_delete.delete()[0]

            # Log the action
            logger.info(f"User {user.id} ({user.username}) cleared {deleted_count} API cache records for their publications")

            # Success message with breakdown
            messages.success(
                request,
                f'Successfully cleared {deleted_count} API cache records for your publications: '
                f'{scopus_records} Scopus, {pubmed_records} PubMed, {crossref_records} CrossRef. '
                f'Future API calls will be slower until the cache is rebuilt.'
            )

        except Exception as e:
            messages.error(request, f'Failed to clear API cache: {str(e)}')
            logger.error(f"Error clearing API cache for user {user.id}: {str(e)}")

        return redirect('academic:admin_panel')


class ClearSpecificAPICacheView(LoginRequiredMixin, View):
    """
    Handle clearing specific API cache records (CrossRef, Scopus, or PubMed)
    Users can clear cache records related to their own publications
    """
    login_url = '/accounts/login/'

    def post(self, request, api_source):
        """Clear specific API cache records for the current user's publications"""
        user = request.user

        # Validate API source
        valid_sources = ['crossref', 'scopus', 'pubmed']
        if api_source not in valid_sources:
            messages.error(request, f'Invalid API source: {api_source}')
            return redirect('academic:admin_panel')

        # Security check - require confirmation parameter
        if request.POST.get('confirm') != 'DELETE':
            messages.error(request, f'Confirmation required to clear {api_source.title()} cache.')
            return redirect('academic:admin_panel')

        try:
            from .models import APIRecordCache, Publication

            # Get DOIs from user's publications
            user_dois = list(Publication.objects.filter(
                owner=user,
                doi__isnull=False
            ).exclude(doi='').values_list('doi', flat=True))

            # Get PMIDs from user's publications
            user_pmids = []
            for pub in Publication.objects.filter(owner=user):
                if pub.identifiers and 'pmid' in pub.identifiers:
                    user_pmids.append(str(pub.identifiers['pmid']))

            # Build query to find cache records related to user's publications
            from django.db.models import Q
            query = Q()

            # Add DOI-based filtering
            if user_dois:
                # Normalize DOIs for comparison
                normalized_dois = [doi.lower() for doi in user_dois]
                query |= Q(doi__in=normalized_dois)

            # Add PMID-based filtering for PubMed cache
            if api_source == 'pubmed' and user_pmids:
                query |= Q(pmid__in=user_pmids)

            # Filter by API source and user's publication identifiers
            records_to_delete = APIRecordCache.objects.filter(
                api_source=api_source
            ).filter(query) if query else APIRecordCache.objects.none()

            record_count = records_to_delete.count()

            if record_count == 0:
                messages.info(request, f'No {api_source.title()} cache records found for your publications.')
                return redirect('academic:admin_panel')

            # Delete the specific cache records
            deleted_count = records_to_delete.delete()[0]

            # Log the action
            logger.info(f"User {user.id} ({user.username}) cleared {deleted_count} {api_source} cache records for their publications")

            # Success message
            messages.success(
                request,
                f'Successfully cleared {deleted_count} {api_source.title()} cache records for your publications. '
                f'Future {api_source} API calls will be slower until the cache is rebuilt.'
            )

        except Exception as e:
            messages.error(request, f'Failed to clear {api_source.title()} cache: {str(e)}')
            logger.error(f"Error clearing {api_source} cache for user {user.id}: {str(e)}")

        return redirect('academic:admin_panel')


# Link Management Views

class LinkListView(LoginRequiredMixin, ListView):
    """
    List view for user's links with CSV upload functionality
    """
    model = Link
    template_name = 'academic/links_list.html'
    context_object_name = 'links'
    login_url = '/accounts/login/'
    paginate_by = 50

    def get_queryset(self):
        return Link.objects.filter(owner=self.request.user).order_by('type', 'doi')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Publication Links'

        # Count links by type
        links_by_type = {}
        for link in self.get_queryset():
            links_by_type[link.type] = links_by_type.get(link.type, 0) + 1
        context['links_by_type'] = links_by_type

        # Check how many publications don't have matching links
        user_pubs = Publication.objects.filter(owner=self.request.user, doi__isnull=False).exclude(doi='')
        user_dois = set(pub.doi.lower() for pub in user_pubs)
        link_dois = set(link.doi.lower() for link in self.get_queryset())
        context['unlinked_publications'] = len(user_dois - link_dois)

        return context


class LinkUploadView(LoginRequiredMixin, View):
    """
    Handle CSV upload for links
    """
    login_url = '/accounts/login/'

    def post(self, request, *args, **kwargs):
        import csv
        from io import StringIO

        if 'csv_file' not in request.FILES:
            messages.error(request, 'No CSV file uploaded.')
            return redirect('academic:links_list')

        csv_file = request.FILES['csv_file']

        # Validate file type
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a CSV file.')
            return redirect('academic:links_list')

        try:
            # Read CSV content
            file_content = csv_file.read().decode('utf-8')
            csv_reader = csv.DictReader(StringIO(file_content))

            # Validate headers
            required_headers = {'type', 'DOI', 'url'}
            if not required_headers.issubset(set(csv_reader.fieldnames)):
                messages.error(request, f'CSV must contain these columns: {", ".join(required_headers)}')
                return redirect('academic:links_list')

            # Process rows
            created_count = 0
            updated_count = 0
            error_count = 0

            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because header is row 1
                try:
                    link_type = row['type'].strip()
                    doi = row['DOI'].strip().lower()
                    url = row['url'].strip()

                    if not all([link_type, doi, url]):
                        error_count += 1
                        continue

                    # Clean DOI
                    if doi.startswith('https://doi.org/'):
                        doi = doi.replace('https://doi.org/', '')
                    elif doi.startswith('http://doi.org/'):
                        doi = doi.replace('http://doi.org/', '')
                    elif doi.startswith('doi:'):
                        doi = doi.replace('doi:', '')

                    # Create or update link
                    link, created = Link.objects.get_or_create(
                        owner=request.user,
                        type=link_type,
                        doi=doi,
                        url=url,
                        defaults={
                            'source': 'csv_import'
                        }
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"Error processing CSV row {row_num}: {str(e)}")

            # Success message
            message_parts = []
            if created_count > 0:
                message_parts.append(f"Created {created_count} links")
            if updated_count > 0:
                message_parts.append(f"Updated {updated_count} links")
            if error_count > 0:
                message_parts.append(f"Skipped {error_count} rows with errors")

            if message_parts:
                messages.success(request, ". ".join(message_parts) + ".")
            else:
                messages.info(request, "No links were processed from the CSV file.")

        except Exception as e:
            messages.error(request, f'Error processing CSV file: {str(e)}')
            logger.error(f"CSV upload error for user {request.user.id}: {str(e)}")

        return redirect('academic:links_list')


class LinkAssociateView(LoginRequiredMixin, View):
    """
    Associate links with publications based on DOI matching
    """
    login_url = '/accounts/login/'

    def post(self, request, *args, **kwargs):
        try:
            associated_count, not_found_dois = Link.associate_with_publications(request.user)

            if associated_count > 0:
                messages.success(
                    request,
                    f'Successfully associated {associated_count} links with publications.'
                )

            if not_found_dois:
                # Limit the display of DOIs to avoid overwhelming the message
                displayed_dois = not_found_dois[:5]
                doi_list = ", ".join(displayed_dois)
                if len(not_found_dois) > 5:
                    doi_list += f", and {len(not_found_dois) - 5} more"

                messages.warning(
                    request,
                    f'Could not find publications for {len(not_found_dois)} DOIs: {doi_list}'
                )

            if associated_count == 0 and not not_found_dois:
                messages.info(request, 'All links are already associated with publications.')

        except Exception as e:
            messages.error(request, f'Error associating links with publications: {str(e)}')
            logger.error(f"Link association error for user {request.user.id}: {str(e)}")

        return redirect('academic:links_list')


class LinkCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new link
    """
    model = Link
    template_name = 'academic/link_form.html'
    fields = ['type', 'doi', 'url', 'title']
    login_url = '/accounts/login/'
    success_url = reverse_lazy('academic:links_list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.source = 'manual'
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add New Link'
        return context


class LinkUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update an existing link
    """
    model = Link
    template_name = 'academic/link_form.html'
    fields = ['type', 'doi', 'url', 'title']
    login_url = '/accounts/login/'
    success_url = reverse_lazy('academic:links_list')

    def get_queryset(self):
        return Link.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Link'
        return context


class LinkDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete a link
    """
    model = Link
    template_name = 'academic/link_confirm_delete.html'
    login_url = '/accounts/login/'
    success_url = reverse_lazy('academic:links_list')

    def get_queryset(self):
        return Link.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Delete Link'
        return context


class FindDuplicatesView(LoginRequiredMixin, View):
    """
    View to find and manage duplicate publications
    """
    login_url = '/accounts/login/'
    template_name = 'academic/find_duplicates.html'

    def get(self, request, *args, **kwargs):
        """Display duplicate publications"""
        duplicates = Publication.find_duplicate_titles(request.user)
        context = {
            'duplicates': duplicates,
            'title': 'Find Duplicate Publications'
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handle actions on duplicate publications"""
        action = request.POST.get('action')
        publication_id = request.POST.get('publication_id')

        if not action or not publication_id:
            messages.error(request, 'Invalid request parameters.')
            return redirect('academic:find_duplicates')

        try:
            # Ensure user can only modify their own publications
            publication = Publication.objects.get(
                id=publication_id,
                owner=request.user
            )

            if action == 'ignore':
                publication.is_ignored = True
                publication.save()
                messages.success(request, f'Publication "{publication.title}" marked as ignored.')

            elif action == 'delete':
                title = publication.title
                publication.delete()
                messages.success(request, f'Publication "{title}" deleted.')

            else:
                messages.error(request, 'Invalid action.')

        except Publication.DoesNotExist:
            messages.error(request, 'Publication not found or access denied.')
        except Exception as e:
            messages.error(request, f'Error processing request: {str(e)}')

        return redirect('academic:find_duplicates')

