from django.test import RequestFactory, TestCase

from apps.core.list_filters import QuerySetFilterMixin
from apps.core.models import Tag
from apps.core.tag_utils import assign_tags, get_or_create_tags, parse_tag_input, tag_slug_from_name
from apps.materials.models import Material
from apps.samples.models import Sample
from apps.structures.models import StructureType


class _SampleFilterView(QuerySetFilterMixin):
    enable_tag_filter = True
    search_fields = ('code', 'name')
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта', 'tag': 'Тег'}

    def __init__(self, request):
        self.request = request

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}


class TagUtilsTests(TestCase):
    def test_parse_tag_input_splits_and_deduplicates(self):
        names = parse_tag_input(' prepreg, T700; prepreg , lab ')
        self.assertEqual(names, ['prepreg', 'T700', 'lab'])

    def test_tag_slug_from_name_normalizes_text(self):
        slug = tag_slug_from_name('T700 test')
        self.assertEqual(slug, 't700-test')

    def test_get_or_create_tags_reuses_existing_slug(self):
        Tag.objects.create(name='Prepreg', slug='prepreg')
        tags = get_or_create_tags(['prepreg', 'PREPREG'])
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].slug, 'prepreg')


class TagAssignmentTests(TestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Composite',
            code='composite_tags_test',
            allow_layers=True,
        )
        self.material = Material.objects.create(
            code='MAT-TAG-001',
            name='Tagged material',
            struct_type=self.structure_type,
        )

    def test_assign_tags_to_material(self):
        assign_tags(self.material, ['prepreg', 'T700'])
        self.assertEqual(self.material.tags.count(), 2)
        self.assertTrue(self.material.tags.filter(slug='prepreg').exists())


class QuerySetFilterMixinTests(TestCase):
    def setUp(self):
        self.structure_type = StructureType.objects.create(
            name='Composite',
            code='composite_filter_test',
            allow_layers=True,
        )
        self.material = Material.objects.create(
            code='MAT-FILTER-001',
            name='Filter material',
            struct_type=self.structure_type,
        )
        self.sample_a = Sample.objects.create(
            code='SMP-FILTER-A',
            name='Alpha sample',
            material=self.material,
            object_type='test',
        )
        self.sample_b = Sample.objects.create(
            code='SMP-FILTER-B',
            name='Beta sample',
            material=self.material,
            object_type='control',
        )
        assign_tags(self.sample_a, ['lab'])
        assign_tags(self.sample_b, ['field'])

    def test_filters_samples_by_search_query(self):
        request = RequestFactory().get('/samples/', {'q': 'Alpha'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

    def test_filters_samples_by_choice(self):
        request = RequestFactory().get('/samples/', {'object_type': 'control'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-B')

    def test_filters_samples_by_tag_slug(self):
        lab_tag = Tag.objects.get(slug='lab')
        request = RequestFactory().get('/samples/', {'tag': lab_tag.slug})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

    def test_search_includes_tag_names(self):
        request = RequestFactory().get('/samples/', {'q': 'field'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-B')
