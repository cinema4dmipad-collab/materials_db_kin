from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Проверяет подключение к S3 и запись через default storage Django.'

    def handle(self, *args, **options):
        if not settings.USE_S3_STORAGE:
            raise CommandError(
                'S3 отключён. Задайте USE_S3=true и AWS_STORAGE_BUCKET_NAME в .env.'
            )

        self.stdout.write(f'Backend: {settings.STORAGES["default"]["BACKEND"]}')
        self.stdout.write(f'Endpoint: {settings.AWS_S3_ENDPOINT_URL or "AWS default"}')
        self.stdout.write(f'Bucket: {settings.AWS_STORAGE_BUCKET_NAME}')

        try:
            import boto3

            client = boto3.client(
                's3',
                endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
            )
            buckets = [item['Name'] for item in client.list_buckets()['Buckets']]
            self.stdout.write(f'Доступные bucket: {", ".join(buckets) or "—"}')
            client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
        except Exception as exc:
            raise CommandError(f'Не удалось подключиться к S3: {exc}') from exc

        test_path = 'healthcheck/django-s3.txt'
        try:
            saved_path = default_storage.save(test_path, ContentFile(b'ok'))
            if not default_storage.exists(saved_path):
                raise CommandError('Файл сохранён, но exists() вернул False.')
            default_storage.delete(saved_path)
        except Exception as exc:
            raise CommandError(f'Ошибка записи через default storage: {exc}') from exc

        self.stdout.write(self.style.SUCCESS('S3 подключён, запись и удаление работают.'))
