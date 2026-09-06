from django.core import mail
from django.test import override_settings

from signal_loop import settings_ci


@override_settings(EMAIL_BACKEND=settings_ci.EMAIL_BACKEND)
def test_ci_email_is_captured_in_memory():
    mail.send_mail(
        "Synthetic CI message", "Test only", "sender@example.com", ["recipient@example.com"]
    )

    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Synthetic CI message"
