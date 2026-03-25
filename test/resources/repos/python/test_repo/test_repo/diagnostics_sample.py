from .models import User


def broken_factory() -> User:
    return missing_user


def broken_consumer() -> None:
    created_user = broken_factory()
    print(created_user)
    print(undefined_name)
