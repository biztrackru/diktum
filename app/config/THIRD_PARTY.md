# Компоненты и модели Диктума

Модели и GigaSTT загружаются отдельно при явном запуске настройки.
Версии, источники и SHA-256 перечислены в `resources.json`.

| Компонент | Авторы и источник | Лицензия или условия |
| --- | --- | --- |
| GigaSTT | [ekhodzitsky/gigastt](https://github.com/ekhodzitsky/gigastt) | MIT |
| GigaAM v3 | [Salute Developers](https://github.com/salute-developers/GigaAM) | MIT |
| GigaAM CTC ONNX bundle | [Handy](https://github.com/cjpais/Handy), модель GigaAM v3 | См. исходную модель GigaAM и каталог Handy |
| Silero VAD | [Silero Team](https://github.com/snakers4/silero-vad) | MIT |
| RUPunct ONNX | [ekhodzitsky/rupunct-small-onnx](https://huggingface.co/ekhodzitsky/rupunct-small-onnx) | См. карточку модели |
| community-1 | [pyannote](https://huggingface.co/pyannote/speaker-diarization-community-1) | CC-BY-4.0; первоначальный доступ требует принятия условий Hugging Face |

Настройка не передаёт аудио и расшифровки этим проектам. Обработка использует
локальные файлы; метрики использования pyannote, Hugging Face и ONNX Runtime
отключены перед запуском моделей.
