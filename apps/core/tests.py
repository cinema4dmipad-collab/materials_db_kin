from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    OBJECT_TYPE_SEARCH_SCOPE,
    SCAN_METHOD_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    QuerySetFilterMixin,
    build_choice_label_filter,
)
from apps.core.templatetags.ui_tags import category_tone, semantic_tone, ui_category_tone, ui_tone
from apps.core.models import Tag
from apps.core.forms import TagForm
from apps.core.number_utils import (
    canonical_number_string,
    format_decimal_display,
    normalize_decimal_input,
    parse_decimal,
)
from apps.core.tag_utils import assign_tags, get_or_create_tags, parse_tag_input, tag_slug_from_name
from apps.materials.models import Material
from apps.samples.models import Sample
from apps.structures.models import StructureType


class _SampleFilterView(QuerySetFilterMixin):
    enable_tag_filter = True
    search_fields = ('code', 'name')
    search_scopes = (
        (ALL_SEARCH_SCOPE, 'Везде', ('code', 'name')),
        ('code', 'Код', ('code',)),
        ('name', 'Название', ('name',)),
        (TAG_SEARCH_SCOPE, 'Тег', ()),
    )
    choice_filters = (('object_type', 'object_type'),)
    choice_filter_labels = {'object_type': 'Тип объекта'}

    def __init__(self, request):
        self.request = request

    def get_choice_filter_options(self):
        return {'object_type': Sample.OBJECT_TYPES}


class TagFormTests(TestCase):
    def test_generates_slug_from_name(self):
        form = TagForm(data={'name': 'T700 test'})
        self.assertTrue(form.is_valid(), form.errors)
        tag = form.save()
        self.assertEqual(tag.slug, 't700-test')

    def test_rejects_duplicate_slug(self):
        Tag.objects.create(name='Prepreg', slug='prepreg')
        form = TagForm(data={'name': 'PREPREG'})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


