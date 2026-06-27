#!/usr/bin/env python3
"""
ASR readability scorer — dependency-free (stdlib only).

Зачем: дать сравнимые числа по «читабельности» вывода ЛЮБОЙ ASR-модели, чтобы
проверить гипотезу «пунктуация/регистр/ё зависят от модели». Метрики текстовые,
без выравнивания, поэтому работают и для нашего вывода, и для референса, и для
любой другой модели (Whisper, GigaAM v3 e2e, LM Studio/Wisper/Handy и т.д.).

Использование:
    python3 score.py <file1.txt|.md> [file2 ...] [--terms нфло,пубертат,...]

Каждый файл нормализуется (срезаются метки «Спикер N:», таймкоды HH:MM:SS и
markdown-таймкоды в backticks), затем считаются метрики. Печатает таблицу.

Метрики:
    words            — число слов
    punct/100w       — знаков [.,!?;:—–] на 100 слов (0 ≈ нет пунктуации)
    upper%           — доля заглавных среди букв (≈0 ≈ всё в нижнем регистре)
    sent_caps%       — доля «предложений», начинающихся с заглавной
    yo/1k            — число «ё/Ё» на 1000 слов (0 = ё не восстановлены)
    terms            — сколько искомых терминов/имён найдено (если задан --terms)
"""
import re
import sys
from argparse import ArgumentParser

PUNCT = ".,!?;:—–"

def normalize(text: str) -> str:
    text = re.sub(r'Спикер\s*\d+\s*:', ' ', text)
    text = re.sub(r'`?\d{2}:\d{2}:\d{2}(?:-\d{2}:\d{2}:\d{2})?`?', ' ', text)
    text = re.sub(r'^#.*$', ' ', text, flags=re.M)       # markdown headers
    text = re.sub(r'[*_>`]+', ' ', text)                  # markdown noise
    return text

def score(text: str, terms):
    body = normalize(text)
    words = re.findall(r'\S+', body)
    nwords = len(words) or 1
    punct = sum(body.count(p) for p in PUNCT)
    letters = re.findall(r'[A-Za-zА-Яа-яЁё]', body)
    uppers = re.findall(r'[A-ZА-ЯЁ]', body)
    nlet = len(letters) or 1
    # sentence segmentation by terminal punctuation
    sents = [s.strip() for s in re.split(r'[.!?]+', body) if s.strip()]
    cap_sents = sum(1 for s in sents if s[:1].isupper())
    yo = body.count('ё') + body.count('Ё')
    found = []
    if terms:
        low = body.lower()
        found = [t for t in terms if t.lower() in low]
    return {
        "words": nwords,
        "punct/100w": round(punct * 100 / nwords, 1),
        "upper%": round(len(uppers) * 100 / nlet, 1),
        "sent_caps%": round(cap_sents * 100 / (len(sents) or 1), 1),
        "yo/1k": round(yo * 1000 / nwords, 2),
        "terms": (f"{len(found)}/{len(terms)}" if terms else "-"),
    }

def main(argv):
    parser = ArgumentParser(description="Score ASR transcript readability.")
    parser.add_argument("files", nargs="*", help="Transcript files (.txt/.md) to score.")
    parser.add_argument("--terms", default="", help="Comma-separated terms to search for.")
    args = parser.parse_args(argv)
    files = args.files
    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    if not files:
        print(__doc__); return 1
    cols = ["words", "punct/100w", "upper%", "sent_caps%", "yo/1k", "terms"]
    name_w = max(len(f.rsplit("/", 1)[-1]) for f in files)
    print(f"{'file':{name_w}} | " + " | ".join(f"{c:>10}" for c in cols))
    print("-" * (name_w + 3 + 13 * len(cols)))
    for f in files:
        try:
            txt = open(f, encoding="utf-8").read()
        except OSError as e:
            print(f"{f}: {e}"); continue
        m = score(txt, terms)
        print(f"{f.rsplit('/',1)[-1]:{name_w}} | " + " | ".join(f"{str(m[c]):>10}" for c in cols))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
