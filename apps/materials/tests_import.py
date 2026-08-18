import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.core.tag_utils import assign_tags
from apps.materials.imports.debug_undo import (
    get_last_import_debug_batch,
    store_last_import_debug_batch,
    undo_last_import_debug_batch,
)
from apps.materials.models import Material, MaterialImportProfile, MaterialProperty
from apps.materials.imports.mapping import (
    TARGET_CODE,
    TARGET_NAME,
    TARGET_PROPERTY_PREFIX,
    TARGET_SKIP,
    TARGET_STRUCTURE_PREFIX,
    TARGET_TAGS,
    TARGET_DESCRIPTION,
    apply_profile_to_columns,
    build_field_mapping_rows,
    find_duplicate_mapping_targets,
    import_templates_for_workspace,
    mapping_catalog_groups,
    mapping_choices,
    missing_required_targets,
    primary_import_targets,
    profile_payload_from_mapping,
    required_import_targets,
    suggest_target,
    unused_columns_from_mapping,
)
from apps.materials.imports.structure_values import merge_structure_sql_payloads
from apps.materials.imports.iterate import (
    apply_iterate_row_post,
    iterate_progress,
    next_active_index,
    start_iterate,
)
from apps.materials.imports.readers import read_csv, read_import_file
from apps.materials.imports.service import MaterialImporter
from apps.materials.imports.staging import (
    MATCH_ALWAYS_CREATE,
    MATCH_BY_CODE,
    MATCH_BY_NAME,
    DraftMaterial,
    DraftProperty,
    DraftStructureValue,
    RECOGNITION_IGNORED,
    RECOGNITION_MANUAL,
    RECOGNITION_OK,
    RECOGNITION_UNRECOGNIZED,
    apply_duplicate_name_policy,
    apply_review_post,
    apply_unrecognized_ignore_all,
    apply_unrecognized_manual_fixes,
    build_review_fix_grid,
    build_staging_draft,
    draft_to_import_rows,
    drafts_from_session,
    drafts_to_session,
    has_unresolved_unrecognized,
    iter_unrecognized_fields,
    merge_default_tags_into_drafts,
    name_collisions_for_drafts,
)
from apps.materials.imports.upload import get_import_config, set_import_config
from apps.materials.imports.value_parse import needs_manual_recognition, parse_property_cell
from apps.materials.imports.wide import (
    WideColumn,
    WideTable,
    build_import_layout_schema,
    detect_header_layout,
    load_wide_table,
)
from apps.references.models import Property, PropertyGroup
from apps.structures.models import StructureField, StructureType
from apps.structures.sql_executor import SQLExecutor
from apps.structures.table_storage import get_row
from apps.workspaces.services import ensure_legacy_workspace


def create_import_structure_type(*, code='import_fabric', table_name='structures_import_fabric'):
    structure_type = StructureType.objects.create(
        name='Import fabric',
        code=code,
        table_name=table_name,
    )
    density_field = StructureField.objects.create(
        structure_type=structure_type,
        name='areal_density',
        label='Плотность пов',
        field_type='DecimalField',
        max_digits=12,
        decimal_places=4,
        sort_order=1,
    )
    StructureField.objects.create(
        structure_type=structure_type,
        name='weave_type',
        label='Тип плетения',
        field_type='CharField',
        max_length=100,
        sort_order=2,
    )
    result = SQLExecutor.create_table(structure_type)
    if not result['success']:
        raise RuntimeError(result.get('error'))
    structure_type.refresh_from_db()
    return structure_type, density_field


class MaterialImportReaderTests(TestCase):
    def test_read_csv_normalizes_headers(self):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as handle:
            handle.write('material_code,material_name,property,value\n')
            handle.write('MAT-R,Reader test,density,1.2\n')
            path = Path(handle.name)
        try:
            rows = read_csv(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['code'], 'MAT-R')
        self.assertEqual(rows[0]['property_name'], 'density')

    def test_read_import_file_rejects_unknown_extension(self):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as handle:
            path = Path(handle.name)
        try:
            with self.assertRaises(ValueError):
                read_import_file(path)
        finally:
            path.unlink(missing_ok=True)


