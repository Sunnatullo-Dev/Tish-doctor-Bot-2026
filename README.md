# 🦷 Tish Doctor Bot

Smile Concept klinikasi uchun Telegram bot. Bemorlar qabulga yozilishi, onlayn tashhis olishi va doktorlar bilan to'g'ridan-to'g'ri suhbat qilishi mumkin.

## Imkoniyatlar

- 📅 **Qabulga yozilish** — doktor, sana va vaqt tanlash, avtomatik eslatmalar
- 🩺 **Onlayn tashhis** — SMS yoki audio/video suhbat orqali doktor bilan bog'lanish
- 🛡️ **Admin panel** — statistika, klinika/doktor boshqaruvi, eksport (Excel/CSV)
- 📢 **Broadcast** — barcha foydalanuvchilarga xabar yuborish
- 📌 **Majburiy kanal** — obuna tekshiruvi bilan kanal boshqaruvi
- ⭐ **Reyting tizimi** — uchrashuv yakunida doktorni baholash

## O'rnatish

```bash
git clone https://github.com/Sunnatullo-Dev/Tish-doctor-Bot-2026.git
cd Tish-doctor-Bot-2026
pip install -r requirements.txt
cp .env.example .env
# .env faylini tahrirlang
python main.py
```

## Sozlash

`.env` faylida quyidagilarni to'ldiring:

```
BOT_TOKEN=your-telegram-bot-token
ADMIN_ID=your-telegram-user-id
BOT_WORKER_THREADS=32
```

## Loyiha tuzilmasi

```
main.py                    — Ishga tushirish nuqtasi
clinic_bot/
  shared.py                — Global o'zgaruvchilar va konfiguratsiya
  storage.py               — JSON saqlash/yuklash
  helpers.py               — Yordamchi funksiyalar
  keyboards.py             — Inline klaviaturalar
  channel_gate.py          — Majburiy kanal tekshiruvi
  scheduler_jobs.py        — Eslatma va reyting scheduleri
  handlers/
    user_flow.py           — Foydalanuvchi oqimi (bron qilish)
    admin_panel.py         — Admin panel
    diagnosis.py           — Onlayn tashhis tizimi
    doctor_registration.py — Doktor tomonidan tasdiqlash
    broadcast.py           — Reklama yuborish
    routing.py             — Foydalanuvchi ↔ doktor/admin xabar yo'naltirish
    fallback.py            — Noma'lum xabarlarga javob
```

## Texnologiyalar

- [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [pytz](https://pythonhosted.org/pytz/)
