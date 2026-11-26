"""Foydalanuvchiga login (username) yoki ro'yxatdan o'tgan email orqali kirish imkonini beruvchi backend."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        login_value = (username or kwargs.get(UserModel.USERNAME_FIELD) or "").strip()
        if not login_value or password is None:
            return None

        user = UserModel.objects.filter(**{UserModel.USERNAME_FIELD: login_value}).first()
        if user is None and "@" in login_value:
            matches = list(UserModel.objects.filter(email__iexact=login_value)[:2])
            if len(matches) == 1:
                user = matches[0]

        if user is None:
            # Timing-attack himoyasi: foydalanuvchi topilmasa ham hash tekshiruvini simulyatsiya qilamiz
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