class MaterialImportServiceTests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        group = PropertyGroup.objects.create(name='Import test group', sort_order=1)
        self.density = Property.objects.create(
            name='density',
            display_name='Density',
            unit='g/cm3',
            data_type='number',
            group=group,
        )
        Property.objects.create(
            name='tensile_strength',
            display_name='Tensile strength',
            unit='MPa',
            data_type='number',
            group=group,
        )

    def _sample_csv(self) -> Path:
        return Path(__file__).resolve().parent / 'fixtures' / 'import_examples' / 'materials_sample.csv'

    def test_dry_run_reports_planned_counts(self):
        report = MaterialImporter(workspace=self.workspace, dry_run=True).import_file(self._sample_csv())
        self.assertTrue(report.ok)
        self.assertEqual(report.materials_created, 2)
        self.assertFalse(Material.objects.filter(code='IMP-MAT-001').exists())

    def test_apply_creates_materials_properties_and_merges_tags(self):
        existing = Material.objects.create(
            code='IMP-MAT-001',
            name='Existing',
            home_workspace=self.workspace,
        )
        assign_tags(existing, ['источник::legacy'], workspace=self.workspace)
        report = MaterialImporter(workspace=self.workspace).import_file(self._sample_csv())
        self.assertTrue(report.ok)
        material = Material.objects.get(code='IMP-MAT-001', home_workspace=self.workspace)
        self.assertEqual(material.name, 'Import demo laminate')
        tag_names = set(material.tags.values_list('name', flat=True))
        self.assertIn('источник::legacy', tag_names)
        self.assertIn('lab', tag_names)

    def test_created_materials_get_import_source_filename(self):
        report = MaterialImporter(
            workspace=self.workspace,
            source_filename='Сводная по материалам.xlsx',
        ).import_file(self._sample_csv())
        self.assertTrue(report.ok)
        sourced = Material.objects.filter(
            home_workspace=self.workspace,
            import_source_filename='Сводная по материалам.xlsx',
        )
        self.assertEqual(sourced.count(), report.materials_created)
        material = sourced.first()
        self.assertNotIn('Создано из файла импорта', material.description or '')
        self.assertNotIn('Создано из файла импорта', material.description_display)
        self.assertIn(
            'статус::на проверке',
            set(material.tags.values_list('name', flat=True)),
        )
        status_tag = material.tags.get(name='статус::на проверке')
        self.assertEqual((status_tag.color or '').upper(), '#E6A700')

    def test_update_does_not_force_approved_status_tag(self):
        from apps.materials.imports.review_status import (
            IMPORT_STATUS_APPROVED,
            IMPORT_STATUS_VERIFIED,
            set_material_import_status,
        )

        MaterialImporter(workspace=self.workspace).import_file(self._sample_csv())
        material = Material.objects.get(code='IMP-MAT-002', home_workspace=self.workspace)
        set_material_import_status(material, workspace=self.workspace, column='verified')
        self.assertIn(
            IMPORT_STATUS_VERIFIED,
            set(material.tags.values_list('name', flat=True)),
        )
        MaterialImporter(workspace=self.workspace).import_file(self._sample_csv())
        material.refresh_from_db()
        names = set(material.tags.values_list('name', flat=True))
        self.assertIn(IMPORT_STATUS_VERIFIED, names)
        self.assertNotIn(IMPORT_STATUS_APPROVED, names)

    def test_reimport_updates_import_source_filename(self):
        first = MaterialImporter(
            workspace=self.workspace,
            source_filename='old.xlsx',
        ).import_file(self._sample_csv())
        self.assertTrue(first.ok)
        second = MaterialImporter(
            workspace=self.workspace,
            source_filename='Сводная по материалам.xlsx',
        ).import_file(self._sample_csv())
        self.assertTrue(second.ok)
        self.assertEqual(second.materials_created, 0)
        self.assertGreater(second.materials_updated, 0)
        self.assertFalse(
            Material.objects.filter(
                home_workspace=self.workspace,
                import_source_filename='old.xlsx',
            ).exists()
        )
        self.assertEqual(
            Material.objects.filter(
                home_workspace=self.workspace,
                import_source_filename='Сводная по материалам.xlsx',
            ).count(),
            Material.objects.filter(home_workspace=self.workspace).count(),
        )

    def test_reimport_is_idempotent(self):
        importer = MaterialImporter(workspace=self.workspace)
        first = importer.import_file(self._sample_csv())
        second = importer.import_file(self._sample_csv())
        self.assertTrue(first.ok and second.ok)
        self.assertEqual(second.materials_created, 0)
        self.assertEqual(Material.objects.filter(home_workspace=self.workspace).count(), 2)

    def test_unknown_property_fails_validation(self):
        csv_text = 'code,name,property_name,value\nMAT-X,Test,unknown_prop,1\n'
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as handle:
            handle.write(csv_text)
            path = Path(handle.name)
        try:
            report = MaterialImporter(workspace=self.workspace).import_file(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertFalse(report.ok)

    def test_home_workspace_mismatch_is_rejected(self):
        csv_text = 'code,name,home_workspace\nMAT-X,Test,other-ws\n'
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as handle:
            handle.write(csv_text)
            path = Path(handle.name)
        try:
            report = MaterialImporter(workspace=self.workspace).import_file(path)
        finally:
            path.unlink(missing_ok=True)
        self.assertFalse(report.ok)


class MaterialImportMappingUnitTests(TestCase):
    def setUp(self):
        self.workspace = ensure_legacy_workspace()
        group = PropertyGroup.objects.create(name='Wide map group', sort_order=1)
        self.density = Property.objects.create(
            name='areal_density',
            display_name='Плотность пов',
            data_type='number',
            group=group,
        )
        self.wide = (
            Path(__file__).resolve().parent
            / 'fixtures'
            / 'import_examples'
            / 'materials_wide_sample.csv'
        )

    def test_required_import_targets_depend_on_match_policy(self):
        by_name = {target for target, _ in required_import_targets('name')}
        by_code = {target for target, _ in required_import_targets('code')}
        self.assertEqual(by_name, {TARGET_NAME})
        self.assertEqual(by_code, {TARGET_NAME, TARGET_CODE})
        missing = missing_required_targets(
            [{'target': TARGET_SKIP}, {'target': TARGET_CODE}],
            match_policy='code',
        )
        self.assertEqual([target for target, _ in missing], [TARGET_NAME])
        missing_field = missing_required_targets(
            [
                {
                    'is_field_row': True,
                    'target': TARGET_NAME,
                    'column': None,
                    'column_index': None,
                },
                {
                    'is_field_row': True,
                    'target': TARGET_CODE,
                    'column_index': 1,
                },
            ],
            match_policy='code',
        )
        self.assertEqual([target for target, _ in missing_field], [TARGET_NAME])

    def test_primary_import_targets_include_structure_not_properties(self):
        structure_type, density_field = create_import_structure_type(
            code='primary_targets_fabric',
            table_name='structures_primary_targets_fabric',
        )
        self.addCleanup(SQLExecutor.drop_table, structure_type)
        by_name = primary_import_targets([density_field], match_policy='name')
        targets = [target for target, _ in by_name]
        self.assertEqual(targets[0], TARGET_NAME)
        self.assertIn(f'{TARGET_STRUCTURE_PREFIX}{density_field.name}', targets)
        self.assertNotIn(TARGET_CODE, targets)
        by_code = primary_import_targets([density_field], match_policy='code')
        code_targets = [target for target, _ in by_code]
        self.assertEqual(code_targets[0], TARGET_CODE)
        self.assertIn(TARGET_NAME, code_targets)

    def test_suggest_target_does_not_auto_map_marka_or_properties(self):
        from apps.materials.imports.wide import WideColumn

        marka = WideColumn(index=1, label='Марка', group='')
        self.assertEqual(suggest_target(marka, [self.density], []), TARGET_SKIP)
        prop_col = WideColumn(index=2, label='Плотность пов', group='')
        self.assertEqual(
            suggest_target(prop_col, [self.density], []),
            TARGET_SKIP,
        )
        self.assertNotEqual(
            suggest_target(prop_col, [self.density], []),
            f'{TARGET_PROPERTY_PREFIX}{self.density.pk}',
        )

    def test_build_field_mapping_rows_and_unused(self):
        from apps.materials.imports.wide import WideColumn

        structure_type, density_field = create_import_structure_type(
            code='field_rows_fabric',
            table_name='structures_field_rows_fabric',
        )
        self.addCleanup(SQLExecutor.drop_table, structure_type)
        columns = [
            WideColumn(index=0, label='Наименование', group=''),
            WideColumn(index=1, label='Марка', group=''),
            WideColumn(index=2, label='Плотность пов', group=''),
        ]
        mapping = {
            '0': {'target': TARGET_NAME, 'parse': 'auto'},
            '1': {'target': TARGET_SKIP, 'parse': 'auto'},
            '2': {
                'target': f'{TARGET_STRUCTURE_PREFIX}{density_field.name}',
                'parse': 'auto',
            },
        }
        rows = build_field_mapping_rows(
            columns=columns,
            mapping=mapping,
            structure_fields=[density_field],
            match_policy='name',
            sample_row={0: 'Т-23', 1: 'E-glass', 2: '300'},
        )
        targets = [row['target'] for row in rows]
        self.assertEqual(targets[0], TARGET_NAME)
        self.assertIn(f'{TARGET_STRUCTURE_PREFIX}{density_field.name}', targets)
        self.assertNotIn(TARGET_TAGS, targets)
        name_row = next(row for row in rows if row['target'] == TARGET_NAME)
        self.assertEqual(name_row['column_index'], 0)
        self.assertEqual(name_row['sample'], 'Т-23')
        self.assertTrue(name_row['is_primary'])
        self.assertFalse(name_row['is_material'])
        self.assertFalse(name_row['is_property'])
        unused = unused_columns_from_mapping(columns, mapping, sample_row={1: 'E-glass'})
        self.assertEqual([col['index'] for col in unused], [1])
        self.assertEqual(unused[0]['sample'], 'E-glass')

        mapping_with_tags = dict(mapping)
        mapping_with_tags['1'] = {'target': TARGET_TAGS, 'parse': 'auto'}
        rows_tags = build_field_mapping_rows(
            columns=columns,
            mapping=mapping_with_tags,
            structure_fields=[density_field],
            match_policy='name',
            sample_row={0: 'Т-23', 1: 'E-glass', 2: '300'},
        )
        tags_row = next(row for row in rows_tags if row.get('is_tag'))
        self.assertTrue(tags_row['is_tag'])
        self.assertEqual(tags_row['section'], 'tag')
        self.assertFalse(tags_row['is_material'])
        self.assertFalse(tags_row['is_property'])
        self.assertTrue(tags_row['is_addon'])
        self.assertEqual(tags_row['mapping_target'], TARGET_TAGS)
        self.assertIn('::', tags_row['tag_preview'])

        mapping_with_field_and_tag = dict(mapping_with_tags)
        mapping_with_field_and_tag['1'] = {
            'target': f'{TARGET_STRUCTURE_PREFIX}{density_field.name}',
            'parse': 'auto',
        }
        rows_dual = build_field_mapping_rows(
            columns=columns,
            mapping=mapping_with_field_and_tag,
            structure_fields=[density_field],
            match_policy='name',
            sample_row={0: 'Т-23', 1: 'E-glass', 2: '300'},
            tag_columns=['1'],
        )
        tag_rows = [row for row in rows_dual if row.get('is_tag')]
        self.assertEqual(len(tag_rows), 1)
        self.assertEqual(tag_rows[0]['column_index'], 1)
        structure_rows = [
            row for row in rows_dual
            if row['target'] == f'{TARGET_STRUCTURE_PREFIX}{density_field.name}'
        ]
        self.assertEqual(len(structure_rows), 1)
        self.assertEqual(structure_rows[0]['column_index'], 1)

    def test_bound_column_is_used_and_shown_on_numeric_rows(self):
        from apps.materials.imports.wide import WideColumn

        columns = [
            WideColumn(index=0, label='Наименование', group=''),
            WideColumn(index=1, label='Плотность пов', group=''),
            WideColumn(index=2, label='Погрешность', group=''),
        ]
        mapping = {
            '0': {'target': TARGET_NAME, 'parse': 'auto'},
            '1': {
                'target': f'{TARGET_PROPERTY_PREFIX}{self.density.pk}',
                'parse': 'auto',
                'bound_column': 2,
                'bound_kind': 'range',
            },
            '2': {'target': TARGET_SKIP, 'parse': 'auto'},
        }
        rows = build_field_mapping_rows(
            columns=columns,
            mapping=mapping,
            extra_properties=[self.density],
            properties=[self.density],
            match_policy='name',
            sample_row={0: 'Т-23', 1: '300', 2: '320'},
        )
        name_row = next(row for row in rows if row['target'] == TARGET_NAME)
        self.assertFalse(name_row['accepts_bound'])
        prop_row = next(
            row for row in rows if row['target'] == f'{TARGET_PROPERTY_PREFIX}{self.density.pk}'
        )
        self.assertTrue(prop_row['accepts_bound'])
        self.assertEqual(prop_row['column_index'], 1)
        self.assertEqual(prop_row['bound_column_index'], 2)
        self.assertEqual(prop_row['bound_kind'], 'range')
        unused = unused_columns_from_mapping(columns, mapping)
        self.assertEqual([col['index'] for col in unused], [])

    def test_build_staging_draft_tag_column_alongside_field_mapping(self):
        from apps.materials.imports.wide import WideColumn

        columns = [
            WideColumn(index=0, label='Наименование', group=''),
            WideColumn(index=1, label='Марка', group=''),
        ]
        table = WideTable(
            sheet_name='test',
            header_row=1,
            columns=columns,
            rows=[{0: 'Ткань A', 1: 'E-glass'}],
            preview_rows=[{0: 'Ткань A', 1: 'E-glass'}],
        )
        mapping = {
            '0': {'target': TARGET_NAME, 'parse': 'auto'},
            '1': {'target': TARGET_DESCRIPTION, 'parse': 'auto'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            tag_columns=['1'],
        )
        self.assertEqual(len(drafts), 1)
        self.assertIn('марка::E-glass', drafts[0].tags)
        self.assertIn('E-glass', drafts[0].description)

    def test_find_duplicate_mapping_targets(self):
        target = f'{TARGET_STRUCTURE_PREFIX}breaking_load'
        dups = find_duplicate_mapping_targets(
            [
                {'target': TARGET_NAME, 'column_label': 'Наименование'},
                {'target': target, 'column_label': 'Разрывная основа'},
                {'target': target, 'column_label': 'Разрывная уток'},
                {'target': TARGET_SKIP, 'column_label': 'X'},
            ]
        )
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]['target'], target)
        self.assertEqual(dups[0]['columns'], ['Разрывная основа', 'Разрывная уток'])

    def test_mapping_catalog_groups(self):
        structure_type = StructureType.objects.create(
            name='Catalog map fabric',
            code='catalog_map_fabric',
            table_name='structures_catalog_map_fabric',
        )
        density_field = StructureField.objects.create(
            structure_type=structure_type,
            name='areal_density',
            label='Плотность пов',
            field_type='DecimalField',
            sort_order=1,
        )
        choices = mapping_choices(
            structure_fields=[density_field],
            properties=[self.density],
        )
        groups = mapping_catalog_groups(choices)
        group_ids = [group['id'] for group in groups]
        self.assertIn('material', group_ids)
        self.assertIn('structure', group_ids)
        self.assertIn('property', group_ids)
        self.assertIn('skip', group_ids)
        material_targets = next(g for g in groups if g['id'] == 'material')['items']
        self.assertTrue(any(item['target'] == TARGET_NAME for item in material_targets))
        structure_targets = next(g for g in groups if g['id'] == 'structure')['items']
        self.assertTrue(
            any(item['target'] == f'{TARGET_STRUCTURE_PREFIX}{density_field.name}' for item in structure_targets)
        )

    def test_merge_structure_payloads_prefers_nonblank(self):
        merged = merge_structure_sql_payloads(
            [
                {'breaking_load': '100'},
                {'breaking_load': None},
                {'breaking_load': '200'},
                {'breaking_load': ''},
            ]
        )
        self.assertEqual(merged['breaking_load'], '200')

    def test_suggest_target_skips_claimed_structure_field(self):
        structure_type, density_field = create_import_structure_type(
            code='dup_suggest_fabric',
            table_name='structures_dup_suggest_fabric',
        )
        self.addCleanup(SQLExecutor.drop_table, structure_type)
        from apps.materials.imports.wide import WideColumn

        claimed = {f'{TARGET_STRUCTURE_PREFIX}{density_field.name}'}
        col = WideColumn(index=3, label='Плотность пов', group='')
        suggested = suggest_target(col, [], [density_field], claimed_targets=claimed)
        self.assertEqual(suggested, TARGET_SKIP)

    def test_parse_boolean_and_date_modes(self):
        from datetime import date

        from apps.materials.imports.value_parse import PARSE_BOOLEAN, PARSE_DATE

        yes = parse_property_cell('да', mode=PARSE_BOOLEAN)
        self.assertEqual(yes['value'], 'true')
        self.assertEqual(yes['confidence'], 'ok')
        no = parse_property_cell('Нет', mode=PARSE_BOOLEAN)
        self.assertEqual(no['value'], 'false')
        self.assertEqual(parse_property_cell(True, mode=PARSE_BOOLEAN)['value'], 'true')
        self.assertEqual(parse_property_cell(0, mode=PARSE_BOOLEAN)['value'], 'false')
        bad = parse_property_cell('иногда', mode=PARSE_BOOLEAN)
        self.assertEqual(bad['confidence'], 'uncertain')

        iso = parse_property_cell('2024-03-15', mode=PARSE_DATE)
        self.assertEqual(iso['value'], '2024-03-15')
        self.assertEqual(iso['confidence'], 'ok')
        dotted = parse_property_cell('15.03.2024', mode=PARSE_DATE)
        self.assertEqual(dotted['value'], '2024-03-15')
        self.assertEqual(
            parse_property_cell(date(2024, 7, 1), mode=PARSE_DATE)['value'],
            '2024-07-01',
        )
        bad_date = parse_property_cell('неделя', mode=PARSE_DATE)
        self.assertEqual(bad_date['confidence'], 'uncertain')

    def test_parse_tolerance_and_range(self):
        tol = parse_property_cell('0,27±0,03')
        self.assertEqual(tol['value_kind'], 'tolerance')
        self.assertEqual(tol['confidence'], 'ok')
        rng = parse_property_cell('900-1200')
        self.assertEqual(rng['value_kind'], 'range')

    def test_parse_number_strips_units(self):
        with_unit = parse_property_cell('12,5 мм')
        self.assertEqual(with_unit['value'], '12.5')
        self.assertEqual(with_unit['value_kind'], 'scalar')
        self.assertEqual(with_unit['confidence'], 'ok')
        self.assertTrue(with_unit['note'].startswith('число извлечено'))

        per_strip = parse_property_cell('4050/ 50мм')
        self.assertEqual(per_strip['value'], '4050')
        self.assertEqual(per_strip['confidence'], 'ok')
        self.assertTrue(per_strip['note'].startswith('число извлечено'))

        compact = parse_property_cell('4050/50мм')
        self.assertEqual(compact['value'], '4050')
        self.assertEqual(compact['confidence'], 'ok')

    def test_parse_plus_as_tolerance_from_excel(self):
        """Сводные часто пишут «0,27+0,035» вместо «±»."""
        tol = parse_property_cell('0,27+0,035')
        self.assertEqual(tol['value_kind'], 'tolerance')
        self.assertEqual(tol['value'], '0.27')
        self.assertEqual(tol['value_b'], '0.035')
        self.assertEqual(tol['confidence'], 'ok')

        with_unit = parse_property_cell('12+1 /м')
        self.assertEqual(with_unit['value_kind'], 'tolerance')
        self.assertEqual(with_unit['value'], '12')
        self.assertEqual(with_unit['value_b'], '1')

    def test_blank_placeholders_are_empty(self):
        from apps.materials.imports.value_parse import is_blank_cell

        for raw in (None, '', '  ', '-', '—', '–', 'н/д', 'N/A', '...'):
            self.assertTrue(is_blank_cell(raw), raw)
            self.assertIsNone(parse_property_cell(raw))

    def test_detect_layout_on_svodnaya(self):
        xlsx = next(Path(__file__).resolve().parents[2].glob('Сводная*.xlsx'), None)
        if xlsx is None:
            self.skipTest('Сводная по материалам.xlsx не в корне репозитория')
        header, group = detect_header_layout(xlsx, sheet_name='Стеклоткани')
        self.assertEqual(header, 2)
        self.assertEqual(group, 1)
        table = load_wide_table(xlsx, sheet_name='Стеклоткани', header_row=2, group_row=1)
        labels = [c.label.casefold() for c in table.columns]
        self.assertTrue(any('наименование' in label for label in labels))
        first_name = table.rows[0][table.columns[0].index]
        self.assertNotEqual(str(first_name).casefold(), 'наименование')

    def test_header_echo_row_skipped_when_wrong_header_row(self):
        xlsx = next(Path(__file__).resolve().parents[2].glob('Сводная*.xlsx'), None)
        if xlsx is None:
            self.skipTest('Сводная по материалам.xlsx не в корне репозитория')
        # header_row=1 → первая «data»-строка = подписи колонок; должна отфильтроваться
        table = load_wide_table(xlsx, sheet_name='Стеклоткани', header_row=1, group_row=0)
        for row in table.rows[:3]:
            values = [str(v).casefold() for v in row.values() if v is not None and str(v).strip()]
            self.assertFalse(
                values[:2] == ['наименование', 'марка'],
                msg=f'header echo leaked into data: {values[:4]}',
            )

    def test_xlsx_expands_vertically_merged_cells(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Demo'
        sheet['A1'] = 'Наименование'
        sheet['B1'] = 'Плотность пов'
        sheet['A2'] = 'Материал A'
        sheet['A3'] = 'Материал B'
        sheet['A4'] = 'Материал C'
        sheet['B2'] = 260
        sheet.merge_cells('B2:B4')
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as handle:
            path = Path(handle.name)
        try:
            workbook.save(path)
            table = load_wide_table(path, header_row=1)
            self.assertEqual(len(table.rows), 3)
            density_index = next(c.index for c in table.columns if 'плотность' in c.label.casefold())
            self.assertEqual(table.rows[0][density_index], 260)
            self.assertEqual(table.rows[1][density_index], 260)
            self.assertEqual(table.rows[2][density_index], 260)
        finally:
            path.unlink(missing_ok=True)

    def test_blank_mapped_cells_kept_as_empty_in_draft(self):
        table = load_wide_table(self.wide, header_row=1)
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': 'material.tags', 'parse': 'auto'},
            '2': {'target': f'property:{self.density.pk}', 'parse': 'auto'},
        }
        # inject blank-like value into first data row density
        table.rows[0][2] = '—'
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
        )
        first = next(d for d in drafts if d.name == 'Стеклоткань демо')
        self.assertEqual(len(first.properties), 1)
        self.assertEqual(first.properties[0].note, 'пусто')
        self.assertTrue(first.properties[0].include)

    def test_marka_not_used_as_shared_code(self):
        """Одинаковая марка Е-стекло не должна схлопывать разные наименования."""
        table = load_wide_table(self.wide, header_row=1)
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto', 'label': 'Наименование'},
            '1': {'target': 'material.tags', 'parse': 'auto', 'label': 'Марка'},
            '2': {'target': f'property:{self.density.pk}', 'parse': 'auto', 'label': 'Плотность пов'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
        )
        self.assertEqual(len(drafts), 2)
        codes = {d.code for d in drafts}
        self.assertEqual(len(codes), 2)
        self.assertTrue(all('марка::' in d.tags for d in drafts))

    def test_marka_osnova_and_utok_become_separate_scoped_tags(self):
        from apps.materials.imports.staging import _tag_from_column
        from apps.materials.imports.wide import WideColumn

        warp = WideColumn(index=0, label='Марка', group='Волокно (основа)')
        weft = WideColumn(index=1, label='Марка', group='Волокно (уток)')
        self.assertEqual(_tag_from_column(warp, 'EC13'), 'марка основа::EC13')
        self.assertEqual(_tag_from_column(weft, 'EC9'), 'марка уток::EC9')
        self.assertEqual(
            _tag_from_column(WideColumn(index=2, label='Плотность'), '6.5 ends/cm'),
            'Плотность::6.5 ends/cm',
        )
        self.assertEqual(
            _tag_from_column(weft, 'Уток: EC 9 - 204 tex'),
            'марка уток::EC 9 - 204 tex',
        )

    def test_always_create_keeps_separate_rows(self):
        table = load_wide_table(self.wide, header_row=1)
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': 'material.code', 'parse': 'auto'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_ALWAYS_CREATE,
        )
        self.assertEqual(len({d.code for d in drafts}), 2)

    def test_suggest_target_prefers_structure_field(self):
        structure_type, density_field = create_import_structure_type(
            code='map_suggest_fabric',
            table_name='structures_map_suggest_fabric',
        )
        try:
            table = load_wide_table(self.wide, header_row=1)
            density_col = next(c for c in table.columns if 'плотность' in c.label.casefold())
            properties = list(Property.objects.all())
            structure_fields = list(StructureField.objects.filter(structure_type=structure_type))
            target = suggest_target(density_col, properties, structure_fields)
            self.assertEqual(target, f'{TARGET_STRUCTURE_PREFIX}{density_field.name}')
        finally:
            SQLExecutor.drop_table(structure_type)


