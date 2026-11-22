"""The welcome mail sent once, right after an account is created.

It is deliberately separate from verification: an account is real before the
address is confirmed, and a mail outage must never turn a successful signup
into an error. The caller sends both mails together and records each failure.
"""

from src.config.settings import get_settings
from src.db.models import User
from src.email.service import send, welcome_message


async def send_welcome_email(user: User) -> None:
    """Send the product welcome to the account's address."""
    settings = get_settings()
    await send(
        welcome_message(
            to=user.email,
            link=f"{settings.app_base_url.rstrip('/')}/overview",
            support_email=settings.legal_contact_email or settings.email_from,
            user_id=str(user.id),
        )
    )
