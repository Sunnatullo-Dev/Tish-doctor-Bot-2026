"""Import all handler modules in a safe registration order."""


def register_all():
    from clinic_bot.handlers import user_flow  # noqa: F401
    from clinic_bot.handlers import doctor_registration  # noqa: F401
    from clinic_bot.handlers import admin_panel  # noqa: F401
    from clinic_bot.handlers import diagnosis  # noqa: F401
    from clinic_bot.handlers import broadcast  # noqa: F401
    from clinic_bot.handlers import routing  # noqa: F401
    from clinic_bot.handlers import fallback  # noqa: F401
