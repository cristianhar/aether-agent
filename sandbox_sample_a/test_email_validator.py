import pytest
from email_validator import is_valid_email

def test_valid_emails():
    assert is_valid_email('user@example.com')
    assert is_valid_email('user.name@domain.co.uk')


def test_invalid_emails():
    assert not is_valid_email('user@')
    assert not is_valid_email('plainaddress')
    assert not is_valid_email('@missingusername.com')
    assert not is_valid_email('user@.com')
