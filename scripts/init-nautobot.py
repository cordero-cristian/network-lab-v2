"""Create local admin credentials once after Nautobot migrations complete."""

import os

from django.contrib.auth import get_user_model
from nautobot.users.models import Token

username = os.environ["NAUTOBOT_SUPERUSER_NAME"]
user_model = get_user_model()
user = user_model.objects.filter(username=username).first()
if user is None:
    user = user_model.objects.create_superuser(
        username,
        os.environ["NAUTOBOT_SUPERUSER_EMAIL"],
        os.environ["NAUTOBOT_SUPERUSER_PASSWORD"],
    )

if not Token.objects.filter(user=user).exists():
    Token.objects.create(user=user, key=os.environ["NAUTOBOT_SUPERUSER_API_TOKEN"])
