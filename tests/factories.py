"""
Model factories for generating test data.
"""
import factory
from factory.django import DjangoModelFactory
from django.contrib.auth import get_user_model
from academic.models import Publication, Funding, Teaching, Talk, Conference, ProfessionalActivity

User = get_user_model()


class AcademicUserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'user_{n}')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.Faker('email')
    orcid_id = factory.Faker('bothify', text='0000-0000-0000-####')
    institution = factory.Faker('company')
    department = factory.Faker('job')
    research_areas = factory.LazyFunction(lambda: ['research', 'testing', 'development'])


class PublicationFactory(DjangoModelFactory):
    class Meta:
        model = Publication

    owner = factory.SubFactory(AcademicUserFactory)
    title = factory.Faker('sentence', nb_words=8)
    doi = factory.Sequence(lambda n: f'10.1234/test.{n}')
    year = factory.Faker('year')
    journal = factory.Faker('company')
    volume = factory.Faker('random_int', min=1, max=100)
    page_range = "100-110"

    # JSON fields
    authors = factory.LazyFunction(
        lambda: [
            {
                'name': 'Test Author',
                'orcid': '0000-0000-0000-0001',
                'affiliation': 'Test University'
            },
            {
                'name': 'Second Author',
                'orcid': None,
                'affiliation': None
            }
        ]
    )

    metadata = factory.LazyFunction(
        lambda: {
            'abstract': 'This is a test abstract for testing purposes.',
            'keywords': ['test', 'research', 'science'],
            'source': 'manual',
            'citations': 10
        }
    )

    manual_edits = factory.LazyFunction(lambda: {})
    edit_history = factory.LazyFunction(lambda: [])


class PublicationWithManualEditsFactory(PublicationFactory):
    """Publication factory that includes manual edits."""

    manual_edits = factory.LazyFunction(
        lambda: {
            'title': True,
            'journal': False
        }
    )

    edit_history = factory.LazyFunction(
        lambda: [
            {
                'field': 'title',
                'old_value': 'Original Title',
                'new_value': 'Updated Title',
                'timestamp': '2024-01-01T12:00:00Z',
                'is_manual': True
            }
        ]
    )


class PreprintFactory(PublicationFactory):
    """Factory for preprint publications."""

    is_preprint = True
    journal = factory.Iterator(['bioRxiv', 'arXiv', 'medRxiv', 'PsyArXiv'])
    doi = factory.Sequence(lambda n: f'10.1101/2024.01.{n:02d}.{n:05d}')


class FundingFactory(DjangoModelFactory):
    class Meta:
        model = Funding

    owner = factory.SubFactory(AcademicUserFactory)
    title = factory.Faker('sentence', nb_words=10)
    agency = factory.Faker('company')
    role = factory.Faker('random_element', elements=['PI', 'Co-PI', 'Co-I', 'Subaward PI'])
    amount = factory.Faker('random_int', min=10000, max=5000000)
    start_date = factory.Faker('date_between', start_date='-5y', end_date='today')
    end_date = factory.Faker('date_between', start_date='today', end_date='+5y')


class TeachingFactory(DjangoModelFactory):
    class Meta:
        model = Teaching

    owner = factory.SubFactory(AcademicUserFactory)
    course_name = factory.Faker('sentence', nb_words=4)
    course_number = factory.Faker('bothify', text='CS ###')
    semester = factory.Faker('random_element', elements=['Fall', 'Spring', 'Summer'])
    year = factory.Faker('year')
    role = factory.Faker('random_element', elements=['Instructor', 'Co-Instructor', 'TA'])


class TalkFactory(DjangoModelFactory):
    class Meta:
        model = Talk

    owner = factory.SubFactory(AcademicUserFactory)
    title = factory.Faker('sentence', nb_words=8)
    venue = factory.Faker('company')
    date = factory.Faker('date_between', start_date='-2y', end_date='today')
    talk_type = factory.Faker('random_element', elements=['Keynote', 'Invited', 'Conference', 'Seminar'])


class ConferenceFactory(DjangoModelFactory):
    class Meta:
        model = Conference

    owner = factory.SubFactory(AcademicUserFactory)
    name = factory.Faker('sentence', nb_words=6)
    location = factory.Faker('city')
    date = factory.Faker('date_between', start_date='-1y', end_date='+1y')
    role = factory.Faker('random_element', elements=['Organizer', 'PC Member', 'Reviewer', 'Attendee'])


class ProfessionalActivityFactory(DjangoModelFactory):
    class Meta:
        model = ProfessionalActivity

    owner = factory.SubFactory(AcademicUserFactory)
    title = factory.Faker('sentence', nb_words=6)
    organization = factory.Faker('company')
    role = factory.Faker('job')
    start_date = factory.Faker('date_between', start_date='-3y', end_date='today')
    end_date = factory.Faker('date_between', start_date='today', end_date='+2y')