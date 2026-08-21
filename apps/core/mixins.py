from django.contrib.auth.mixins import UserPassesTestMixin


class RoleRequiredMixin(UserPassesTestMixin):
    """Ограничение доступа к view по роли пользователя (сборщик/менеджер/админ)."""

    allowed_roles: tuple[str, ...] = ()

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.role in self.allowed_roles or user.is_superuser)