class TagViewsTests(TestCase):
    def setUp(self):
        self.tag = Tag.objects.create(name='Prepreg', slug='prepreg')

    def test_tag_list_renders(self):
        response = self.client.get(reverse('core:tag_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Prepreg')
        self.assertContains(response, 'prepreg')

    def test_tag_create_view(self):
        response = self.client.post(reverse('core:tag_create'), {'name': 'T700'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Tag.objects.filter(slug='t700').exists())

    def test_tag_update_view(self):
        response = self.client.post(
            reverse('core:tag_edit', kwargs={'pk': self.tag.pk}),
            {'name': 'Pre-preg'},
        )
        self.assertEqual(response.status_code, 302)
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, 'Pre-preg')
        self.assertEqual(self.tag.slug, 'pre-preg')

    def test_tag_delete_view(self):
        response = self.client.post(reverse('core:tag_delete', kwargs={'pk': self.tag.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())


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


class NumberUtilsTests(TestCase):
    def test_normalize_decimal_input_accepts_comma(self):
        self.assertEqual(normalize_decimal_input('12,34'), '12.34')

    def test_parse_decimal_from_comma_string(self):
        self.assertEqual(parse_decimal('1,55'), parse_decimal('1.55'))

    def test_format_decimal_display_uses_comma(self):
        self.assertEqual(format_decimal_display('12.50', 2), '12,50')

    def test_canonical_number_string_stores_with_dot(self):
        self.assertEqual(canonical_number_string('12,50'), '12.5')


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


class _SampleFilterViewWithObjectType(_SampleFilterView):
    search_scopes = _SampleFilterView.search_scopes + (
        (OBJECT_TYPE_SEARCH_SCOPE, 'Тип объекта', ()),
    )

    def get_custom_search_scope_filters(self):
        return {
            OBJECT_TYPE_SEARCH_SCOPE: build_choice_label_filter(
                Sample.OBJECT_TYPES,
                'object_type',
            ),
        }


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

    def test_filters_samples_by_multiple_tags(self):
        assign_tags(self.sample_a, ['lab', 'field'])
        request = RequestFactory().get('/samples/', [('tag', 'lab'), ('tag', 'field')])
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

        request = RequestFactory().get('/samples/', [('tag', 'lab'), ('tag', 'missing-tag')])
        view = _SampleFilterView(request)
        self.assertEqual(view.filter_queryset(Sample.objects.all()).count(), 0)

    def test_search_includes_tag_names(self):
        request = RequestFactory().get('/samples/', {'q': 'field'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-B')

    def test_search_scope_limits_fields(self):
        request = RequestFactory().get('/samples/', {'q': 'Alpha', 'q_in': 'code'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())
        self.assertEqual(queryset.count(), 0)

        request = RequestFactory().get('/samples/', {'q': 'SMP-FILTER-A', 'q_in': 'code'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())
        self.assertEqual(queryset.count(), 1)

    def test_multiple_search_scopes_combine_with_or(self):
        request = RequestFactory().get(
            '/samples/',
            [('q', 'FILTER'), ('q_in', 'code'), ('q_in', 'name')],
        )
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())
        self.assertEqual(queryset.count(), 2)

    def test_search_scope_options_exclude_everywhere(self):
        request = RequestFactory().get('/samples/', {'q_in': 'code'})
        view = _SampleFilterView(request)
        context = view.get_filter_context()
        option_values = [item['value'] for item in context['search_scope_options']]
        self.assertNotIn('', option_values)
        self.assertIn('code', option_values)
        self.assertTrue(context['search_scope_options'][0]['checked'] or any(
            item['checked'] for item in context['search_scope_options'] if item['value'] == 'code'
        ))

    def test_tag_search_scope(self):
        request = RequestFactory().get('/samples/', {'q': 'lab', 'q_in': TAG_SEARCH_SCOPE})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

    def test_object_type_search_scope(self):
        request = RequestFactory().get(
            '/samples/',
            {'q': 'Испытательный', 'q_in': OBJECT_TYPE_SEARCH_SCOPE},
        )
        view = _SampleFilterViewWithObjectType(request)
        queryset = view.filter_queryset(Sample.objects.all())
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

    def test_build_filter_url_removes_selected_params(self):
        request = RequestFactory().get('/samples/', {'q': 'lab', 'q_in': TAG_SEARCH_SCOPE, 'tag': 'lab', 'page': '2'})
        view = _SampleFilterView(request)
        self.assertEqual(view._build_filter_url(remove_tag_slugs=('lab',)), '/samples/?q=lab&q_in=__tag__')
        self.assertEqual(view._build_filter_url(('q', 'q_in')), '/samples/?tag=lab')

    def test_active_tags_context(self):
        request = RequestFactory().get('/samples/', [('tag', 'lab'), ('tag', 'field')])
        view = _SampleFilterView(request)
        context = view.get_filter_context()
        self.assertEqual(len(context['active_tags']), 2)
        self.assertEqual(context['active_tags'][0]['slug'], 'lab')
        self.assertEqual(context['active_tags'][1]['slug'], 'field')
        self.assertEqual(context['active_tags'][0]['remove_url'], '/samples/?tag=field')
        self.assertEqual(context['active_tags'][1]['remove_url'], '/samples/?tag=lab')


class HelpPageTests(TestCase):
    def test_help_page_renders(self):
        response = self.client.get(reverse('core:help'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Справка по работе с базой')
        self.assertContains(response, 'Справочник свойств')
        self.assertContains(response, 'Образцы')


class AppVersionTests(TestCase):
    def test_get_app_version_reads_pyproject(self):
        from apps.core.version import get_app_version

        self.assertEqual(get_app_version(), '0.1.0')

    def test_footer_shows_app_version(self):
        from django.conf import settings

        response = self.client.get(reverse('core:dashboard'))

        self.assertContains(response, f'База композитов v{settings.APP_VERSION}')


class DebugPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username='diagnostics_staff',
            password='test-pass',
            is_staff=True,
        )
        self.regular_user = user_model.objects.create_user(
            username='diagnostics_user',
            password='test-pass',
        )

    def test_debug_page_requires_staff(self):
        response = self.client.get(reverse('core:debug'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('core:debug'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_debug_page_not_linked_in_navigation(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertNotContains(response, 'href="/debug/"')
        self.assertNotContains(response, '>Debug</a>')

        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertNotContains(response, 'href="/debug/"')
        self.assertNotContains(response, '>Debug</a>')

    def test_base_layout_includes_file_transfer_progress_assets(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'file-transfer-progress')
        self.assertContains(response, 'file_transfer_progress.js')
        self.assertContains(response, 'file_transfer_progress.css')

    def test_debug_page_renders_database_and_runtime_info_without_log_file(self):
        with TemporaryDirectory() as temp_dir:
            missing_log = Path(temp_dir) / 'debug.log'
            self.client.force_login(self.staff_user)
            with override_settings(DEBUG_LOG_FILE=missing_log):
                response = self.client.get(reverse('core:debug'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Подключение к БД')
        self.assertContains(response, 'DB engine')
        self.assertContains(response, 'App version')
        self.assertContains(response, 'Storage backend')
        self.assertContains(response, 'Локальный файл логов пока не найден.')

    def test_debug_page_disables_response_caching(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('core:debug'))

        self.assertEqual(response.status_code, 200)
        cache_control = response['Cache-Control']
        self.assertIn('max-age=0', cache_control)
        self.assertIn('no-cache', cache_control)
        self.assertIn('no-store', cache_control)
        self.assertIn('must-revalidate', cache_control)

    def test_debug_page_redacts_sensitive_log_values(self):
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / 'debug.log'
            log_file.write_text(
                (
                    'INFO start\n'
                    'ERROR password=supersecret token:abc123 Bearer eyJsecret\n'
                    'ERROR client_secret=csecretvalue refresh_token=refreshvalue '
                    'AWS_SECRET_ACCESS_KEY=awssecretvalue api-token:apitokenvalue\n'
                ),
                encoding='utf-8',
            )
            self.client.force_login(self.staff_user)
            with override_settings(DEBUG_LOG_FILE=log_file):
                response = self.client.get(reverse('core:debug'))

        self.assertContains(response, 'password=[redacted]')
        self.assertContains(response, 'token:[redacted]')
        self.assertContains(response, 'Bearer [redacted]')
        self.assertContains(response, 'client_secret=[redacted]')
        self.assertContains(response, 'refresh_token=[redacted]')
        self.assertContains(response, 'AWS_SECRET_ACCESS_KEY=[redacted]')
        self.assertContains(response, 'api-token:[redacted]')
        self.assertNotContains(response, 'supersecret')
        self.assertNotContains(response, 'abc123')
        self.assertNotContains(response, 'eyJsecret')
        self.assertNotContains(response, 'csecretvalue')
        self.assertNotContains(response, 'refreshvalue')
        self.assertNotContains(response, 'awssecretvalue')
        self.assertNotContains(response, 'apitokenvalue')

    def test_debug_page_drops_partial_log_line_before_redaction(self):
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / 'debug.log'
            log_file.write_text(
                'ERROR password=supersecret\nINFO visible safe line\n',
                encoding='utf-8',
            )
            self.client.force_login(self.staff_user)
            with override_settings(DEBUG_LOG_FILE=log_file), patch('apps.core.views.RECENT_LOG_BYTES', 32):
                response = self.client.get(reverse('core:debug'))

        self.assertContains(response, 'INFO visible safe line')
        self.assertNotContains(response, 'supersecret')


class UiToneTests(TestCase):
    def test_semantic_tone_uses_known_mapping(self):
        self.assertEqual(ui_tone('test'), 'tone-amber')
        self.assertEqual(ui_tone('echo'), 'tone-blue')

    def test_semantic_tone_unknown_is_neutral(self):
        self.assertEqual(semantic_tone('mat-001'), 'tone-slate')
        self.assertEqual(semantic_tone('carbon_fiber'), 'tone-slate')

    def test_category_tone_is_stable_for_structure_type_code(self):
        self.assertEqual(
            ui_category_tone('composite_panel'),
            ui_category_tone('composite_panel'),
        )

    def test_category_tone_differs_for_different_types(self):
        tones = {category_tone(f'type_{index}') for index in range(12)}
        self.assertGreater(len(tones), 1)
