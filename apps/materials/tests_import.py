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
from apps.materials.imports.mapping import (
    TARGET_CODE,
    TARGET_NAME,
    TARGET_SKIP,
    TARGET_STRUCTURE_PREFIX,
    find_duplicate_mapping_targets,
    mapping_catalog_groups,
    mapping_choices,
    missing_required_targets,
    required_import_targets,
    suggest_target,
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
    MATCH_BY_NAME,
    DraftMaterial,
    DraftProperty,
    DraftStructureValue,
    apply_review_post,
    build_staging_draft,
    draft_to_import_rows,
)
from apps.materials.imports.value_parse import parse_property_cell
from apps.materials.imports.wide import detect_header_layout, load_wide_table
from apps.materials.models import Material, MaterialProperty
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

    def test_created_materials_get_import_source_note(self):
        report = MaterialImporter(
            workspace=self.workspace,
            source_filename='Сводная по материалам.xlsx',
        ).import_file(self._sample_csv())
        self.assertTrue(report.ok)
        with_note = Material.objects.filter(
            home_workspace=self.workspace,
            description__contains='Создано из файла импорта: Сводная по материалам.xlsx',
        )
        self.assertEqual(with_note.count(), report.materials_created)
        material = with_note.first()
        self.assertEqual(material.import_source_filename, 'Сводная по материалам.xlsx')
        self.assertNotIn('Создано из файла импорта', material.description_display)

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
        self.assertContains(response, 'Загрузить и продолжить')

    def test_sidebar_shows_import_link(self):
        response = self.client.get(reverse('materials:list'))
        self.assertContains(response, reverse('materials:import'))
        self.assertNotContains(response, 'btn btn-outline-primary btn-sm">Импорт')

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

    def test_mapping_constructor_renders(self):
        response = self._upload_and_configure_wide_sample()
        self.assertContains(response, 'import-map-constructor')
        self.assertContains(response, 'import-map-catalog')
        self.assertContains(response, 'Поля для подстановки')
        self.assertContains(response, 'Колонки файла')
        self.assertContains(response, 'Куда писать')
        self.assertContains(response, 'import-map-expr-slot')
        self.assertContains(response, 'import-map-panel')
        self.assertContains(response, 'data-drop-slot')
        self.assertContains(response, 'draggable="true"')
        self.assertContains(response, 'import_mapping_constructor.js')
        self.assertContains(response, 'name="map_0"')
        self.assertContains(response, 'name="parse_0"')
        self.assertContains(response, 'data-target="material.name"')

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
        self.assertContains(preview, 'Применить пакетно')
        self.assertNotContains(preview, 'Построчно (точнее)')
        self.assertFalse(Material.objects.filter(name='Стеклоткань демо').exists())

        apply_response = self.client.post(
            reverse('materials:import'),
            {
                'action': 'review_apply',
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

    def test_iterate_starts_from_mapping(self):
        self._upload_and_configure_wide_sample()
        mapping_page = self.client.get(reverse('materials:import') + '?step=mapping')
        self.assertEqual(mapping_page.status_code, 200)
        self.assertContains(mapping_page, 'Собрать черновик (пакетно)')
        self.assertContains(mapping_page, 'Идти построчно')

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
        self.assertContains(iterate_page, 'Записать эту строку')
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
