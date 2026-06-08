from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0002_material_structure_link'),
        ('samples', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='sample',
            name='created_by',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='sample',
            name='material',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='samples',
                to='materials.material',
            ),
        ),
        migrations.AlterField(
            model_name='sample',
            name='object_type',
            field=models.CharField(
                choices=[
                    ('sample', 'Образец'),
                    ('prototype', 'Прототип'),
                    ('production', 'Производственная партия'),
                ],
                default='sample',
                max_length=50,
            ),
        ),
    ]
