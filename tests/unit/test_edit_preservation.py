"""
Tests for the edit preservation logic.

This is critical functionality that prevents manual edits from being
overwritten by external API synchronization.
"""
import pytest
from django.utils import timezone
from academic.models import Publication
from tests.factories import AcademicUserFactory, PublicationFactory, PublicationWithManualEditsFactory


@pytest.mark.django_db
class TestEditPreservation:
    """Test that manual edits are preserved during API sync operations."""

    def test_manual_edit_flag_preservation(self):
        """Manual edit flags should be preserved when set."""
        user = AcademicUserFactory()
        pub = PublicationFactory(owner=user)

        # Mark title as manually edited
        pub.manual_edits = {"title": True}
        pub.save()

        pub.refresh_from_db()
        assert pub.manual_edits.get("title") is True

    def test_edit_history_recording(self):
        """Edit history should be recorded when changes are made."""
        user = AcademicUserFactory()
        pub = PublicationFactory(owner=user, title="Original Title")

        # Simulate manual edit with history
        original_title = pub.title
        new_title = "Manually Edited Title"

        pub.title = new_title
        pub.manual_edits = {"title": True}

        # Add to edit history
        edit_entry = {
            "field": "title",
            "old_value": original_title,
            "new_value": new_title,
            "timestamp": timezone.now().isoformat(),
            "is_manual": True,
            "user_id": user.id
        }

        if not pub.edit_history:
            pub.edit_history = []
        pub.edit_history.append(edit_entry)
        pub.save()

        pub.refresh_from_db()
        assert len(pub.edit_history) == 1
        assert pub.edit_history[0]["field"] == "title"
        assert pub.edit_history[0]["is_manual"] is True
        assert pub.edit_history[0]["new_value"] == new_title

    def test_api_sync_preserves_manual_edits(self):
        """Simulate API sync and verify manual edits are preserved."""
        user = AcademicUserFactory()
        pub = PublicationFactory(
            owner=user,
            title="Manual Title",
            publication_name="Manual Journal",
            year=2024
        )

        # Mark title and publication_name as manually edited
        pub.manual_edits = {"title": True, "publication_name": True}
        pub.save()

        # Simulate API sync data (this would come from external APIs)
        api_sync_data = {
            "title": "API Title",  # Should NOT override manual edit
            "publication_name": "API Journal",  # Should NOT override manual edit
            "year": 2023,  # Should update (not manually edited)
            "volume": "42",  # Should add (new field)
        }

        # Simulate the sync process that preserves manual edits
        original_title = pub.title
        original_publication_name = pub.publication_name

        for field, value in api_sync_data.items():
            if not pub.manual_edits.get(field, False):
                setattr(pub, field, value)

        pub.save()
        pub.refresh_from_db()

        # Manual edits should be preserved
        assert pub.title == original_title  # "Manual Title"
        assert pub.publication_name == original_publication_name  # "Manual Journal"

        # Non-manual fields should be updated
        assert pub.year == 2023
        assert pub.volume == "42"

    def test_partial_manual_edits(self):
        """Only specific fields marked as manual should be preserved."""
        user = AcademicUserFactory()
        pub = PublicationFactory(
            owner=user,
            title="Manual Title",
            publication_name="Auto Journal",
            year=2024,
            volume="10"
        )

        # Only mark title as manually edited
        pub.manual_edits = {"title": True}
        pub.save()

        # API sync should preserve title but update everything else
        api_data = {
            "title": "New API Title",
            "publication_name": "New API Journal",
            "year": 2023,
            "volume": "20"
        }

        original_title = pub.title

        # Simulate sync logic
        for field, value in api_data.items():
            if not pub.manual_edits.get(field, False):
                setattr(pub, field, value)

        pub.save()
        pub.refresh_from_db()

        # Only title should be preserved
        assert pub.title == original_title
        assert pub.publication_name == "New API Journal"
        assert pub.year == 2023
        assert pub.volume == "20"

    def test_complex_edit_history(self):
        """Test complex edit history with multiple changes."""
        user = AcademicUserFactory()
        pub = PublicationWithManualEditsFactory(owner=user)

        # Add multiple edit history entries
        pub.edit_history = [
            {
                "field": "title",
                "old_value": "Original Title",
                "new_value": "First Edit",
                "timestamp": "2024-01-01T10:00:00Z",
                "is_manual": False,
                "source": "api_sync"
            },
            {
                "field": "title",
                "old_value": "First Edit",
                "new_value": "Manual Edit",
                "timestamp": "2024-01-02T14:30:00Z",
                "is_manual": True,
                "user_id": user.id
            },
            {
                "field": "publication_name",
                "old_value": "Old Journal",
                "new_value": "New Journal",
                "timestamp": "2024-01-03T09:15:00Z",
                "is_manual": True,
                "user_id": user.id
            }
        ]
        pub.save()

        pub.refresh_from_db()
        assert len(pub.edit_history) == 3

        # Check chronological order and types
        manual_edits = [entry for entry in pub.edit_history if entry["is_manual"]]
        assert len(manual_edits) == 2

        api_edits = [entry for entry in pub.edit_history if not entry["is_manual"]]
        assert len(api_edits) == 1

    def test_metadata_field_preservation(self):
        """Test that manual edits work for nested metadata fields."""
        user = AcademicUserFactory()
        pub = PublicationFactory(owner=user)

        # Set initial metadata
        pub.metadata = {
            "abstract": "Manual abstract",
            "keywords": ["manual", "keywords"],
            "citations": 10
        }
        pub.manual_edits = {"metadata.abstract": True, "metadata.keywords": True}
        pub.save()

        # Simulate API sync with new metadata
        api_metadata = {
            "abstract": "API abstract",  # Should be preserved
            "keywords": ["api", "keywords"],  # Should be preserved
            "citations": 15,  # Should be updated
            "pubmed_id": "12345"  # Should be added
        }

        # Preserve manually edited metadata fields
        current_metadata = pub.metadata.copy()
        for field, value in api_metadata.items():
            if not pub.manual_edits.get(f"metadata.{field}", False):
                current_metadata[field] = value

        pub.metadata = current_metadata
        pub.save()
        pub.refresh_from_db()

        # Manual fields should be preserved
        assert pub.metadata["abstract"] == "Manual abstract"
        assert pub.metadata["keywords"] == ["manual", "keywords"]

        # Non-manual fields should be updated
        assert pub.metadata["citations"] == 15
        assert pub.metadata["pubmed_id"] == "12345"

    def test_author_list_preservation(self):
        """Test that manually edited author lists are preserved."""
        user = AcademicUserFactory()
        pub = PublicationFactory(owner=user)

        # Set manual author list
        manual_authors = [
            {"name": "Manual Author 1", "orcid": "0000-0000-0000-0001"},
            {"name": "Manual Author 2", "orcid": None}
        ]
        pub.authors = manual_authors
        pub.manual_edits = {"authors": True}
        pub.save()

        # API provides different authors
        api_authors = [
            {"name": "API Author 1", "orcid": "0000-0000-0000-0002"},
            {"name": "API Author 2", "orcid": "0000-0000-0000-0003"},
            {"name": "API Author 3", "orcid": None}
        ]

        # Should preserve manual author list
        if not pub.manual_edits.get("authors", False):
            pub.authors = api_authors

        pub.save()
        pub.refresh_from_db()

        # Should still have manual authors
        assert pub.authors == manual_authors
        assert len(pub.authors) == 2

    def test_clear_manual_edit_flag(self):
        """Test ability to clear manual edit flags when needed."""
        user = AcademicUserFactory()
        pub = PublicationWithManualEditsFactory(owner=user)

        # Verify manual edit is set
        assert pub.manual_edits.get("title") is True

        # Clear the manual edit flag
        pub.manual_edits["title"] = False
        pub.save()

        # Now API sync should be able to update the title
        api_title = "New API Title"
        if not pub.manual_edits.get("title", False):
            pub.title = api_title

        pub.save()
        pub.refresh_from_db()

        assert pub.title == api_title

    def test_edit_preservation_edge_cases(self):
        """Test edge cases in edit preservation logic."""
        user = AcademicUserFactory()
        pub = PublicationFactory(owner=user)

        # Test with empty manual_edits
        pub.manual_edits = {}
        api_data = {"title": "API Title"}

        for field, value in api_data.items():
            if not pub.manual_edits.get(field, False):
                setattr(pub, field, value)

        pub.save()
        assert pub.title == "API Title"

        # Test with empty dict manual_edits (the model default)
        pub.manual_edits = {}
        pub.save()

        # Should handle empty dict gracefully
        for field, value in api_data.items():
            manual_edits = pub.manual_edits or {}
            if not manual_edits.get(field, False):
                setattr(pub, field, value)

        pub.save()
        # Should still work without errors