from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, modify_settings, override_settings
from django.urls import reverse

from apps.core.list_filters import (
    ALL_SEARCH_SCOPE,
    CREATOR_SEARCH_SCOPE,
    CREATOR_WITH_LABEL_FILTER,
    OBJECT_TYPE_SEARCH_SCOPE,
    SCAN_METHOD_SEARCH_SCOPE,
    TAG_SEARCH_SCOPE,
    QuerySetFilterMixin,
    build_choice_label_filter,
)
from apps.core.tag_utils import (
    assign_tags,
    dedupe_scoped_tag_names,
    get_or_create_tags,
    parse_scoped_tag_name,
    parse_tag_input,
    tag_slug_from_name,
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

_COMMIT_ENV_VARS = ('GIT_COMMIT', 'CI_COMMIT_SHORT_SHA', 'CI_COMMIT_SHA')


@contextmanager
def isolated_git_commit(*, build_commit_path=None, **env):
    import os

    from apps.core import version as version_module
    from apps.core.version import get_git_commit_hash

    get_git_commit_hash.cache_clear()
    saved_env = {name: os.environ.pop(name, None) for name in _COMMIT_ENV_VARS}
    original_path = version_module.BUILD_COMMIT_PATH
    if build_commit_path is not None:
        version_module.BUILD_COMMIT_PATH = build_commit_path
    for name, value in env.items():
        os.environ[name] = value
    try:
        yield
    finally:
        version_module.BUILD_COMMIT_PATH = original_path
        for name in _COMMIT_ENV_VARS:
            os.environ.pop(name, None)
        for name, value in saved_env.items():
            if value is not None:
                os.environ[name] = value
        get_git_commit_hash.cache_clear()
from apps.core.creator import assign_creator, creator_label, get_creator_display
from apps.materials.models import Material
from apps.samples.models import Sample
from apps.structures.models import StructureType
from apps.workspaces.services import ensure_legacy_workspace
from apps.workspaces.test_utils import AuthenticatedWorkspaceTestCase, login_test_client


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


class CreatorUtilsTests(TestCase):
    def test_assign_creator_sets_user_and_label(self):
        user = get_user_model().objects.create_user('creator-user', password='pass')
        material = Material(code='M-CR', name='Creator test')
        assign_creator(material, user)
        self.assertEqual(material.created_by_user, user)
        self.assertEqual(material.created_by, 'creator-user')

    def test_get_creator_display_prefers_user(self):
        user = get_user_model().objects.create_user('display-user', password='pass')
        material = Material(code='M-DSP', name='Display test', created_by='legacy', created_by_user=user)
        self.assertEqual(get_creator_display(material), 'display-user')


class TagFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = ensure_legacy_workspace()

    def test_generates_slug_from_name(self):
        form = TagForm(data={'name': 'T700 test'}, workspace=self.workspace)
        self.assertTrue(form.is_valid(), form.errors)
        tag = form.save()
        self.assertEqual(tag.slug, 't700-test')
        self.assertEqual(tag.workspace, self.workspace)

    def test_rejects_duplicate_slug_in_workspace(self):
        Tag.objects.create(name='Prepreg', slug='prepreg', workspace=self.workspace)
        form = TagForm(data={'name': 'PREPREG'}, workspace=self.workspace)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_global_and_workspace_tags_may_share_slug(self):
        Tag.objects.create(name='Prepreg', slug='prepreg', workspace=None)
        form = TagForm(data={'name': 'PREPREG'}, workspace=self.workspace)
        self.assertTrue(form.is_valid(), form.errors)
        tag = form.save()
        self.assertEqual(tag.slug, 'prepreg')
        self.assertEqual(tag.workspace, self.workspace)

    def test_global_tag_requires_unique_slug_globally(self):
        Tag.objects.create(name='Prepreg', slug='prepreg', workspace=None)
        form = TagForm(
            data={'name': 'PREPREG', 'is_global': True},
            workspace=self.workspace,
            allow_global=True,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_tag_form_accepts_metadata(self):
        form = TagForm(
            data={
                'name': 'Pilot',
                'description': 'Test pilot batch',
                'color': '#aabbcc',
                'is_archived': True,
            },
            workspace=self.workspace,
        )
        self.assertTrue(form.is_valid(), form.errors)
        tag = form.save()
        self.assertEqual(tag.description, 'Test pilot batch')
        self.assertEqual(tag.color, '#AABBCC')
        self.assertTrue(tag.is_archived)

    def test_tag_form_rejects_invalid_color(self):
        form = TagForm(data={'name': 'Pilot', 'color': 'red'}, workspace=self.workspace)
        self.assertFalse(form.is_valid())
        self.assertIn('color', form.errors)

    def test_tag_form_accepts_scoped_name(self):
        form = TagForm(data={'name': 'тип::баг'}, workspace=self.workspace)
        self.assertTrue(form.is_valid(), form.errors)
        tag = form.save()
        self.assertEqual(tag.name, 'тип::баг')
        self.assertEqual(tag.slug, 'тип--баг')


class TagViewsTests(AuthenticatedWorkspaceTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = get_user_model().objects.create_superuser('tag-admin', password=cls.password)
        cls.operator = get_user_model().objects.create_user('tag-operator', password=cls.password)
        from apps.workspaces.models import BUILTIN_GROUP_OPERATOR
        from apps.workspaces.services import assign_user_to_groups, ensure_default_groups

        ensure_default_groups(cls.workspace)
        assign_user_to_groups(cls.operator, cls.workspace, [BUILTIN_GROUP_OPERATOR])
        cls.workspace_tag = Tag.objects.create(
            name='Prepreg',
            slug='prepreg',
            workspace=cls.workspace,
        )
        cls.global_tag = Tag.objects.create(
            name='Composite',
            slug='composite',
            workspace=None,
        )

    def test_tag_list_renders_workspace_tags_by_default(self):
        response = self.client.get(reverse('core:tag_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Prepreg')
        self.assertNotContains(response, 'Composite')
        self.assertContains(response, 'Пространство')
        self.assertContains(response, 'Общие')

    def test_tag_list_global_scope_shows_global_tags(self):
        response = self.client.get(reverse('core:tag_list'), {'scope': 'global'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Composite')
        self.assertNotContains(response, 'Prepreg')

    def test_manager_can_create_workspace_tag(self):
        Tag.objects.filter(slug='t700').delete()
        response = self.client.post(reverse('core:tag_create'), {'name': 'T700'})
        self.assertEqual(response.status_code, 302)
        tag = Tag.objects.get(slug='t700', workspace=self.workspace)
        self.assertEqual(tag.workspace, self.workspace)
        self.assertEqual(tag.workspace, self.workspace)

    def test_operator_can_edit_global_tag(self):
        login_test_client(
            self.client,
            user=self.operator,
            workspace=self.workspace,
            password=self.password,
        )
        response = self.client.post(
            reverse('core:tag_edit', kwargs={'pk': self.global_tag.pk}),
            {'name': 'Composite updated', 'is_global': True},
        )
        self.assertEqual(response.status_code, 302)
        self.global_tag.refresh_from_db()
        self.assertEqual(self.global_tag.name, 'Composite updated')

    def test_admin_can_create_global_tag(self):
        login_test_client(
            self.client,
            user=self.admin,
            workspace=self.workspace,
            password=self.password,
        )
        response = self.client.post(
            reverse('core:tag_create'),
            {'name': 'Shared tag', 'is_global': True},
        )
        self.assertEqual(response.status_code, 302)
        tag = Tag.objects.get(slug='shared-tag')
        self.assertIsNone(tag.workspace_id)

    def test_operator_can_create_global_tag(self):
        login_test_client(
            self.client,
            user=self.operator,
            workspace=self.workspace,
            password=self.password,
        )
        response = self.client.post(
            reverse('core:tag_create'),
            {'name': 'Fake global', 'is_global': True},
        )
        self.assertEqual(response.status_code, 302)
        tag = Tag.objects.get(slug='fake-global')
        self.assertIsNone(tag.workspace_id)

    def test_tag_update_view(self):
        response = self.client.post(
            reverse('core:tag_edit', kwargs={'pk': self.workspace_tag.pk}),
            {'name': 'Pre-preg'},
        )
        self.assertEqual(response.status_code, 302)
        self.workspace_tag.refresh_from_db()
        self.assertEqual(self.workspace_tag.name, 'Pre-preg')
        self.assertEqual(self.workspace_tag.slug, 'pre-preg')
        self.assertEqual(self.workspace_tag.workspace, self.workspace)

    def test_tag_delete_view(self):
        response = self.client.post(
            reverse('core:tag_delete', kwargs={'pk': self.workspace_tag.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Tag.objects.filter(pk=self.workspace_tag.pk).exists())

    def test_tag_list_archive_filter(self):
        Tag.objects.create(
            name='Old tag',
            slug='old-tag',
            workspace=self.workspace,
            is_archived=True,
        )
        response = self.client.get(reverse('core:tag_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Old tag')
        response = self.client.get(reverse('core:tag_list'), {'archive': 'archived'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Old tag')
        self.assertNotContains(response, 'Prepreg')


class TagUtilsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = ensure_legacy_workspace()

    def test_parse_tag_input_splits_and_deduplicates(self):
        names = parse_tag_input(' prepreg, T700; prepreg , lab ')
        self.assertEqual(names, ['prepreg', 'T700', 'lab'])

    def test_tag_slug_from_name_normalizes_text(self):
        slug = tag_slug_from_name('T700 test')
        self.assertEqual(slug, 't700-test')

    def test_tag_slug_from_scoped_name(self):
        bug_slug = tag_slug_from_name('тип::баг')
        feature_slug = tag_slug_from_name('тип::фича')
        self.assertEqual(bug_slug, 'тип--баг')
        self.assertNotEqual(bug_slug, feature_slug)

    def test_parse_scoped_tag_name(self):
        scope, value = parse_scoped_tag_name('тип::баг')
        self.assertEqual(scope, 'тип')
        self.assertEqual(value, 'баг')
        scope, value = parse_scoped_tag_name('plain')
        self.assertIsNone(scope)
        self.assertEqual(value, 'plain')

    def test_dedupe_scoped_tag_names_keeps_last_per_scope(self):
        names = dedupe_scoped_tag_names(['тип::баг', 'lab', 'тип::фича', 'field'])
        self.assertEqual(names, ['тип::фича', 'lab', 'field'])

    def test_dedupe_scoped_tag_names_ignores_invalid_scoped(self):
        from apps.core.tag_utils import tag_scope_key

        self.assertIsNone(tag_scope_key('a::b::c'))
        names = dedupe_scoped_tag_names(['a::b::c', 'тип::баг', 'тип::фича'])
        self.assertEqual(names, ['a::b::c', 'тип::фича'])

    def test_split_scoped_tag_display(self):
        from apps.core.tag_utils import split_scoped_tag_display

        self.assertEqual(split_scoped_tag_display('тип::баг'), ('тип', 'баг', 'тип::баг'))
        self.assertEqual(split_scoped_tag_display('plain'), (None, None, 'plain'))

    def test_get_or_create_tags_reuses_existing_slug(self):
        Tag.objects.create(name='Prepreg', slug='prepreg', workspace=self.workspace)
        tags = get_or_create_tags(['prepreg', 'PREPREG'], self.workspace)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].slug, 'prepreg')

    def test_get_or_create_tags_reuses_legacy_scoped_slug_by_name(self):
        """Старый slugify схлопывал «--» в «-»; повторное назначение не должно падать."""
        existing = Tag.objects.create(
            name='Волокно::Стекло',
            slug='волокно-стекло',
            workspace=self.workspace,
        )
        tags = get_or_create_tags(['Волокно::Стекло'], self.workspace)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].pk, existing.pk)
        self.assertEqual(tags[0].slug, 'волокно--стекло')

    def test_get_or_create_tags_reuses_global_tag(self):
        global_tag = Tag.objects.create(
            name='Prepreg',
            slug='prepreg',
            color='#cc0000',
            workspace=None,
        )
        tags = get_or_create_tags(['prepreg'], self.workspace)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0].pk, global_tag.pk)
        self.assertIsNone(tags[0].workspace_id)
        self.assertEqual(tags[0].color, '#cc0000')

    def test_get_or_create_tags_prefers_colored_global_over_colorless_workspace(self):
        global_tag = Tag.objects.create(
            name='Prepreg',
            slug='prepreg',
            color='#cc0000',
            workspace=None,
        )
        Tag.objects.create(
            name='Prepreg',
            slug='prepreg',
            color='',
            workspace=self.workspace,
        )
        tags = get_or_create_tags(['prepreg'], self.workspace)
        self.assertEqual(tags[0].pk, global_tag.pk)

    def test_get_or_create_tags_prefers_workspace_tag_over_global(self):
        Tag.objects.create(name='Prepreg', slug='prepreg', color='#cc0000', workspace=None)
        local = Tag.objects.create(
            name='Prepreg',
            slug='prepreg',
            color='#00cc00',
            workspace=self.workspace,
        )
        tags = get_or_create_tags(['prepreg'], self.workspace)
        self.assertEqual(tags[0].pk, local.pk)

    def test_coalesce_tags_for_display_uses_global_color(self):
        from apps.core.tag_utils import coalesce_tags_for_display

        Tag.objects.create(
            name='Общий',
            slug='obshchiy',
            color='#336699',
            workspace=None,
        )
        local = Tag.objects.create(
            name='Общий',
            slug='obshchiy',
            color='',
            workspace=self.workspace,
        )
        display = coalesce_tags_for_display([local])
        self.assertEqual(len(display), 1)
        self.assertEqual(display[0].color, '#336699')


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
    @classmethod
    def setUpTestData(cls):
        cls.workspace = ensure_legacy_workspace()

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
            home_workspace=self.workspace,
        )

    def test_assign_tags_to_material(self):
        assign_tags(self.material, ['prepreg', 'T700'], workspace=self.workspace)
        self.assertEqual(self.material.tags.count(), 2)
        self.assertTrue(self.material.tags.filter(slug='prepreg').exists())

    def test_assign_tags_dedupes_scoped_tags_by_scope(self):
        assign_tags(self.material, ['тип::баг', 'тип::фича'], workspace=self.workspace)
        self.assertEqual(self.material.tags.count(), 1)
        self.assertEqual(self.material.tags.get().name, 'тип::фича')


class TagNamesFormMixinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = ensure_legacy_workspace()
        Tag.objects.create(name='Active tag', slug='active-tag', workspace=cls.workspace)
        Tag.objects.create(
            name='Archived tag',
            slug='archived-tag',
            workspace=cls.workspace,
            is_archived=True,
        )

    def test_suggestions_exclude_archived_tags(self):
        from apps.materials.forms import MaterialForm

        form = MaterialForm(workspace=self.workspace)
        suggestions = form.fields['tag_names'].widget.get_tag_suggestions()
        slugs = {item['slug'] for item in suggestions}
        self.assertIn('active-tag', slugs)
        self.assertNotIn('archived-tag', slugs)

    def test_suggestions_dedupe_global_and_workspace_same_name(self):
        from apps.materials.forms import MaterialForm

        Tag.objects.create(
            name='общий тег',
            slug='obshchiy-teg-global',
            color='#336699',
            workspace=None,
        )
        Tag.objects.create(
            name='общий тег',
            slug='obshchiy-teg-ws',
            color='',
            workspace=self.workspace,
        )

        form = MaterialForm(workspace=self.workspace)
        suggestions = form.fields['tag_names'].widget.get_tag_suggestions()
        matching = [item for item in suggestions if item['name'].casefold() == 'общий тег']
        self.assertEqual(len(matching), 1)
        # Colored global wins over colorless workspace duplicate.
        self.assertEqual(matching[0]['slug'], 'obshchiy-teg-global')
        self.assertEqual(matching[0]['color'], '#336699')


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


class _SampleFilterViewWithCreator(_SampleFilterView):
    search_scopes = _SampleFilterView.search_scopes + (
        (CREATOR_SEARCH_SCOPE, 'Создал', ()),
    )

    def get_custom_search_scope_filters(self):
        return {
            CREATOR_SEARCH_SCOPE: CREATOR_WITH_LABEL_FILTER,
        }


class QuerySetFilterMixinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = ensure_legacy_workspace()

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
            home_workspace=self.workspace,
        )
        self.sample_a = Sample.objects.create(
            code='SMP-FILTER-A',
            name='Alpha sample',
            material=self.material,
            object_type='test',
            workspace=self.workspace,
        )
        self.sample_b = Sample.objects.create(
            code='SMP-FILTER-B',
            name='Beta sample',
            material=self.material,
            object_type='control',
            workspace=self.workspace,
        )
        assign_tags(self.sample_a, ['lab'], workspace=self.workspace)
        assign_tags(self.sample_b, ['field'], workspace=self.workspace)

    def _request(self, path, params=None):
        request = RequestFactory().get(path, params or {})
        request.active_workspace = self.workspace
        return request

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
        lab_tag = Tag.objects.get(slug='lab', workspace=self.workspace)
        request = self._request('/samples/', {'tag': lab_tag.slug})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

    def test_filters_samples_by_multiple_tags(self):
        assign_tags(self.sample_a, ['lab', 'field'], workspace=self.workspace)
        request = self._request('/samples/', [('tag', 'lab'), ('tag', 'field')])
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

        request = self._request('/samples/', [('tag', 'lab'), ('tag', 'missing-tag')])
        view = _SampleFilterView(request)
        self.assertEqual(view.filter_queryset(Sample.objects.all()).count(), 0)

    def test_search_includes_tag_names(self):
        request = self._request('/samples/', {'q': 'field'})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-B')

    def test_search_and_filter_include_global_tags(self):
        global_tag = Tag.objects.create(
            name='Общие теги::Тест',
            slug='obshchie-tegi--test',
            color='#aa33cc',
            workspace=None,
        )
        assign_tags(self.sample_a, [global_tag.name], workspace=self.workspace)
        self.assertTrue(self.sample_a.tags.filter(pk=global_tag.pk).exists())

        request = self._request('/samples/', {'q': 'Общие', 'q_in': TAG_SEARCH_SCOPE})
        view = _SampleFilterView(request)
        queryset = view.filter_queryset(Sample.objects.all())
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.get().code, 'SMP-FILTER-A')

        request = self._request('/samples/', {'tag': global_tag.slug})
        view = _SampleFilterView(request)
        context = view.get_filter_context()
        self.assertEqual(view.filter_queryset(Sample.objects.all()).count(), 1)
        self.assertEqual(context['active_tags'][0]['label'], global_tag.name)
        self.assertEqual(context['active_tags'][0]['color'], '#aa33cc')
        self.assertEqual(context['active_tags'][0]['tag'].pk, global_tag.pk)

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
        request = self._request('/samples/', {'q': 'lab', 'q_in': TAG_SEARCH_SCOPE})
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

    def test_creator_search_scope(self):
        user = get_user_model().objects.create_user('filter-creator', password='pass')
        assign_creator(self.sample_a, user)
        self.sample_a.save()
        request = RequestFactory().get(
            '/samples/',
            {'q': 'filter-creator', 'q_in': CREATOR_SEARCH_SCOPE},
        )
        view = _SampleFilterViewWithCreator(request)
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
        self.assertContains(response, 'id="interface"')
        self.assertContains(response, 'Пространство')
        self.assertContains(response, 'область::значение')
        self.assertContains(response, 'Общие цветные теги')
        self.assertContains(response, '± погрешностью')
        self.assertContains(response, 'Знаков после запятой')


class AppVersionTests(TestCase):
    def test_get_app_version_reads_pyproject(self):
        import tomllib

        from apps.core.version import PYPROJECT_PATH, get_app_version

        with PYPROJECT_PATH.open('rb') as pyproject_file:
            expected = tomllib.load(pyproject_file)['project']['version']
        self.assertEqual(get_app_version(), expected)

    def test_get_git_commit_hash_reads_env_variable(self):
        import tempfile

        from apps.core.version import get_git_commit_hash

        missing_build_commit = Path(tempfile.gettempdir()) / 'missing-build-commit-for-env-test'
        with isolated_git_commit(
            build_commit_path=missing_build_commit,
            GIT_COMMIT='abc1234',
        ):
            self.assertEqual(get_git_commit_hash(), 'abc1234')

    def test_get_git_commit_hash_prefers_build_commit_over_env(self):
        import tempfile

        from apps.core.version import get_git_commit_hash

        with tempfile.TemporaryDirectory() as temp_dir:
            build_commit = Path(temp_dir) / 'BUILD_COMMIT'
            build_commit.write_text('cafe001', encoding='utf-8')
            with isolated_git_commit(
                build_commit_path=build_commit,
                GIT_COMMIT='deadbeef',
            ):
                self.assertEqual(get_git_commit_hash(), 'cafe001')

    def test_get_git_commit_hash_rejects_unexpanded_shell_command(self):
        import tempfile

        from apps.core.version import format_git_commit_display, get_git_commit_hash

        missing_build_commit = Path(tempfile.gettempdir()) / 'missing-build-commit-for-test'
        with isolated_git_commit(
            build_commit_path=missing_build_commit,
            GIT_COMMIT='$(git rev-parse --short HEAD)',
        ):
            self.assertEqual(get_git_commit_hash(), '')
            self.assertIn('abf8eb9', format_git_commit_display())
            self.assertIn('.env', format_git_commit_display())

    def test_format_version_with_commit_joins_version_and_hash(self):
        from apps.core.version import format_version_with_commit

        self.assertEqual(
            format_version_with_commit('0.1.1', 'deadbeef'),
            '0.1.1 · deadbeef',
        )
        self.assertEqual(format_version_with_commit('0.1.1', ''), '0.1.1')

    def test_get_git_commit_hash_reads_build_commit_file(self):
        import tempfile

        from apps.core.version import get_git_commit_hash

        with tempfile.TemporaryDirectory() as temp_dir:
            build_commit = Path(temp_dir) / 'BUILD_COMMIT'
            build_commit.write_text('abc1234', encoding='utf-8')
            with isolated_git_commit(build_commit_path=build_commit):
                self.assertEqual(get_git_commit_hash(), 'abc1234')

    def test_footer_shows_app_version(self):
        from django.conf import settings

        response = self.client.get(reverse('core:dashboard'))

        self.assertContains(response, f'База композитов v{settings.APP_VERSION}')


class DebugPageTests(TestCase):
    def setUp(self):
        from apps.workspaces.models import BUILTIN_GROUP_OPERATOR
        from apps.workspaces.services import assign_user_to_groups, ensure_default_groups, ensure_legacy_workspace

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
        workspace = ensure_legacy_workspace()
        ensure_default_groups(workspace)
        for user in (self.staff_user, self.regular_user):
            assign_user_to_groups(user, workspace, [BUILTIN_GROUP_OPERATOR])

    @modify_settings(MIDDLEWARE={'remove': 'apps.workspaces.middleware.TestAutoLoginMiddleware'})
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

    def test_admin_index_links_to_debug_for_staff(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('core:debug'))
        self.assertContains(response, '>Debug</a>')

    def test_base_layout_includes_file_transfer_progress_assets(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'file-transfer-progress')
        self.assertContains(response, 'file_transfer_progress.js')
        self.assertContains(response, 'file_transfer_progress.css')

    def test_debug_page_renders_database_and_runtime_info_without_log_file(self):
        from django.conf import settings

        with TemporaryDirectory() as temp_dir:
            missing_log = Path(temp_dir) / 'debug.log'
            self.client.force_login(self.staff_user)
            with override_settings(DEBUG_LOG_FILE=missing_log):
                response = self.client.get(reverse('core:debug'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Подключение к БД')
        self.assertContains(response, 'DB engine')
        self.assertContains(response, 'App version')
        self.assertContains(response, settings.APP_VERSION)
        self.assertContains(response, 'Storage backend')
        self.assertContains(response, 'Локальный файл логов пока не найден.')

    def test_debug_page_shows_commit_hash_next_to_version(self):
        import tempfile

        from apps.core.version import get_git_commit_hash

        self.client.force_login(self.staff_user)
        with tempfile.TemporaryDirectory() as temp_dir:
            build_commit = Path(temp_dir) / 'BUILD_COMMIT'
            build_commit.write_text('cafe001', encoding='utf-8')
            with isolated_git_commit(build_commit_path=build_commit):
                response = self.client.get(reverse('core:debug'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Git commit')
        self.assertContains(response, 'cafe001')
        get_git_commit_hash.cache_clear()

    def test_debug_page_shows_s3_admin_links_when_enabled(self):
        self.client.force_login(self.staff_user)
        with override_settings(
            USE_S3_STORAGE=True,
            AWS_STORAGE_BUCKET_NAME='materials-db',
            DEBUG_S3_ADMIN_BASE_URL='http://localhost',
            SEAWEEDFS_FILER_PORT='8888',
            SEAWEEDFS_MASTER_PORT='9333',
            SEAWEEDFS_ADMIN_PORT='23646',
        ):
            response = self.client.get(reverse('core:debug'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Админка S3')
        self.assertContains(response, 'http://localhost:8888/buckets/materials-db/')
        self.assertContains(response, 'http://localhost:9333/')
        self.assertContains(response, 'http://localhost:23646/')

    def test_debug_page_hides_s3_admin_links_when_disabled(self):
        self.client.force_login(self.staff_user)
        with override_settings(USE_S3_STORAGE=False):
            response = self.client.get(reverse('core:debug'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Админка S3')

    def test_debug_page_renders_scrollable_log_list(self):
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / 'debug.log'
            log_file.write_text('INFO safe line\n', encoding='utf-8')
            self.client.force_login(self.staff_user)
            with override_settings(DEBUG_LOG_FILE=log_file):
                response = self.client.get(reverse('core:debug'))

        self.assertContains(response, 'debug-log-list')
        self.assertContains(response, 'INFO safe line')
        self.assertContains(response, 'debug-page.css')

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
