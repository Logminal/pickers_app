"""Приватное зашифрованное хранилище для сканов паспорта (152-ФЗ, п.2.3 ТЗ).

Файл шифруется симметрично (Fernet/AES) перед записью на диск и расшифровывается
при чтении. Публичного URL у хранилища нет намеренно — `.url()` не реализован,
доступ возможен только через `PassportScanView` (apps/collectors/views.py),
которая дополнительно проверяет роль и логирует обращение в PersonalDataAccessLog.
"""

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from cryptography.fernet import Fernet, InvalidToken


def _fernet():
    return Fernet(settings.PASSPORT_ENCRYPTION_KEY)


class EncryptedPrivateStorage(FileSystemStorage):
    """Хранилище вне MEDIA_ROOT — не отдаётся веб-сервером напрямую."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.PRIVATE_STORAGE_ROOT / 'passports')
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise NotImplementedError(
            'У зашифрованного хранилища паспортов нет публичного URL. '
            'Используйте PassportScanView для доступа с логированием.'
        )

    def _save(self, name, content):
        raw = content.read()
        encrypted = _fernet().encrypt(raw)
        return super()._save(name, ContentFile(encrypted))

    def open_decrypted(self, name):
        """Возвращает расшифрованные байты файла. Не использовать напрямую вне
        PassportScanView — там же происходит проверка прав и логирование."""
        with super()._open(name, 'rb') as f:
            encrypted = f.read()
        try:
            return _fernet().decrypt(encrypted)
        except InvalidToken as exc:
            raise ValueError('Не удалось расшифровать файл — неверный ключ шифрования') from exc
