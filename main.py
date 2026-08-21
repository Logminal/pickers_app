"""
Точка входа для запуска dev-сервера: `python main.py`.

Для остальных команд (migrate, createsuperuser, makemigrations и т.д.)
используйте стандартный `python manage.py <command>`.
"""

import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

    from django.core.management import execute_from_command_line

    argv = sys.argv[:1] + ['runserver'] + sys.argv[1:]
    execute_from_command_line(argv)


if __name__ == '__main__':
    main()
