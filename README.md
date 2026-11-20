# NMD — Nail Master Designs Feed

> Публичный контентный репозиторий с каталогом проверенных дизайнов маникюра и нейл-арта для мобильного приложения **NMA** (`com.outrot.nailsmastet`).

[![Update Nail Designs Feed](https://github.com/Outrot174/NMD/actions/workflows/update_designs.yml/badge.svg)](https://github.com/Outrot174/NMD/actions/workflows/update_designs.yml)

---

## 💅 Описание каталога

Репозиторий `NMD` служит CDN-источником для клиента `NMA`. Приложение обращается напрямую к `designs.json`:
```
https://raw.githubusercontent.com/Outrot174/NMD/main/designs.json
```

Каталог автоматически обновляется и проверяется ежедневным воркфлоу GitHub Actions в 04:00 UTC.

### Структура схемы элемента `designs.json`:
```json
{
  "id": "nm_001",
  "imageUrl": "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1080&q=80",
  "title": "Ультратонкий микрофренч на молочной базе",
  "tags": [
    "минимализм",
    "молочный",
    "нюд",
    "френч"
  ],
  "sourceAuthor": "Елена Морозова (Москва)",
  "createdAt": "2026-02-10T10:00:00Z"
}
```

---

## 🛠️ Скрипт валидации

Локальный запуск скрипта валидации и тегирования:
```bash
python3 scripts/fetch_designs.py
```
- Проверяет доступность изображений по коду **HTTP 200**.
- Проверяет валидность `Content-Type` и ненулевой размер.
- Устраняет дубликаты по URL и ID.
- Автоматически назначает русскоязычные теги формы, стиля и повода.
