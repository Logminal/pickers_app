from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid02
from py_vapid.utils import b64urlencode


class Command(BaseCommand):
    help = 'Генерирует пару VAPID-ключей для Web Push и печатает готовые строки для .env'

    def handle(self, *args, **options):
        vapid = Vapid02()
        vapid.generate_keys()

        private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, 'big')
        public_raw = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

        self.stdout.write('Добавьте в .env:\n')
        self.stdout.write(f'VAPID_PRIVATE_KEY={b64urlencode(private_raw)}')
        self.stdout.write(f'VAPID_PUBLIC_KEY={b64urlencode(public_raw)}')
        self.stdout.write('VAPID_CLAIM_EMAIL=mailto:admin@example.com  # свой email/домен')