class MaterialImportHybridTests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        self.structure_type, self.density_field = create_import_structure_type(
            code='hybrid_fabric',
            table_name='structures_hybrid_fabric',
        )
        group = PropertyGroup.objects.create(name='Hybrid extra group', sort_order=1)
        self.extra_prop = Property.objects.create(
            name='manufacturer_note',
            display_name='Производитель',
            data_type='string',
            group=group,
        )
        self.wide = (
            Path(__file__).resolve().parent
            / 'fixtures'
            / 'import_examples'
            / 'materials_wide_sample.csv'
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def test_hybrid_import_writes_structure_and_extra_property(self):
        table = load_wide_table(self.wide, header_row=1)
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': 'material.tags', 'parse': 'auto'},
            '2': {'target': f'structure:{self.density_field.name}', 'parse': 'auto'},
            '4': {'target': f'property:{self.extra_prop.pk}', 'parse': 'text'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        material = Material.objects.get(name='Стеклоткань демо', home_workspace=self.workspace)
        self.assertEqual(material.struct_type_id, self.structure_type.pk)
        self.assertIsNotNone(material.struct_props_id)
        row = get_row(self.structure_type, material.struct_props_id)
        self.assertIsNotNone(row)
        self.assertEqual(str(row[self.density_field.name]).rstrip('0').rstrip('.'), '260')
        self.assertTrue(
            material.properties.filter(property=self.extra_prop, value__icontains='Завод').exists()
        )

    def test_hybrid_import_resolves_structure_and_property_material_links(self):
        from apps.core.property_number_value import VALUE_KIND_SCALAR
        from apps.materials.imports.staging import DraftMaterial, DraftProperty, DraftStructureValue
        from apps.materials.imports.value_parse import CONFIDENCE_OK

        base = Material.objects.create(
            code='LINK-BASE',
            name='Базовый материал',
            home_workspace=self.workspace,
        )
        link_field = StructureField.objects.create(
            structure_type=self.structure_type,
            name='base_material',
            label='Базовый материал',
            field_type='MaterialLink',
            sort_order=10,
        )
        link_prop = Property.objects.create(
            name='related_material',
            display_name='Связанный материал',
            data_type='material_link',
            group=self.extra_prop.group,
        )
        drafts = [
            DraftMaterial(
                source_row=2,
                name='Дочерний материал',
                code='LINK-CHILD',
                description='',
                tags='',
                action='create',
                structure_values=[
                    DraftStructureValue(
                        field_name=link_field.name,
                        field_label=link_field.label,
                        column_label='base',
                        raw=base.code,
                        value_kind=VALUE_KIND_SCALAR,
                        value=base.code,
                        value_b='',
                        confidence=CONFIDENCE_OK,
                        note='',
                    ),
                ],
                properties=[
                    DraftProperty(
                        property_name=link_prop.name,
                        property_id=str(link_prop.pk),
                        column_label='related',
                        raw=base.name,
                        value_kind=VALUE_KIND_SCALAR,
                        value=base.name,
                        value_b='',
                        confidence=CONFIDENCE_OK,
                        note='',
                    ),
                ],
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        child = Material.objects.get(code='LINK-CHILD', home_workspace=self.workspace)
        row = get_row(self.structure_type, child.struct_props_id)
        self.assertIsNotNone(row)
        linked_pk = str(row[link_field.name]).replace('-', '')
        self.assertEqual(linked_pk, str(base.pk).replace('-', ''))
        prop = child.properties.get(property=link_prop)
        self.assertEqual(str(prop.value).replace('-', ''), str(base.pk).replace('-', ''))

    def test_hybrid_import_accepts_name_only_with_empty_fields(self):
        from apps.materials.imports.staging import DraftMaterial

        drafts = [
            DraftMaterial(
                source_row=2,
                name='Только название',
                code='NAME-ONLY-1',
                description='',
                tags='',
                action='create',
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        material = Material.objects.get(code='NAME-ONLY-1', home_workspace=self.workspace)
        self.assertEqual(material.name, 'Только название')
        self.assertIsNone(material.struct_props_id)

    def test_unknown_manufacturer_errors_without_create_option(self):
        from apps.materials.imports.staging import DraftMaterial

        drafts = [
            DraftMaterial(
                source_row=2,
                name='С тканью',
                code='DICT-ERR-1',
                description='',
                tags='',
                action='create',
                manufacturer='Unknown Vendor XYZ',
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertFalse(report.ok)
        self.assertTrue(any('не найден' in err.message for err in report.errors))

    def test_dictionary_create_is_deferred_until_apply(self):
        """Validate must not insert dictionary rows before the import transaction."""
        from apps.materials.imports.report import ImportReport
        from apps.materials.imports.staging import DraftMaterial
        from apps.materials.imports.validate import validate_drafts
        from apps.references.models import Manufacturer

        drafts = [
            DraftMaterial(
                source_row=2,
                name='Мат Deferred',
                code='DICT-DEF',
                description='',
                tags='',
                action='create',
                manufacturer='Brand New Deferred Co',
            ),
        ]
        report = ImportReport(dry_run=False)
        items = validate_drafts(
            drafts,
            structure_type=self.structure_type,
            workspace=self.workspace,
            report=report,
            create_missing_dictionaries=True,
            dry_run=False,
        )
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(items)
        self.assertIsNotNone(items[0].manufacturer_create)
        self.assertFalse(Manufacturer.objects.filter(name='Brand New Deferred Co').exists())

    def test_create_missing_dictionaries_with_dedupe(self):
        from apps.materials.imports.staging import DraftMaterial
        from apps.references.models import Manufacturer

        drafts = [
            DraftMaterial(
                source_row=2,
                name='Мат A',
                code='DICT-A',
                description='',
                tags='',
                action='create',
                manufacturer='Solvay Specialty',
            ),
            DraftMaterial(
                source_row=3,
                name='Мат B',
                code='DICT-B',
                description='',
                tags='',
                action='create',
                manufacturer='solvay specialty',
            ),
            DraftMaterial(
                source_row=4,
                name='Мат C',
                code='DICT-C',
                description='',
                tags='',
                action='create',
                # Same normalized code as existing seed "Hexcel" → link, not create
                manufacturer='HEXCEL!!!',
            ),
        ]
        dry = MaterialImporter(
            workspace=self.workspace,
            dry_run=True,
            create_missing_dictionaries=True,
        ).import_drafts(drafts, structure_type=self.structure_type)
        self.assertTrue(dry.ok, dry.errors)
        self.assertEqual(len(dry.dictionaries_created), 1)
        self.assertIn('Solvay Specialty', dry.dictionaries_created[0])
        self.assertTrue(dry.dictionaries_linked_by_code)
        self.assertFalse(Manufacturer.objects.filter(name='Solvay Specialty').exists())

        report = MaterialImporter(
            workspace=self.workspace,
            create_missing_dictionaries=True,
        ).import_drafts(drafts, structure_type=self.structure_type)
        self.assertTrue(report.ok, report.errors)
        vendor = Manufacturer.objects.get(name='Solvay Specialty')
        self.assertEqual(Manufacturer.objects.filter(name__iexact='solvay specialty').count(), 1)
        hexcel = Manufacturer.objects.get(code='hexcel')
        self.assertEqual(Material.objects.get(code='DICT-A').manufacturer_id, vendor.pk)
        self.assertEqual(Material.objects.get(code='DICT-B').manufacturer_id, vendor.pk)
        self.assertEqual(Material.objects.get(code='DICT-C').manufacturer_id, hexcel.pk)

    def test_create_reuses_on_integrity_error(self):
        """If insert races/collides, reuse existing row instead of hard error."""
        from apps.materials.imports.staging import DraftMaterial
        from apps.references.dictionaries import resolve_or_create_dictionary_item
        from apps.references.models import Manufacturer

        existing = Manufacturer.objects.create(name='Sino-Composites', code='sino_composites')
        # Simulate path that tries to create the same again (pending empty).
        result = resolve_or_create_dictionary_item(
            Manufacturer,
            'Sino-Composites',
            create_missing=True,
            dry_run=False,
            pending={},
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.item.pk, existing.pk)
        self.assertTrue(result.matched_existing)

        # Name differs but code would collide — should link by code, not error.
        result2 = resolve_or_create_dictionary_item(
            Manufacturer,
            'Sino Composites',
            create_missing=True,
            dry_run=False,
            pending={},
        )
        self.assertIsNone(result2.error, result2.error)
        self.assertEqual(result2.item.pk, existing.pk)
        self.assertTrue(result2.linked_by_code)

        drafts = [
            DraftMaterial(
                source_row=2,
                name='SC mat',
                code='SC-1',
                description='',
                tags='',
                action='create',
                manufacturer='Sino-Composites',
            ),
        ]
        report = MaterialImporter(
            workspace=self.workspace,
            create_missing_dictionaries=True,
        ).import_drafts(drafts, structure_type=self.structure_type)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(Material.objects.get(code='SC-1').manufacturer_id, existing.pk)

    def test_ambiguous_dictionary_match_is_error(self):
        from apps.materials.imports.staging import DraftMaterial
        from apps.references.models import Manufacturer

        Manufacturer.objects.create(name='Acme One', code='acme_one')
        Manufacturer.objects.create(name='Acme', code='shared_token')
        # Craft collision: raw text matching two rows is hard with unique name/code.
        # Use same iexact on code for one and name for another via identical token:
        Manufacturer.objects.filter(code='shared_token').update(code='acme')
        # Now "acme" matches code of second; add third with name Acme Dup - wait name Acme exists.
        # Two matches: code__iexact=acme → one row; name__iexact=acme → same row if name is Acme.
        # For true ambiguity need name of A matching code of B:
        Manufacturer.objects.filter(name='Acme One').update(code='other')
        Manufacturer.objects.filter(name='Acme').update(name='Other Acme', code='acme_x')
        Manufacturer.objects.create(name='Token', code='dup_key')
        Manufacturer.objects.create(name='dup_key', code='dup_key_2')

        drafts = [
            DraftMaterial(
                source_row=2,
                name='Amb',
                code='DICT-AMB',
                description='',
                tags='',
                action='create',
                manufacturer='dup_key',
            ),
        ]
        report = MaterialImporter(
            workspace=self.workspace,
            create_missing_dictionaries=True,
        ).import_drafts(drafts, structure_type=self.structure_type)
        self.assertFalse(report.ok)
        self.assertTrue(any('неоднозначно' in err.message for err in report.errors))

    def test_rows_without_name_are_skipped_not_blocking(self):
        """Пустое название (напр. пустая «Марка») — пропуск строки, остальные пишутся."""
        from apps.materials.imports.wide import WideColumn, WideTable

        table = WideTable(
            sheet_name='CSV',
            header_row=1,
            columns=[
                WideColumn(index=0, label='Марка'),
                WideColumn(index=1, label='Плотность пов'),
            ],
            rows=[
                {0: '', 1: 260},
                {0: 'E-стекло', 1: 300},
            ],
            preview_rows=[{0: '', 1: 260}, {0: 'E-стекло', 1: 300}],
        )
        drafts = build_staging_draft(
            table,
            {
                '0': {'target': 'material.name', 'parse': 'auto'},
                '1': {'target': f'structure:{self.density_field.name}', 'parse': 'auto'},
            },
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        self.assertEqual(len(drafts), 2)
        self.assertEqual(drafts[0].action, 'skip')
        self.assertTrue(any('Пропущено' in w for w in drafts[0].warnings))
        self.assertIn('Марка', drafts[0].warnings[0])
        self.assertEqual(drafts[1].action, 'create')
        self.assertEqual(drafts[1].name, 'E-стекло')

        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(Material.objects.filter(home_workspace=self.workspace).count(), 1)
        self.assertTrue(
            Material.objects.filter(home_workspace=self.workspace, name='E-стекло').exists()
        )

    def test_hybrid_import_keeps_mapped_empty_structure_field_as_null(self):
        from apps.core.property_number_value import VALUE_KIND_SCALAR
        from apps.materials.imports.staging import DraftMaterial, DraftStructureValue
        from apps.materials.imports.value_parse import CONFIDENCE_OK

        drafts = [
            DraftMaterial(
                source_row=2,
                name='Пустое поле структуры',
                code='EMPTY-MAPPED-1',
                description='',
                tags='',
                action='create',
                structure_values=[
                    DraftStructureValue(
                        field_name='weave_type',
                        field_label='Тип плетения',
                        column_label='Плетение',
                        raw='',
                        value_kind=VALUE_KIND_SCALAR,
                        value='',
                        value_b='',
                        confidence=CONFIDENCE_OK,
                        note='пусто',
                        include=True,
                    ),
                ],
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        material = Material.objects.get(code='EMPTY-MAPPED-1', home_workspace=self.workspace)
        row = get_row(self.structure_type, material.struct_props_id)
        self.assertIsNotNone(row)
        self.assertIn(row.get('weave_type'), (None, ''))

    def test_hybrid_import_skips_structure_field_when_include_false(self):
        from apps.core.property_number_value import VALUE_KIND_SCALAR
        from apps.materials.imports.staging import DraftMaterial, DraftStructureValue
        from apps.materials.imports.value_parse import CONFIDENCE_OK

        drafts = [
            DraftMaterial(
                source_row=2,
                name='Пропуск поля',
                code='SKIP-FIELD-1',
                description='есть описание',
                tags='',
                action='create',
                structure_values=[
                    DraftStructureValue(
                        field_name='weave_type',
                        field_label='Тип плетения',
                        column_label='Плетение',
                        raw='саржа',
                        value_kind=VALUE_KIND_SCALAR,
                        value='саржа',
                        value_b='',
                        confidence=CONFIDENCE_OK,
                        note='',
                        include=False,
                    ),
                ],
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        material = Material.objects.get(code='SKIP-FIELD-1', home_workspace=self.workspace)
        self.assertIsNone(material.struct_props_id)

    def test_staging_keeps_blank_mapped_structure_cells(self):
        table = load_wide_table(self.wide, header_row=1)
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '3': {'target': f'structure:weave_type', 'parse': 'text'},
        }
        # Пустая ячейка в колонке плетения
        table.rows[0][3] = None
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        self.assertTrue(drafts)
        weave_vals = [s for s in drafts[0].structure_values if s.field_name == 'weave_type']
        self.assertEqual(len(weave_vals), 1)
        self.assertEqual(weave_vals[0].value, '')
        self.assertTrue(weave_vals[0].include)

    def test_hybrid_import_rejects_overlong_material_name(self):
        from apps.materials.imports.staging import DraftMaterial

        limit = Material._meta.get_field('name').max_length
        drafts = [
            DraftMaterial(
                source_row=2,
                name='X' * (limit + 1),
                code='LONG-NAME',
                description='ok',
                tags='',
                action='create',
            ),
        ]
        report = MaterialImporter(workspace=self.workspace, dry_run=True).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertFalse(report.ok)
        self.assertTrue(any(str(limit) in err.message for err in report.errors))

    def test_hybrid_import_accepts_long_layup_material_name(self):
        from apps.materials.imports.staging import DraftMaterial

        name = (
            'Образец 50x30x2, Пленка 5 мкм - (0º/90º) – пленка 5 мкм - (0º/90º) '
            '(+45º/-45º) (+45º/-45º) (90º/0º) (+45º/-45º) (+45º/-45º) (90º/0º) - '
            'фольга - (0º/90º)) (-45º/+45º) (-45º/+45º) (0º/90º) (-45º/+45º)'
            '(-45º/+45º) (90º/0º) - Пленка 5 мкм - (90º/0º) - пленка 5 мкм. '
            '№1. Препрег 120 г/кв.м.'
        )
        self.assertGreater(len(name), 200)
        self.assertLessEqual(len(name), Material._meta.get_field('name').max_length)
        drafts = [
            DraftMaterial(
                source_row=2,
                name=name,
                code='LAYUP-1',
                description='укладка',
                tags='',
                action='create',
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(
            Material.objects.get(code='LAYUP-1', home_workspace=self.workspace).name,
            name,
        )

    def test_hybrid_import_resolves_material_link_within_same_batch(self):
        from apps.core.property_number_value import VALUE_KIND_SCALAR
        from apps.materials.imports.staging import DraftMaterial, DraftProperty
        from apps.materials.imports.value_parse import CONFIDENCE_OK

        link_prop = Property.objects.create(
            name='batch_related',
            display_name='Связь в пакете',
            data_type='material_link',
            group=self.extra_prop.group,
        )
        drafts = [
            DraftMaterial(
                source_row=2,
                name='Пакет A',
                code='BATCH-A',
                description='',
                tags='',
                action='create',
                properties=[
                    DraftProperty(
                        property_name=link_prop.name,
                        property_id=str(link_prop.pk),
                        column_label='rel',
                        raw='BATCH-B',
                        value_kind=VALUE_KIND_SCALAR,
                        value='BATCH-B',
                        value_b='',
                        confidence=CONFIDENCE_OK,
                        note='',
                    ),
                ],
            ),
            DraftMaterial(
                source_row=3,
                name='Пакет B',
                code='BATCH-B',
                description='цель ссылки',
                tags='',
                action='create',
            ),
        ]
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts,
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok, report.errors)
        a = Material.objects.get(code='BATCH-A', home_workspace=self.workspace)
        b = Material.objects.get(code='BATCH-B', home_workspace=self.workspace)
        self.assertEqual(
            str(a.properties.get(property=link_prop).value).replace('-', ''),
            str(b.pk).replace('-', ''),
        )


class MaterialImportUITests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        self.structure_type, self.density_field = create_import_structure_type(
            code='ui_import_fabric',
            table_name='structures_ui_import_fabric',
        )
        group = PropertyGroup.objects.create(name='UI import group', sort_order=1)
        self.density = Property.objects.create(
            name='areal_density',
            display_name='Плотность пов',
            data_type='number',
            group=group,
        )
        self.wide_sample = (
            Path(__file__).resolve().parent
            / 'fixtures'
            / 'import_examples'
            / 'materials_wide_sample.csv'
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def test_import_page_renders(self):
        response = self.client.get(reverse('materials:import'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Вперёд')
        self.assertContains(response, 'import-wizard-nav')

    def test_wizard_nav_back_and_forward_on_configure_and_mapping(self):
        mapping = self._upload_and_configure_wide_sample()
        self.assertEqual(mapping.context['step'], 'mapping')
        self.assertContains(mapping, 'import-wizard-nav')
        self.assertContains(mapping, '← Назад')
        self.assertContains(mapping, 'Вперёд')
        self.assertEqual(
            mapping.context['wizard_back_url'],
            reverse('materials:import') + '?step=configure',
        )

        configure = self.client.get(mapping.context['wizard_back_url'])
        self.assertEqual(configure.status_code, 200)
        self.assertEqual(configure.context['step'], 'configure')
        self.assertContains(configure, '← Назад')
        self.assertEqual(
            configure.context['wizard_back_url'],
            reverse('materials:import') + '?step=upload',
        )

        back_upload = self.client.get(configure.context['wizard_back_url'])
        self.assertEqual(back_upload.status_code, 200)
        self.assertEqual(back_upload.context['step'], 'upload')
        self.assertTrue(back_upload.context['has_staged_file'])
        self.assertContains(back_upload, 'вернитесь к настройке листа')

    def test_import_templates_save_and_load_with_structure_type(self):
        mapping_page = self._upload_and_configure_wide_sample()
        self.assertEqual(mapping_page.context['step'], 'mapping')

        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.context['step'], 'review')

        # Возвращаемся на mapping и сохраняем шаблон из текущего map_* (не из «старой» сессии).
        self.client.get(reverse('materials:import'), {'step': 'mapping'})
        save = self.client.post(
            reverse('materials:import'),
            {
                'action': 'save_template',
                'template_name': 'Шаблон ткани',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(save.status_code, 200)
        profile = MaterialImportProfile.objects.get(
            workspace=self.workspace,
            name='Шаблон ткани',
        )
        self.assertEqual(profile.structure_type_id, str(self.structure_type.pk))
        self.assertTrue(any(
            (col.get('target') or '') == 'material.name'
            for col in profile.config.get('columns') or []
        ))
        self.assertTrue(any(
            (col.get('target') or '') == 'material.tags'
            for col in profile.config.get('columns') or []
        ))

        # Второй шаблон с другим маппингом «Марка» → skip (через POST UI).
        save_b = self.client.post(
            reverse('materials:import'),
            {
                'action': 'save_template',
                'template_name': 'Шаблон без марки',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'skip',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(save_b.status_code, 200)
        profile_b = MaterialImportProfile.objects.get(
            workspace=self.workspace,
            name='Шаблон без марки',
        )
        self.assertTrue(any(
            (col.get('label') or '') == 'Марка' and (col.get('target') or '') == 'skip'
            for col in profile_b.config.get('columns') or []
        ))

        templates = import_templates_for_workspace(self.workspace)
        self.assertEqual(len(templates), 2)
        self.assertIn(self.structure_type.name, templates[0]['option_label'])

        with self.wide_sample.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'materials_wide_sample2.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.assertEqual(
            self.client.post(
                reverse('materials:import'),
                {'action': 'upload', 'file': uploaded},
            ).status_code,
            302,
        )
        configure = self.client.get(reverse('materials:import'), {'step': 'configure'})
        self.assertNotContains(configure, 'Шаблоны маппинга')
        self.assertNotContains(configure, 'Применить шаблон')

        # Сначала выбираем структуру и переходим к сопоставлению.
        self.assertEqual(
            self.client.post(
                reverse('materials:import'),
                {
                    'action': 'configure',
                    'sheet': 'CSV',
                    'header_row': '1',
                    'group_row': '',
                    'match_policy': MATCH_BY_NAME,
                    'structure_type_id': str(self.structure_type.pk),
                },
            ).status_code,
            200,
        )
        mapping_before = self.client.get(reverse('materials:import'), {'step': 'mapping'})
        self.assertEqual(mapping_before.status_code, 200)
        self.assertContains(mapping_before, 'Шаблоны маппинга')
        self.assertContains(mapping_before, 'Шаблон ткани')
        self.assertContains(mapping_before, 'Применить шаблон')
        self.assertContains(mapping_before, 'Сохранить шаблон')
        self.assertContains(mapping_before, 'id="import-templates-panel"')
        self.assertContains(mapping_before, 'id="import-template-name"')
        self.assertContains(mapping_before, 'id="import-template-id"')

        applied = self.client.post(
            reverse('materials:import'),
            {
                'action': 'load_template',
                'template_id': str(profile.pk),
            },
        )
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.context['step'], 'mapping')
        self.assertEqual(
            str(applied.context['config'].get('structure_type_id')),
            str(self.structure_type.pk),
        )
        self.assertEqual(
            str(applied.context['selected_template_id']),
            str(profile.pk),
        )
        tags_a = next(
            (
                row
                for row in applied.context['mapping_rows']
                if (row['column'].label or '') == 'Марка'
            ),
            None,
        )
        self.assertIsNotNone(tags_a)
        self.assertEqual(tags_a['target'], 'material.tags')
        self.assertContains(applied, 'Сохранить шаблон')
        self.assertContains(applied, 'Применить шаблон')
        self.assertContains(applied, 'id="import-templates-panel"')
        self.assertEqual(applied.context['missing_required_targets'], [])

        # Выбор шаблона — на шаге сопоставления, не на «Лист и структура».
        configure_after = self.client.get(reverse('materials:import'), {'step': 'configure'})
        self.assertNotContains(configure_after, 'Применить шаблон')
        mapping_after = self.client.get(reverse('materials:import'), {'step': 'mapping'})
        map_html = mapping_after.content.decode('utf-8')
        self.assertIn(
            f'value="{profile.pk}" selected',
            map_html.replace("'", '"'),
        )

        applied_b = self.client.post(
            reverse('materials:import'),
            {
                'action': 'load_template',
                'template_id': str(profile_b.pk),
            },
        )
        self.assertEqual(applied_b.status_code, 200)
        self.assertEqual(applied_b.context['step'], 'mapping')
        self.assertEqual(
            str(applied_b.context['selected_template_id']),
            str(profile_b.pk),
        )
        self.assertContains(applied_b, 'Применить шаблон')
        tags_b = next(
            (
                row
                for row in applied_b.context['mapping_rows']
                if (row['column'].label or '') == 'Марка'
            ),
            None,
        )
        self.assertIsNotNone(tags_b)
        self.assertEqual(tags_b['target'], 'skip')
        # field UI: у «Теги» не должно остаться колонки «Марка» от первого шаблона
        tags_field = next(
            (
                row
                for row in applied_b.context['field_mapping_rows']
                if row.get('is_tag') and row.get('column') and row['column'].label == 'Марка'
            ),
            None,
        )
        self.assertIsNone(tags_field)

    def test_sidebar_shows_import_link(self):
        response = self.client.get(reverse('materials:list'))
        self.assertContains(response, reverse('materials:import'))
        self.assertNotContains(response, 'btn btn-outline-primary btn-sm">Импорт')

    def test_import_review_board_moves_between_columns(self):
        from apps.materials.imports.review_status import (
            IMPORT_STATUS_APPROVED,
            IMPORT_STATUS_VERIFIED,
            apply_import_tags,
        )

        material = Material.objects.create(
            code='REV-1',
            name='Review candidate',
            home_workspace=self.workspace,
            struct_type=self.structure_type,
        )
        apply_import_tags(
            material,
            workspace=self.workspace,
            import_names=[],
            created=True,
        )
        self.assertIn(
            IMPORT_STATUS_APPROVED,
            set(material.tags.values_list('name', flat=True)),
        )

        page = self.client.get(reverse('materials:import_review'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'На проверке')
        self.assertContains(page, 'Учрежден')
        self.assertNotContains(page, 'Утвержден')
        self.assertNotContains(page, 'Проверено')
        self.assertContains(page, 'Review candidate')

        to_verified = self.client.post(
            reverse('materials:import_review'),
            {
                'action': 'set_status',
                'status': 'verified',
                'material_id': str(material.pk),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(to_verified.status_code, 200)
        payload = to_verified.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['status'], 'verified')
        self.assertIn('tags_html', payload)
        self.assertIn('учрежден', payload['tags_html'])
        material.refresh_from_db()
        names = set(material.tags.values_list('name', flat=True))
        self.assertIn(IMPORT_STATUS_VERIFIED, names)
        self.assertNotIn(IMPORT_STATUS_APPROVED, names)

        board = self.client.get(reverse('materials:import_review'))
        self.assertContains(board, 'Учрежден')
        self.assertContains(board, 'Review candidate')

        back = self.client.post(
            reverse('materials:import_review'),
            {
                'action': 'set_status',
                'status': 'approved',
                'material_id': str(material.pk),
            },
        )
        self.assertEqual(back.status_code, 302)
        material.refresh_from_db()
        names = set(material.tags.values_list('name', flat=True))
        self.assertIn(IMPORT_STATUS_APPROVED, names)
        self.assertNotIn(IMPORT_STATUS_VERIFIED, names)

    def _upload_and_configure_wide_sample(self):
        with self.wide_sample.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'materials_wide_sample.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.assertEqual(
            self.client.post(
                reverse('materials:import'),
                {'action': 'upload', 'file': uploaded},
            ).status_code,
            302,
        )
        configure = self.client.post(
            reverse('materials:import'),
            {
                'action': 'configure',
                'sheet': 'CSV',
                'header_row': '1',
                'group_row': '',
                'match_policy': MATCH_BY_NAME,
                'structure_type_id': str(self.structure_type.pk),
            },
        )
        self.assertEqual(configure.status_code, 200)
        return configure

    def test_configure_hides_header_rows_for_simple_layout(self):
        with self.wide_sample.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'materials_wide_sample.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.assertEqual(
            self.client.post(
                reverse('materials:import'),
                {'action': 'upload', 'file': uploaded},
            ).status_code,
            302,
        )
        response = self.client.get(reverse('materials:import'), {'step': 'configure'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_header_layout_fields'])
        self.assertContains(response, 'name="header_row"')
        self.assertContains(response, 'type="hidden"')
        self.assertNotContains(response, 'id="import-header-row"')
        self.assertNotContains(response, 'id="import-group-row"')
        self.assertContains(response, 'Заголовки в строке 1')
        self.assertContains(response, 'import-layout-schema')
        self.assertContains(response, 'import-schema')
        self.assertContains(response, 'import-schema__arrow')
        self.assertContains(response, 'Файл')
        self.assertContains(response, 'База данных')
        self.assertContains(response, 'Статистика по листу')
        self.assertContains(response, 'Использовать справочники')
        schema = response.context['layout_schema']
        self.assertEqual(schema['header_row'], 1)
        self.assertFalse(schema['has_groups'])
        self.assertEqual(schema['rows'][0]['role'], 'header')

    def test_build_import_layout_schema_marks_group_and_header(self):
        from openpyxl import Workbook
        from tempfile import NamedTemporaryFile

        workbook = Workbook()
        sheet = workbook.active
        sheet['A1'] = 'Ткань'
        sheet['B1'] = 'Ткань'
        sheet['C1'] = 'Волокно'
        sheet['A2'] = 'Наименование'
        sheet['B2'] = 'Марка'
        sheet['C2'] = 'Диаметр'
        sheet['A3'] = 'Т-23'
        sheet['B3'] = 'E-glass'
        sheet['C3'] = '9'
        tmp = NamedTemporaryFile(suffix='.xlsx', delete=False)
        tmp.close()
        path = Path(tmp.name)
        try:
            workbook.save(path)
            schema = build_import_layout_schema(
                path, header_row=2, group_row=1, max_cols=3, max_data_rows=1,
            )
            self.assertTrue(schema['has_groups'])
            self.assertEqual(schema['rows'][0]['role'], 'group')
            self.assertEqual(schema['rows'][1]['role'], 'header')
            self.assertEqual(schema['rows'][2]['role'], 'data')
            self.assertIn('Наименование', schema['rows'][1]['cells'])
            schema_wide = build_import_layout_schema(path, header_row=2, group_row=1)
            self.assertGreaterEqual(schema_wide['cols_shown'], 3)
            self.assertGreaterEqual(schema_wide['data_rows_shown'], 1)
            self.assertGreaterEqual(len(schema_wide['rows']), 3)
        finally:
            path.unlink(missing_ok=True)

    def test_build_import_layout_schema_trims_trailing_empty_rows_and_columns(self):
        from openpyxl import Workbook
        from tempfile import NamedTemporaryFile

        workbook = Workbook()
        sheet = workbook.active
        sheet['A1'] = 'Наименование'
        sheet['B1'] = 'Марка'
        sheet['A2'] = 'Мат-1'
        sheet['B2'] = 'X'
        sheet['A3'] = 'Мат-2'
        sheet['B3'] = 'Y'
        # Пустые хвосты, которые Excel часто держит в used range.
        sheet['M1'] = None
        sheet['A500'] = None
        tmp = NamedTemporaryFile(suffix='.xlsx', delete=False)
        tmp.close()
        path = Path(tmp.name)
        try:
            workbook.save(path)
            schema = build_import_layout_schema(path, header_row=1, group_row=0)
            self.assertEqual(schema['cols_shown'], 2)
            self.assertEqual(schema['cols_total'], 2)
            self.assertEqual(schema['data_rows_shown'], 2)
            self.assertEqual(len(schema['rows']), 3)
            self.assertEqual(len(schema['rows'][0]['cells']), 2)
        finally:
            path.unlink(missing_ok=True)

    def test_refresh_layout_keeps_user_header_rows(self):
        from openpyxl import Workbook
        from tempfile import NamedTemporaryFile

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Лист1'
        sheet['A1'] = 'Группа'
        sheet['A2'] = 'Наименование'
        sheet['B2'] = 'Марка'
        sheet['A3'] = 'Мат-1'
        sheet['B3'] = 'X'
        sheet['A4'] = 'Мат-2'
        sheet['B4'] = 'Y'
        sheet['A5'] = 'Мат-3'
        sheet['B5'] = 'Z'
        tmp = NamedTemporaryFile(suffix='.xlsx', delete=False)
        tmp.close()
        path = Path(tmp.name)
        try:
            workbook.save(path)
            with path.open('rb') as handle:
                uploaded = SimpleUploadedFile(
                    'layout_refresh.xlsx',
                    handle.read(),
                    content_type=(
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    ),
                )
            self.assertEqual(
                self.client.post(
                    reverse('materials:import'),
                    {'action': 'upload', 'file': uploaded},
                ).status_code,
                302,
            )
            refresh = self.client.post(
                reverse('materials:import'),
                {
                    'action': 'configure',
                    'refresh_layout': '1',
                    'sheet': 'Лист1',
                    'header_row': '2',
                    'group_row': '1',
                },
            )
            self.assertEqual(refresh.status_code, 200)
            self.assertEqual(refresh.context['layout_form_header_row'], 2)
            self.assertEqual(refresh.context['layout_form_group_row'], 1)
            schema = refresh.context['layout_schema']
            self.assertEqual(schema['header_row'], 2)
            self.assertEqual(schema['group_row'], 1)
            self.assertEqual(schema['rows'][0]['role'], 'group')
            self.assertEqual(schema['rows'][1]['role'], 'header')
            data_roles = [row['role'] for row in schema['rows'] if row['role'] == 'data']
            self.assertGreaterEqual(len(data_roles), 3)
            self.assertContains(refresh, 'id="import-header-row"')
            self.assertContains(refresh, 'value="2"')
            self.assertContains(refresh, 'value="1"')
        finally:
            path.unlink(missing_ok=True)

    def test_mapping_constructor_renders(self):
        response = self._upload_and_configure_wide_sample()
        self.assertContains(response, 'import-map-constructor')
        self.assertContains(response, 'import-map-catalog')
        self.assertContains(response, 'Поля для записи')
        self.assertContains(response, 'Колонки файла')
        self.assertContains(response, 'Сопоставление колонок')
        self.assertContains(response, 'import-map-mapping')
        self.assertContains(response, 'import-map-bound-kind')
        self.assertContains(response, 'Тип поля')
        self.assertContains(response, 'import-map-expr-slot')
        self.assertContains(response, 'import-map-panel')
        self.assertContains(response, 'data-drop-slot')
        self.assertContains(response, 'draggable="true"')
        self.assertContains(response, 'data-field-target="material.name"')
        self.assertContains(response, 'Из структуры')
        self.assertContains(response, 'Дополнительные свойства')
        self.assertContains(response, 'import-map-section-tag')
        self.assertContains(response, 'import-map-section__title">Теги</span>')
        self.assertContains(response, 'значение/колонку из полей')
        self.assertContains(response, 'Справочники')
        self.assertContains(response, 'Поле материала')
        self.assertContains(response, 'Теги для всех материалов')
        self.assertContains(response, 'name="import_default_tags"')
        self.assertContains(response, 'import-map-section-material')
        self.assertContains(response, 'import-map-section')
        self.assertContains(response, 'data-map-section-toggle')
        self.assertContains(response, 'import-map-add-property')
        self.assertContains(response, 'import-map-section__add')
        self.assertContains(response, 'import-map-add-field')
        self.assertContains(response, 'reference-properties-modal')
        self.assertContains(response, 'reference_properties_picker.js')
        self.assertContains(response, 'Выбор свойств')
        self.assertContains(response, 'import_mapping_constructor.js')
        self.assertContains(response, 'name="map_0"')
        self.assertContains(response, 'name="parse_0"')
        self.assertNotContains(response, 'id="import-match-policy"')
        self.assertNotContains(response, 'name="match_policy"')
        self.assertNotContains(response, 'Проверка дубликатов')
        self.assertContains(response, 'import-file-columns')
        self.assertContains(response, '★ обязательно')
        self.assertContains(response, '>Да/Нет<')
        self.assertContains(response, '>Дата<')
        self.assertNotContains(response, 'import-map-column-select')
        self.assertNotContains(response, 'Неиспользованные колонки')
        self.assertNotContains(response, 'Поля для подстановки')
        self.assertNotContains(response, 'import-map-addon-modal')
        self.assertNotContains(response, 'Название ★ обязательно')
        self.assertContains(response, 'form="import-map-form"')
        self.assertContains(response, 'import-map-continue')
        self.assertContains(response, 'novalidate')
        constructor_js = (
            Path(__file__).resolve().parents[2] / 'static' / 'js' / 'import_mapping_constructor.js'
        ).read_text(encoding='utf-8')
        self.assertIn("document.querySelectorAll('.import-map-continue')", constructor_js)
        self.assertNotIn("form.querySelectorAll('.import-map-continue')", constructor_js)

    def test_configure_does_not_show_match_policy(self):
        with self.wide_sample.open('rb') as handle:
            uploaded = SimpleUploadedFile(
                'materials_wide_sample.csv',
                handle.read(),
                content_type='text/csv',
            )
        self.assertEqual(
            self.client.post(
                reverse('materials:import'),
                {'action': 'upload', 'file': uploaded},
            ).status_code,
            302,
        )
        response = self.client.get(reverse('materials:import'), {'step': 'configure'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="import-match-policy"')
        self.assertContains(response, 'Лист и структура')

    def test_mapping_forces_always_create_policy(self):
        self._upload_and_configure_wide_sample()
        response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_CODE,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.code',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(response.status_code, 200)
        config = get_import_config(self.client.session)
        self.assertEqual(config.get('match_policy'), MATCH_ALWAYS_CREATE)

    def test_mapping_without_name_blocked(self):
        self._upload_and_configure_wide_sample()
        blocked = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'skip',
                'parse_0': 'auto',
                'map_1': 'skip',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, 'import-map-constructor')
        self.assertContains(blocked, 'не сопоставлено обязательное поле')
        self.assertContains(blocked, 'Название')
        self.assertNotContains(blocked, 'Итог по черновику')

    def test_duplicate_structure_mapping_blocks_preview(self):
        self._upload_and_configure_wide_sample()
        response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': f'structure:{self.density_field.name}',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Нельзя сопоставлять несколько колонок')
        self.assertNotContains(response, 'Черновик')

    def test_mapped_review_and_apply_flow(self):
        self._upload_and_configure_wide_sample()

        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'material.description',
                'parse_4': 'text',
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'Черновик')
        self.assertContains(preview, 'Записать')
        self.assertContains(preview, 'import-wizard-nav')
        self.assertContains(preview, 'value="review_resolve_manual"')
        self.assertNotContains(preview, 'Построчно (точнее)')
        self.assertEqual(preview.context['wizard_forward_label'], 'Записать')
        self.assertFalse(Material.objects.filter(name='Стеклоткань демо').exists())

        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'review_marker': '1',
                'include_struct_0_0': '1',
                'include_1_0': '1',
            },
        )
        self.assertEqual(apply_response.status_code, 302)
        material = Material.objects.get(name='Стеклоткань демо', home_workspace=self.workspace)
        self.assertIsNotNone(material.struct_props_id)
        row = get_row(self.structure_type, material.struct_props_id)
        self.assertEqual(str(row[self.density_field.name]).rstrip('0').rstrip('.'), '260')
        self.assertTrue(material.tags.filter(name='марка::Е-стекло').exists())

    def test_review_apply_persists_edited_material_name(self):
        self._upload_and_configure_wide_sample()

        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(preview.status_code, 200)

        edited_name = 'Стеклоткань переименована'
        post_data = {
            'action': 'review_resolve_manual',
            'review_marker': '1',
            'fix_material_0_name': edited_name,
        }
        for item in preview.context['review_editable_fields']:
            input_name = item.get('input_name')
            if not input_name or input_name == 'fix_material_0_name':
                continue
            post_data[input_name] = item.get('fix_value') or ''
            skip_name = item.get('skip_name')
            if skip_name and item.get('skip_checked'):
                post_data[skip_name] = '1'

        apply_response = self.client.post(reverse('materials:import'), post_data)
        self.assertEqual(apply_response.status_code, 302)
        self.assertTrue(
            Material.objects.filter(name=edited_name, home_workspace=self.workspace).exists()
        )
        self.assertFalse(
            Material.objects.filter(name='Стеклоткань демо', home_workspace=self.workspace).exists()
        )

    def test_default_tags_applied_to_imported_materials(self):
        self._upload_and_configure_wide_sample()
        mapping = self.client.get(reverse('materials:import'), {'step': 'mapping'})
        self.assertEqual(mapping.status_code, 200)
        self.assertContains(mapping, 'Теги для всех материалов')

        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'import_default_tags': 'партия::тест, demo',
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(preview.status_code, 200)
        config = get_import_config(self.client.session)
        self.assertEqual(config.get('default_tags'), 'партия::тест, demo')
        drafts = drafts_from_session(config.get('draft'))
        self.assertTrue(drafts)
        self.assertIn('партия::тест', drafts[0].tags)
        self.assertIn('demo', drafts[0].tags)
        self.assertIn('марка::', drafts[0].tags)

        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'review_marker': '1',
                'include_struct_0_0': '1',
            },
        )
        self.assertEqual(apply_response.status_code, 302)
        material = Material.objects.get(name='Стеклоткань демо', home_workspace=self.workspace)
        names = set(material.tags.values_list('name', flat=True))
        self.assertIn('партия::тест', names)
        self.assertIn('demo', names)
        self.assertTrue(any(n.startswith('марка::') for n in names))

    def test_default_tag_colors_saved_and_applied(self):
        self._upload_and_configure_wide_sample()
        mapping = self.client.get(reverse('materials:import'), {'step': 'mapping'})
        self.assertEqual(mapping.status_code, 200)
        self.assertContains(mapping, 'name="import_default_tags_colors"')
        self.assertContains(mapping, 'data-allow-tag-colors="1"')
        self.assertContains(mapping, 'import-default-tags-panel')
        # Блок тегов идёт после конструктора маппинга.
        body = mapping.content.decode('utf-8')
        self.assertLess(
            body.index('import-map-constructor'),
            body.index('import-default-tags-panel'),
        )

        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'import_default_tags': 'партия::цвет, demo-color',
                'import_default_tags_colors': (
                    '{"партия::цвет":"#AABBCC","demo-color":"#112233"}'
                ),
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(preview.status_code, 200)
        config = get_import_config(self.client.session)
        self.assertEqual(
            config.get('default_tag_colors'),
            {'партия::цвет': '#AABBCC', 'demo-color': '#112233'},
        )

        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'review_marker': '1',
                'include_struct_0_0': '1',
            },
        )
        self.assertEqual(apply_response.status_code, 302)
        from apps.core.models import Tag

        scoped = Tag.objects.get(workspace=self.workspace, name='партия::цвет')
        plain = Tag.objects.get(workspace=self.workspace, name='demo-color')
        self.assertEqual((scoped.color or '').upper(), '#AABBCC')
        self.assertEqual((plain.color or '').upper(), '#112233')

    def test_save_template_validation_keeps_default_tags(self):
        """При ошибке «пустое имя шаблона» теги из формы остаются на маппинге."""
        self._upload_and_configure_wide_sample()
        response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'save_template',
                'template_name': '',
                'import_default_tags': 'партия::keep, demo-keep',
                'import_default_tags_colors': '{"demo-keep":"#AABBCC"}',
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['step'], 'mapping')
        config = get_import_config(self.client.session)
        self.assertEqual(config.get('default_tags'), 'партия::keep, demo-keep')
        self.assertEqual(
            config.get('default_tag_colors'),
            {'demo-keep': '#AABBCC'},
        )
        self.assertContains(response, 'партия::keep')
        self.assertContains(response, 'demo-keep')

    def test_review_resolve_manual_persists_partial_fixes(self):
        """Успешные правки остаются после ошибки в другом поле (не откатываются)."""
        self._upload_and_configure_wide_sample()
        session = self.client.session
        draft = DraftMaterial(
            source_row=2,
            name='Ткань Fix',
            code='fix-1',
            description='',
            tags='',
            action='create',
            struct_type_id=str(self.structure_type.pk),
            structure_values=[
                DraftStructureValue(
                    field_name=self.density_field.name,
                    field_label='Плотность',
                    column_label='Плотность',
                    raw='плохо',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                ),
            ],
            properties=[
                DraftProperty(
                    property_name=self.density.name,
                    property_id=str(self.density.pk),
                    property_label='Плотность пов',
                    column_label='Плотн пов',
                    raw='ерунда',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                ),
            ],
        )
        set_import_config(session, draft=drafts_to_session([draft]))
        session.save()

        response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'fix_struct_0_0': '260',
                'fix_prop_0_0': 'аааа дичь',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['step'], 'review')
        self.assertEqual(response.context['unrecognized_count'], 1)

        saved = drafts_from_session(get_import_config(self.client.session).get('draft'))
        self.assertEqual(saved[0].structure_values[0].recognition, RECOGNITION_MANUAL)
        self.assertEqual(saved[0].structure_values[0].value, '260')
        self.assertEqual(saved[0].properties[0].recognition, RECOGNITION_UNRECOGNIZED)

        # Исправленная ячейка больше не в списке нераспознанных.
        names = {item['input_name'] for item in response.context['unrecognized_fields']}
        self.assertNotIn('fix_struct_0_0', names)
        self.assertIn('fix_prop_0_0', names)

    def test_review_warns_on_name_collision_and_skip(self):
        Material.objects.create(
            home_workspace=self.workspace,
            code='EXIST-1',
            name='Стеклоткань демо',
        )
        self._upload_and_configure_wide_sample()
        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'Совпадения по названию')
        self.assertContains(preview, 'name="duplicate_name_policy"')
        self.assertContains(preview, 'import-collision-panel')
        self.assertContains(preview, 'import-unrecognized-panel')
        self.assertGreater(preview.context['name_collision_count'], 0)

        before = Material.objects.filter(home_workspace=self.workspace).count()
        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'review_marker': '1',
                'duplicate_name_policy': 'skip',
                'include_struct_0_0': '1',
            },
        )
        self.assertEqual(apply_response.status_code, 302)
        # Дубликат «Стеклоткань демо» пропущен; «Углеткань демо» создана.
        self.assertEqual(
            Material.objects.filter(home_workspace=self.workspace).count(),
            before + 1,
        )
        self.assertEqual(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Стеклоткань демо',
            ).count(),
            1,
        )
        self.assertTrue(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Углеткань демо',
            ).exists()
        )

    def test_review_prefix_creates_new_material_on_name_collision(self):
        Material.objects.create(
            home_workspace=self.workspace,
            code='EXIST-1',
            name='Стеклоткань демо',
        )
        self._upload_and_configure_wide_sample()
        self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'review_marker': '1',
                'duplicate_name_policy': 'prefix',
                'duplicate_name_prefix': 'импорт-',
                'include_struct_0_0': '1',
            },
        )
        self.assertEqual(apply_response.status_code, 302)
        self.assertTrue(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='импорт-Стеклоткань демо',
            ).exists()
        )
        self.assertEqual(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Стеклоткань демо',
            ).count(),
            1,
        )

    def test_review_postfix_creates_new_material_on_name_collision(self):
        Material.objects.create(
            home_workspace=self.workspace,
            code='EXIST-1',
            name='Стеклоткань демо',
        )
        self._upload_and_configure_wide_sample()
        self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_resolve_manual',
                'review_marker': '1',
                'duplicate_name_policy': 'postfix',
                'duplicate_name_postfix': '-импорт',
                'include_struct_0_0': '1',
            },
        )
        self.assertEqual(apply_response.status_code, 302)
        self.assertTrue(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Стеклоткань демо-импорт',
            ).exists()
        )
        self.assertEqual(
            Material.objects.filter(
                home_workspace=self.workspace,
                name='Стеклоткань демо',
            ).count(),
            1,
        )

    def test_review_validation_errors_block_apply(self):
        """При ошибках валидации запись запрещена; остаётся путь к сопоставлению."""
        self._upload_and_configure_wide_sample()
        preview = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_preview',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'skip',
                'parse_4': 'auto',
            },
        )
        self.assertEqual(preview.status_code, 200)

        # Портим имя в черновике сессии → dry-run на review даёт жёсткую ошибку валидации
        session = self.client.session
        config = get_import_config(session)
        drafts = drafts_from_session(config.get('draft'))
        self.assertTrue(drafts)
        name_max = Material._meta.get_field('name').max_length
        drafts[0].name = 'x' * (name_max + 10)
        set_import_config(session, draft=drafts_to_session(drafts))
        session.save()

        review = self.client.get(reverse('materials:import') + '?step=review')
        self.assertEqual(review.status_code, 200)
        self.assertContains(review, 'import-validation-report')
        self.assertContains(review, 'запись запрещена')
        self.assertContains(review, 'Исправить сопоставление')
        self.assertNotContains(review, 'value="review_resolve_manual"')
        self.assertNotContains(review, 'value="review_iterate_start"')
        self.assertNotContains(review, 'value="review_recheck"')

        back = self.client.get(reverse('materials:import') + '?step=mapping')
        self.assertEqual(back.status_code, 200)
        self.assertContains(back, 'import-map-constructor')

        blocked = self.client.post(
            reverse('materials:import'),
            {'action': 'review_resolve_manual', 'review_marker': '1'},
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, 'запись запрещена')
        self.assertFalse(Material.objects.filter(name__startswith='x' * 20).exists())

    def test_iterate_starts_from_mapping(self):
        self._upload_and_configure_wide_sample()
        mapping_page = self.client.get(reverse('materials:import') + '?step=mapping')
        self.assertEqual(mapping_page.status_code, 200)
        self.assertContains(mapping_page, 'Вперёд')
        self.assertContains(mapping_page, 'Построчно')
        self.assertContains(mapping_page, '← Назад')
        self.assertContains(mapping_page, 'import-wizard-nav')

        start = self.client.post(
            reverse('materials:import'),
            {
                'action': 'map_iterate',
                'match_policy': MATCH_BY_NAME,
                'map_0': 'material.name',
                'parse_0': 'auto',
                'map_1': 'material.tags',
                'parse_1': 'auto',
                'map_2': f'structure:{self.density_field.name}',
                'parse_2': 'auto',
                'map_3': 'skip',
                'parse_3': 'auto',
                'map_4': 'material.description',
                'parse_4': 'text',
            },
        )
        self.assertEqual(start.status_code, 302)
        self.assertIn('step=iterate', start.url)

        iterate_page = self.client.get(reverse('materials:import') + '?step=iterate')
        self.assertEqual(iterate_page.status_code, 200)
        self.assertContains(iterate_page, 'Вперёд → записать')
        self.assertContains(iterate_page, '← Назад')
        self.assertContains(iterate_page, 'Стеклоткань демо')

        apply_one = self.client.post(
            reverse('materials:import'),
            {
                'action': 'iterate_apply',
                'include_struct_0': '1',
            },
        )
        self.assertEqual(apply_one.status_code, 302)
        self.assertTrue(
            Material.objects.filter(name='Стеклоткань демо', home_workspace=self.workspace).exists()
        )
        self.assertFalse(
            Material.objects.filter(name='Углеткань демо', home_workspace=self.workspace).exists()
        )

        finish = self.client.post(
            reverse('materials:import'),
            {'action': 'iterate_finish'},
        )
        self.assertEqual(finish.status_code, 302)
        self.assertEqual(finish.url, reverse('materials:list'))
        self.assertEqual(
            Material.objects.filter(
                name__in=['Стеклоткань демо', 'Углеткань демо'],
                home_workspace=self.workspace,
            ).count(),
            1,
        )

    def test_example_download(self):
        response = self.client.get(reverse('materials:import_example'))
        self.assertEqual(response.status_code, 200)


