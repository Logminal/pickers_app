from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        COLLECTOR = 'collector', 'Сборщик'
        MANAGER = 'manager', 'Менеджер'
        ADMIN = 'admin', 'Администратор'

    role = models.CharField('Роль', max_length=20, choices=Role.choices, default=Role.COLLECTOR)
    phone = models.CharField('Телефон', max_length=20, unique=True, null=True, blank=True)
    phone_confirmed = models.BooleanField('Телефон подтверждён', default=False)
    telegram_chat_id = models.CharField('Telegram chat ID', max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def is_collector(self):
        return self.role == self.Role.COLLECTOR

    def is_manager(self):
        return self.role == self.Role.MANAGER

    def is_admin_role(self):
        return self.role == self.Role.ADMIN
