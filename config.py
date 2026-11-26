import os

# Токен берется из настроек хостинга, а не из кода - так безопасно
BOT_TOKEN = os.getenv("9133481234:AAGh2-EbjN4G4jWIl0B18VpG69lj6L3oMvA", "")

# Твой ID - вставь сюда цифрами, когда пришлешь мне
ADMIN_IDS = [int(os.getenv("8355753325", "0"))] if os.getenv("8355753325") else []

# Если нет HF - оставь пустым
HF_TOKEN = os.getenv("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", "")


# Больше ключей НЕ НУЖНО. Все бесплатно.