def _draft(*, source_row: int, action: str, name: str) -> DraftMaterial:
    return DraftMaterial(
        source_row=source_row,
        name=name,
        code='',
        description='',
        tags='',
        action=action,
    )


class MaterialImportReviewPostTests(TestCase):
    def test_apply_review_post_keeps_includes_when_not_posted(self):
        """Свёрнутый черновик не шлёт include_* — флаги из сессии должны сохраниться."""
        draft = DraftMaterial(
            source_row=2,
            name='Fabric',
            code='F-1',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Плотность',
                    column_label='Плотность',
                    raw='100',
                    value_kind='scalar',
                    value='100',
                    value_b='',
                    confidence='ok',
                    note='число',
                    include=True,
                )
            ],
            properties=[
                DraftProperty(
                    property_name='note',
                    property_id='1',
                    column_label='Примечание',
                    raw='x',
                    value_kind='scalar',
                    value='x',
                    value_b='',
                    confidence='ok',
                    note='текст',
                    include=True,
                )
            ],
        )
        updated = apply_review_post([draft], {'review_marker': '1'})
        self.assertTrue(updated[0].structure_values[0].include)
        self.assertTrue(updated[0].properties[0].include)
        self.assertEqual(updated[0].action, 'create')


class MaterialImportNameCollisionTests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()

    def test_name_collisions_skip_and_prefix(self):
        Material.objects.create(
            home_workspace=self.workspace,
            code='EXIST',
            name='Alpha',
        )
        drafts = [
            DraftMaterial(
                source_row=2, name='Alpha', code='a1', description='', tags='', action='create',
            ),
            DraftMaterial(
                source_row=3, name='Beta', code='b1', description='', tags='', action='create',
            ),
        ]
        collisions = name_collisions_for_drafts(self.workspace, drafts)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['name'], 'Alpha')

        skipped = apply_duplicate_name_policy(
            [
                DraftMaterial(
                    source_row=2, name='Alpha', code='a1', description='', tags='', action='create',
                ),
                DraftMaterial(
                    source_row=3, name='Beta', code='b1', description='', tags='', action='create',
                ),
            ],
            collisions,
            mode='skip',
        )
        self.assertEqual(skipped[0].action, 'skip')
        self.assertEqual(skipped[1].action, 'create')

        prefixed = apply_duplicate_name_policy(
            [
                DraftMaterial(
                    source_row=2, name='Alpha', code='a1', description='', tags='', action='create',
                ),
                DraftMaterial(
                    source_row=3, name='Beta', code='b1', description='', tags='', action='create',
                ),
            ],
            collisions,
            mode='prefix',
            prefix='imp-',
        )
        self.assertEqual(prefixed[0].action, 'create')
        self.assertEqual(prefixed[0].name, 'imp-Alpha')
        self.assertIsNone(prefixed[0].existing_pk)
        self.assertEqual(prefixed[1].name, 'Beta')

        postfixed = apply_duplicate_name_policy(
            [
                DraftMaterial(
                    source_row=2, name='Alpha', code='a1', description='', tags='', action='create',
                ),
                DraftMaterial(
                    source_row=3, name='Beta', code='b1', description='', tags='', action='create',
                ),
            ],
            collisions,
            mode='postfix',
            postfix='-imp',
        )
        self.assertEqual(postfixed[0].action, 'create')
        self.assertEqual(postfixed[0].name, 'Alpha-imp')
        self.assertIsNone(postfixed[0].existing_pk)
        self.assertEqual(postfixed[1].name, 'Beta')

        with self.assertRaises(ValueError):
            apply_duplicate_name_policy(
                drafts,
                collisions,
                mode='prefix',
                prefix='',
            )

        with self.assertRaises(ValueError):
            apply_duplicate_name_policy(
                drafts,
                collisions,
                mode='postfix',
                postfix='',
            )

    def test_merge_default_tags_into_drafts(self):
        drafts = [
            DraftMaterial(
                source_row=2,
                name='A',
                code='a',
                description='',
                tags='марка::EC9',
                action='create',
            ),
            DraftMaterial(
                source_row=3,
                name='B',
                code='b',
                description='',
                tags='',
                action='skip',
            ),
        ]
        merge_default_tags_into_drafts(drafts, 'партия::1, demo')
        self.assertIn('партия::1', drafts[0].tags)
        self.assertIn('demo', drafts[0].tags)
        self.assertIn('марка::EC9', drafts[0].tags)
        self.assertEqual(drafts[1].tags, '')

    def test_apply_review_post_honours_include_checkboxes(self):
        draft = DraftMaterial(
            source_row=2,
            name='Fabric',
            code='F-1',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Плотность',
                    column_label='Плотность',
                    raw='100',
                    value_kind='scalar',
                    value='100',
                    value_b='',
                    confidence='ok',
                    note='число',
                    include=True,
                )
            ],
            properties=[],
        )
        updated = apply_review_post(
            [draft],
            {'review_marker': '1'},  # include_struct_0_0 отсутствует → False
        )
        # без include_* в POST — не трогаем
        self.assertTrue(updated[0].structure_values[0].include)

        updated = apply_review_post(
            [draft],
            {'review_marker': '1', 'include_struct_0_0': '1'},
        )
        self.assertTrue(updated[0].structure_values[0].include)

        draft.structure_values[0].include = True
        updated = apply_review_post(
            [draft],
            {'review_marker': '1', 'include_0_0': '1'},  # только property-ключ, struct нет
        )
        self.assertFalse(updated[0].structure_values[0].include)


