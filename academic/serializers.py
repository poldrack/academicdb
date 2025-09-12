"""
Django REST Framework serializers for academic models
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Publication

User = get_user_model()


class PublicationSerializer(serializers.ModelSerializer):
    """Serializer for Publication model"""
    
    class Meta:
        model = Publication
        fields = [
            'id', 'title', 'year', 'publication_type', 'publication_name',
            'doi', 'authors', 'source', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'source']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make authors required
        self.fields['authors'].required = True
        self.fields['authors'].allow_null = False
    
    def validate_doi(self, value):
        """Validate DOI format and uniqueness for the user"""
        if value and not value.startswith('10.'):
            raise serializers.ValidationError(
                "DOI must start with '10.' (e.g., '10.1234/example')"
            )
        
        # Check for duplicate DOI for the same user
        user = self.context['request'].user
        if value:
            existing = Publication.objects.filter(
                owner=user, doi=value
            ).exclude(id=getattr(self.instance, 'id', None))
            
            if existing.exists():
                raise serializers.ValidationError(
                    "You already have a publication with this DOI"
                )
        
        return value
    
    def validate_year(self, value):
        """Validate publication year"""
        if value < 1900 or value > 2030:
            raise serializers.ValidationError(
                "Year must be between 1900 and 2030"
            )
        return value
    
    def validate_authors(self, value):
        """Validate authors list"""
        if not value:  # Handle None, empty list, or falsy values
            raise serializers.ValidationError(
                "At least one author is required"
            )
        
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Authors must be a list"
            )
        
        if len(value) == 0:
            raise serializers.ValidationError(
                "At least one author is required"
            )
        
        for author in value:
            if not isinstance(author, dict) or 'name' not in author:
                raise serializers.ValidationError(
                    "Each author must be an object with at least a 'name' field"
                )
        
        return value
    
    def create(self, validated_data):
        """Create publication with proper owner and source"""
        validated_data['owner'] = self.context['request'].user
        validated_data['source'] = 'manual'
        return super().create(validated_data)