from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.contrib import messages
from django.urls import reverse_lazy
from django.core.management import call_command
from django.utils import timezone
import logging
from .models import Publication

logger = logging.getLogger(__name__)


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
        user.institution = request.POST.get('institution', '')
        user.department = request.POST.get('department', '')
        user.scopus_id = request.POST.get('scopus_id', '')
        user.pubmed_query = request.POST.get('pubmed_query', '')
        
        # Handle research areas (comma-separated string to list)
        research_areas_str = request.POST.get('research_areas', '')
        if research_areas_str:
            user.research_areas = [area.strip() for area in research_areas_str.split(',') if area.strip()]
        else:
            user.research_areas = []
        
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
        return Publication.objects.filter(owner=self.request.user).order_by('-year', 'title')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'My Publications'
        context['publication_count'] = self.get_queryset().count()
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


class PublicationCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new publication manually
    """
    model = Publication
    template_name = 'academic/publication_form.html'
    fields = ['title', 'year', 'publication_date', 'publication_name', 
              'publication_type', 'doi', 'authors']
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
              'publication_type', 'doi']
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
                if 'Synced' in output and 'publications' in output:
                    messages.success(request, 'ORCID sync completed successfully! Check your publications.')
                elif 'No publications' in output or 'Found 0 publications' in output:
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


class ComprehensiveSyncView(LoginRequiredMixin, View):
    """
    Handle comprehensive synchronization requests - one button to sync everything
    """
    login_url = '/accounts/login/'
    
    def post(self, request):
        """Handle comprehensive sync request"""
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
        
        # Inform user what will be synced
        sync_sources = []
        if has_orcid:
            sync_sources.append('ORCID')
        if has_pubmed:
            sync_sources.append('PubMed')
        if has_scopus:
            sync_sources.append('Scopus')
        
        sources_str = ', '.join(sync_sources)
        messages.info(request, f'Starting comprehensive sync from: {sources_str}')
        
        try:
            # Use call_command to run the comprehensive_sync management command
            from io import StringIO
            import sys
            
            # Capture output
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            
            try:
                # Run comprehensive sync for this user
                call_command('comprehensive_sync', user_id=user.id, verbosity=1)
                output = captured_output.getvalue()
                
                # Parse results from output
                success_indicators = [
                    'All syncs completed successfully',
                    'User sync completed',
                    'Comprehensive sync completed'
                ]
                
                warning_indicators = [
                    'No publications found',
                    'not connected',
                    'No PubMed query',
                    'No Scopus ID'
                ]
                
                error_indicators = [
                    'failed',
                    'error',
                    'Error'
                ]
                
                # Determine result type based on output
                if any(indicator in output for indicator in success_indicators):
                    # Extract stats from output if available
                    import re
                    pub_match = re.search(r'(\d+) new publications', output)
                    enriched_match = re.search(r'Enriched: (\d+)', output)
                    
                    result_msg = 'Comprehensive sync completed successfully!'
                    if pub_match:
                        result_msg += f' Added {pub_match.group(1)} new publications.'
                    if enriched_match:
                        result_msg += f' Enriched {enriched_match.group(1)} publications.'
                    
                    messages.success(request, result_msg)
                    
                elif any(indicator in output for indicator in warning_indicators):
                    messages.warning(request, 'Sync completed with some warnings. Check your profile settings.')
                    
                elif any(indicator in output for indicator in error_indicators):
                    messages.error(request, 'Sync completed with some errors. Some data may not have been updated.')
                    
                else:
                    messages.info(request, 'Comprehensive sync completed.')
                
                # Log detailed output for debugging
                logger.info(f"Comprehensive sync for user {user.id}: {output}")
                
            except Exception as e:
                error_msg = str(e)
                if 'not found' in error_msg:
                    messages.error(request, f'Configuration error: {error_msg}')
                else:
                    messages.error(request, f'Sync failed: {error_msg}')
                logger.error(f"Comprehensive sync error for user {user.id}: {error_msg}")
            finally:
                sys.stdout = old_stdout
        
        except Exception as e:
            messages.error(request, f'Failed to start comprehensive sync: {str(e)}')
            logger.error(f"Failed to start comprehensive sync for user {user.id}: {str(e)}")
        
        # Redirect to publications list to show results
        return redirect('academic:publication_list')


class SyncStatusView(LoginRequiredMixin, View):
    """
    AJAX endpoint to check sync status and provide progress updates
    """
    login_url = '/accounts/login/'
    
    def get(self, request):
        """Return sync status for the current user"""
        user = request.user
        
        # Check last sync times
        sync_status = {
            'orcid_connected': user.is_orcid_connected,
            'pubmed_configured': user.has_pubmed_query,
            'scopus_configured': user.has_scopus_id,
            'last_sync': user.last_orcid_sync.isoformat() if user.last_orcid_sync else None,
            'publication_count': user.publications.count() if hasattr(user, 'publications') else 0,
            'sync_sources': []
        }
        
        # Build list of available sync sources
        if user.is_orcid_connected:
            sync_status['sync_sources'].append('ORCID')
        if user.has_pubmed_query:
            sync_status['sync_sources'].append('PubMed')  
        if user.has_scopus_id:
            sync_status['sync_sources'].append('Scopus')
            
        return JsonResponse(sync_status)


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