class MaterialImportIterateUnitTests(TestCase):
    def test_next_active_index_skips_marked_rows(self):
        drafts = [
            _draft(source_row=2, action='create', name='a'),
            _draft(source_row=3, action='skip', name='b'),
            _draft(source_row=4, action='update', name='c'),
        ]
        self.assertEqual(next_active_index(drafts, start_at=0), 0)
        self.assertEqual(next_active_index(drafts, start_at=1), 2)
        self.assertIsNone(next_active_index(drafts, start_at=3))

    def test_start_iterate_sets_first_active(self):
        class FakeSession(dict):
            modified = False

        session = FakeSession()
        drafts = [
            _draft(source_row=2, action='skip', name='a'),
            _draft(source_row=3, action='create', name='b'),
        ]
        index = start_iterate(session, drafts)
        self.assertEqual(index, 1)
        self.assertTrue(session.get('material_import_iterate_active'))
        self.assertEqual(session.get('material_import_iterate_index'), 1)
        self.assertEqual(session.get('material_import_iterate_total'), 1)
        self.assertTrue(session.modified)

    def test_iterate_progress_keeps_initial_total(self):
        class FakeSession(dict):
            modified = False

        session = FakeSession()
        drafts = [
            _draft(source_row=2, action='create', name='a'),
            _draft(source_row=3, action='create', name='b'),
            _draft(source_row=4, action='create', name='c'),
        ]
        start_iterate(session, drafts)
        drafts[0].action = 'skip'
        position, total, done, percent = iterate_progress(session, drafts)
        self.assertEqual(total, 3)
        self.assertEqual(done, 1)
        self.assertEqual(position, 2)
        self.assertEqual(percent, 33)

    def test_apply_iterate_row_post_updates_name_and_code(self):
        draft = _draft(source_row=2, action='create', name='old')
        draft.code = 'OLD'
        updated = apply_iterate_row_post(draft, {'name': '  new name  ', 'code': '  NEW-1  '})
        self.assertEqual(updated.name, 'new name')
        self.assertEqual(updated.code, 'NEW-1')


