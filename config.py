import os

# Токен берется из настроек хостинга, а не из кода - так безопасно
BOT_TOKEN = os.getenv("9133481234:AAHGO_aZ7FmRzJxVIf8kx2gJj2EyPNiBj8o", "")

# Твой ID - вставь сюда цифрами, когда пришлешь мне
ADMIN_IDS = [int(os.getenv("8355753325", "0"))] if os.getenv("8355753325") else []

# Если нет HF - оставь пустым
HF_TOKEN = os.getenv("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", "")


# Больше ключей НЕ НУЖНО. Все бесплатно.
