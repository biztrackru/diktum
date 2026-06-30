# Contributing

Спасибо за интерес к Диктум.

Проект пока находится в alpha-стадии, поэтому лучший вклад сейчас:

- воспроизводимые bug reports;
- feedback по установке на macOS;
- небольшие исправления setup/doctor/launcher UX;
- тесты без приватных аудио;
- улучшения документации;
- аккуратные улучшения pipeline, не ломающие local-first приватность.

## Правила приватности

Не прикладывайте к issue/PR:

- реальные аудиозаписи;
- транскрипты из `outputs/`;
- `.env`;
- Hugging Face/OpenAI/другие токены;
- model/cache/runtime folders;
- private benchmark references.

Если нужен пример, используйте синтетические fixtures или короткое специально созданное тестовое аудио без персональных данных.

## Локальная проверка

```bash
zsh -n app/scripts/*.sh *.command
.venv/bin/python -m compileall app/src tests
app/scripts/smoke_local.sh
git diff --check
```

`app/scripts/smoke_local.sh` не запускает тяжелые модели и не требует приватных аудио.

## Pull requests

- Делайте маленькие тематические PR.
- Не смешивайте refactor и product change без необходимости.
- Не добавляйте внешний API/облачную отправку аудио без явного opt-in UX и документации.
- Обновляйте README/docs, если меняется путь установки, запуска или privacy model.