class MaterialImportUnrecognizedFieldTests(TestCase):
    def setUp(self):
        self.workspace = ensure_legacy_workspace()
        self.structure_type, self.density_field = create_import_structure_type(
            code='unrecognized_fabric',
            table_name='structures_unrecognized_fabric',
        )
        group = PropertyGroup.objects.create(name='Unrecognized import group', sort_order=1)
        self.breaking_prop = Property.objects.create(
            name='breaking_load',
            display_name='Разрывная',
            data_type='number',
            group=group,
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def test_needs_manual_recognition_for_dual_slash_and_annotation(self):
        dual_raw = '160(+10)/100(±10)'
        dual_parsed = parse_property_cell(dual_raw)
        self.assertTrue(needs_manual_recognition(dual_raw, dual_parsed, expects_number=True))

        annotation_raw = '(на 1дм) основа/уток'
        annotation_parsed = parse_property_cell(annotation_raw)
        self.assertTrue(needs_manual_recognition(annotation_raw, annotation_parsed, expects_number=True))

        clean_parsed = parse_property_cell('260')
        self.assertFalse(needs_manual_recognition('260', clean_parsed, expects_number=True))

        strip_parsed = parse_property_cell('4050/50мм')
        self.assertFalse(needs_manual_recognition('4050/50мм', strip_parsed, expects_number=True))

        # Без единиц это основа/уток, а не «на полоску»
        dual_bare = parse_property_cell('900/2200')
        self.assertTrue(needs_manual_recognition('900/2200', dual_bare, expects_number=True))

    def test_text_parse_mode_on_number_field_uses_auto_parse(self):
        """Для number-поля режим «Текст» в staging переключается на авто — «30±3» не ломается."""
        table = WideTable(
            sheet_name='CSV',
            header_row=1,
            columns=[
                WideColumn(index=0, label='Наименование'),
                WideColumn(index=1, label='Плотность'),
            ],
            rows=[{0: 'Ткань A', 1: '30±3'}],
            preview_rows=[{0: 'Ткань A', 1: '30±3'}],
        )
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': f'property:{self.breaking_prop.pk}', 'parse': 'text'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        prop = drafts[0].properties[0]
        self.assertEqual(prop.recognition, RECOGNITION_OK)
        self.assertEqual(prop.value, '30')
        self.assertEqual(prop.value_b, '3')
        self.assertEqual(prop.property_label, 'Разрывная')

    def test_staging_combines_bound_column_as_tolerance_or_range(self):
        table = WideTable(
            sheet_name='CSV',
            header_row=1,
            columns=[
                WideColumn(index=0, label='Наименование'),
                WideColumn(index=1, label='Плотность'),
                WideColumn(index=2, label='Погрешность'),
                WideColumn(index=3, label='До'),
            ],
            rows=[
                {0: 'Ткань A', 1: '30', 2: '3', 3: '40'},
            ],
            preview_rows=[{0: 'Ткань A', 1: '30', 2: '3', 3: '40'}],
        )
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {
                'target': f'property:{self.breaking_prop.pk}',
                'parse': 'auto',
                'bound_column': 2,
                'bound_kind': 'tolerance',
            },
            '2': {'target': TARGET_SKIP, 'parse': 'auto'},
            '3': {'target': TARGET_SKIP, 'parse': 'auto'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        prop = drafts[0].properties[0]
        self.assertEqual(prop.value_kind, 'tolerance')
        self.assertEqual(prop.value, '30')
        self.assertEqual(prop.value_b, '3')

        mapping['1']['bound_column'] = 3
        mapping['1']['bound_kind'] = 'range'
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        prop = drafts[0].properties[0]
        self.assertEqual(prop.value_kind, 'range')
        self.assertEqual(prop.value, '30')
        self.assertEqual(prop.value_b, '40')

    def test_tolerance_slash_variants_parse(self):
        for raw in ('30±3', '30 +/- 3', '30+-3'):
            parsed = parse_property_cell(raw)
            self.assertEqual(parsed['value_kind'], 'tolerance', raw)
            self.assertEqual(parsed['value'], '30', raw)
            self.assertEqual(parsed['value_b'], '3', raw)

    def test_warp_weft_with_units_needs_manual_recognition(self):
        raw = '900/2200 Н/50мм'
        parsed = parse_property_cell(raw)
        self.assertTrue(needs_manual_recognition(raw, parsed, expects_number=True))
        strip = parse_property_cell('4050/50мм')
        self.assertFalse(needs_manual_recognition('4050/50мм', strip, expects_number=True))
        self.assertEqual(strip['value'], '4050')

    def test_validate_blocks_unresolved_unrecognized_fields(self):
        from apps.materials.imports.validate import validate_drafts
        from apps.materials.imports.report import ImportReport

        draft = DraftMaterial(
            source_row=3,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name=self.density_field.name,
                    field_label='Плотность пов',
                    column_label='Плотность',
                    raw='900/2200 Н/50мм',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано автоматически',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                )
            ],
        )
        dry_report = ImportReport(dry_run=True)
        validate_drafts(
            [draft],
            structure_type=self.structure_type,
            workspace=self.workspace,
            report=dry_report,
            dry_run=True,
        )
        self.assertTrue(dry_report.ok)

        apply_report = ImportReport(dry_run=False)
        validate_drafts(
            [draft],
            structure_type=self.structure_type,
            workspace=self.workspace,
            report=apply_report,
            dry_run=False,
        )
        self.assertFalse(apply_report.ok)
        self.assertTrue(any('не распознано' in err.message for err in apply_report.errors))

    def test_build_staging_marks_unrecognized_numeric_cells(self):
        table = WideTable(
            sheet_name='CSV',
            header_row=1,
            columns=[
                WideColumn(index=0, label='Наименование'),
                WideColumn(index=1, label='Разрывная основа/уток'),
            ],
            rows=[{0: 'Ткань A', 1: '160(+10)/100(±10)'}],
            preview_rows=[{0: 'Ткань A', 1: '160(+10)/100(±10)'}],
        )
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': f'structure:{self.density_field.name}', 'parse': 'auto'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        self.assertEqual(len(drafts), 1)
        struct = drafts[0].structure_values[0]
        self.assertEqual(struct.recognition, RECOGNITION_UNRECOGNIZED)
        self.assertEqual(struct.raw, '160(+10)/100(±10)')
        self.assertTrue(has_unresolved_unrecognized(drafts))
        self.assertEqual(len(iter_unrecognized_fields(drafts)), 1)

    def test_apply_unrecognized_ignore_all_clears_values(self):
        draft = DraftMaterial(
            source_row=2,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Плотность пов',
                    column_label='Разрывная',
                    raw='160(+10)/100(±10)',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано автоматически',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                )
            ],
        )
        updated = apply_unrecognized_ignore_all([draft])[0]
        struct = updated.structure_values[0]
        self.assertEqual(struct.recognition, RECOGNITION_IGNORED)
        self.assertFalse(struct.include)
        self.assertFalse(has_unresolved_unrecognized([updated]))

    def test_apply_unrecognized_manual_fixes_parses_values(self):
        draft = DraftMaterial(
            source_row=2,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            properties=[
                DraftProperty(
                    property_name='Разрывная',
                    property_id=str(self.breaking_prop.pk),
                    column_label='Разрывная основа/уток',
                    raw='160(+10)/100(±10)',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано автоматически',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                )
            ],
        )
        updated, errors = apply_unrecognized_manual_fixes(
            [draft],
            {'fix_prop_0_0': '160 ± 10'},
        )
        self.assertEqual(errors, [])
        prop = updated[0].properties[0]
        self.assertEqual(prop.recognition, RECOGNITION_MANUAL)
        self.assertEqual(prop.value, '160')
        self.assertEqual(prop.value_b, '10')
        self.assertFalse(has_unresolved_unrecognized(updated))

    def test_apply_unrecognized_manual_fixes_skips_individual_field(self):
        draft = DraftMaterial(
            source_row=2,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            properties=[
                DraftProperty(
                    property_name='Разрывная',
                    property_id=str(self.breaking_prop.pk),
                    column_label='Разрывная основа/уток',
                    raw='160(+10)/100(±10)',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано автоматически',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                )
            ],
        )
        updated, errors = apply_unrecognized_manual_fixes(
            [draft],
            {'skip_fix_prop_0_0': '1'},
        )
        self.assertEqual(errors, [])
        prop = updated[0].properties[0]
        self.assertEqual(prop.recognition, RECOGNITION_IGNORED)
        self.assertFalse(prop.include)

    def test_iter_unrecognized_fields_prefills_raw_value(self):
        draft = DraftMaterial(
            source_row=18,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Разрывная нагрузка',
                    column_label='Разрывная основа',
                    raw='900/2200 Н/50мм',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано автоматически',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                )
            ],
        )
        items = iter_unrecognized_fields([draft])
        self.assertEqual(items[0]['fix_value'], '900/2200 Н/50мм')
        items_after_post = iter_unrecognized_fields(
            [draft],
            post={'fix_struct_0_0': '900'},
        )
        self.assertEqual(items_after_post[0]['fix_value'], '900')

    def test_build_review_fix_grid_marks_unrecognized_cells(self):
        draft = DraftMaterial(
            source_row=18,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Плотность',
                    column_label='Плотность пов',
                    raw='300',
                    value_kind='scalar',
                    value='300',
                    value_b='',
                    confidence='ok',
                    note='',
                    include=True,
                    recognition=RECOGNITION_OK,
                ),
                DraftStructureValue(
                    field_name='breaking_load',
                    field_label='Разрывная нагрузка',
                    column_label='Разрывная основа',
                    raw='900/2200 Н/50мм',
                    value_kind='scalar',
                    value='',
                    value_b='',
                    confidence='uncertain',
                    note='не распознано',
                    include=True,
                    recognition=RECOGNITION_UNRECOGNIZED,
                ),
            ],
            properties=[
                DraftProperty(
                    property_name='note',
                    property_id='prop-1',
                    property_label='Заметка',
                    column_label='Примечание',
                    raw='ok',
                    value_kind='scalar',
                    value='ok',
                    value_b='',
                    confidence='ok',
                    note='',
                    include=True,
                    recognition=RECOGNITION_OK,
                ),
            ],
        )
        ok_only = DraftMaterial(
            source_row=19,
            name='Ткань B',
            code='fab-b',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Плотность',
                    column_label='Плотность пов',
                    raw='200',
                    value_kind='scalar',
                    value='200',
                    value_b='',
                    confidence='ok',
                    note='',
                    include=True,
                    recognition=RECOGNITION_OK,
                ),
            ],
        )
        grid = build_review_fix_grid([draft, ok_only])
        self.assertEqual(grid['unrecognized_count'], 1)
        self.assertEqual(len(grid['rows']), 2)
        self.assertEqual(grid['rows'][0]['source_row'], 18)
        self.assertEqual(grid['rows'][1]['source_row'], 19)
        keys = [col['key'] for col in grid['columns']]
        self.assertEqual(
            keys,
            ['material:code', 'struct:areal_density', 'struct:breaking_load', 'prop:prop-1'],
        )
        self.assertEqual(
            [col['letter'] for col in grid['columns']],
            ['B', 'C', 'D', 'E'],
        )
        bad = grid['rows'][0]['cells']['struct:breaking_load']
        self.assertTrue(bad['is_unrecognized'])
        self.assertEqual(bad['display'], '900/2200 Н/50мм')
        self.assertEqual(bad['input_name'], 'fix_struct_0_1')
        good = grid['rows'][0]['cells']['struct:areal_density']
        self.assertFalse(good['is_unrecognized'])
        self.assertTrue(good['is_editable'])
        self.assertEqual(good['display'], '300')
        self.assertEqual(good['input_name'], 'fix_struct_0_0')
        self.assertEqual(good['fix_value'], '300')
        self.assertEqual(grid['rows'][0]['cells']['material:code']['display'], 'fab-a')
        self.assertEqual(grid['rows'][0]['cells']['material:code']['input_name'], 'fix_material_0_code')
        self.assertEqual(grid['rows'][0]['name_cell']['input_name'], 'fix_material_0_name')
        self.assertEqual(grid['rows'][1]['cells']['struct:areal_density']['display'], '200')
        self.assertEqual(len(grid['rows'][0]['cell_list']), 4)
        self.assertEqual(grid['rows'][0]['cell_list'][2]['letter'], 'D')

    def test_apply_manual_fixes_updates_ok_structure_and_name(self):
        draft = DraftMaterial(
            source_row=18,
            name='Ткань A',
            code='fab-a',
            description='',
            tags='',
            action='create',
            structure_values=[
                DraftStructureValue(
                    field_name='areal_density',
                    field_label='Плотность',
                    column_label='Плотность пов',
                    raw='300',
                    value_kind='scalar',
                    value='300',
                    value_b='',
                    confidence='ok',
                    note='',
                    include=True,
                    recognition=RECOGNITION_OK,
                ),
            ],
            properties=[],
        )
        updated, errors = apply_unrecognized_manual_fixes(
            [draft],
            {
                'fix_material_0_name': 'Ткань A new',
                'fix_material_0_code': 'fab-a2',
                'fix_struct_0_0': '350',
            },
        )
        self.assertEqual(errors, [])
        self.assertEqual(updated[0].name, 'Ткань A new')
        self.assertEqual(updated[0].code, 'fab-a2')
        self.assertEqual(updated[0].structure_values[0].value, '350')
        self.assertEqual(updated[0].structure_values[0].recognition, RECOGNITION_MANUAL)

    def test_apply_manual_fixes_regenerates_code_when_name_changes(self):
        draft = DraftMaterial(
            source_row=3,
            name='Ткань A',
            code='tkan-a',
            description='',
            tags='',
            action='create',
            structure_values=[],
            properties=[],
        )
        updated, errors = apply_unrecognized_manual_fixes(
            [draft],
            {'fix_material_0_name': 'Ткань B'},
        )
        self.assertEqual(errors, [])
        self.assertEqual(updated[0].name, 'Ткань B')
        self.assertNotEqual(updated[0].code, 'tkan-a')
        self.assertTrue(updated[0].code)

class MaterialImportDebugUndoTests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        self.structure_type, _ = create_import_structure_type(
            code='undo_fabric',
            table_name='structures_undo_fabric',
        )

    def tearDown(self):
        SQLExecutor.drop_table(self.structure_type)

    def test_undo_deletes_last_import_batch(self):
        table = load_wide_table(
            Path(__file__).resolve().parent / 'fixtures' / 'import_examples' / 'materials_wide_sample.csv',
            header_row=1,
        )
        mapping = {
            '0': {'target': 'material.name', 'parse': 'auto'},
            '1': {'target': 'material.tags', 'parse': 'auto'},
        }
        drafts = build_staging_draft(
            table,
            mapping,
            workspace=self.workspace,
            match_policy=MATCH_BY_NAME,
            structure_type_id=str(self.structure_type.pk),
        )
        report = MaterialImporter(workspace=self.workspace).import_drafts(
            drafts[:1],
            structure_type=self.structure_type,
        )
        self.assertTrue(report.ok)
        material = Material.objects.get(home_workspace=self.workspace)
        self.assertIsNotNone(material.pk)

        from django.contrib.sessions.backends.db import SessionStore

        session = SessionStore()
        store_last_import_debug_batch(
            session,
            workspace=self.workspace,
            material_ids=report.affected_material_ids,
        )
        result = undo_last_import_debug_batch(session, workspace=self.workspace)
        self.assertTrue(result.ok)
        self.assertEqual(result.deleted_materials, 1)
        self.assertFalse(Material.objects.filter(home_workspace=self.workspace).exists())
        self.assertIsNone(get_last_import_debug_batch(session))


class MaterialImportCommandTests(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self.workspace = ensure_legacy_workspace()
        group = PropertyGroup.objects.create(name='Cmd import group', sort_order=1)
        Property.objects.create(name='density', display_name='Density', data_type='number', group=group)
        Property.objects.create(
            name='tensile_strength',
            display_name='Tensile strength',
            data_type='number',
            group=group,
        )

    def test_management_command_dry_run(self):
        sample = Path(__file__).resolve().parent / 'fixtures' / 'import_examples' / 'materials_sample.csv'
        out = StringIO()
        call_command(
            'import_materials',
            str(sample),
            workspace=self.workspace.slug,
            dry_run=True,
            stdout=out,
        )
        self.assertIn('Dry-run', out.getvalue())

    def test_management_command_errors_on_invalid_workspace(self):
        sample = Path(__file__).resolve().parent / 'fixtures' / 'import_examples' / 'materials_sample.csv'
        with self.assertRaises(CommandError):
            call_command('import_materials', str(sample), workspace='missing-workspace-slug')
