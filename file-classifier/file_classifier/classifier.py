"""Classificazione dei file per argomento tramite TF-IDF + clustering non supervisionato."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from .db import FileRecord

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Stopword italiane e inglesi di base, sufficienti per ripulire le etichette dei temi.
STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in",
    "con", "su", "per", "tra", "fra", "e", "o", "che", "non", "come", "del", "della",
    "dei", "delle", "al", "allo", "alla", "ai", "agli", "alle", "questo", "questa",
    "questi", "queste", "sono", "essere", "anche", "più", "meno", "the", "and", "or",
    "of", "to", "in", "is", "are", "on", "for", "with", "at", "by", "an", "as", "it",
    "this", "that", "be", "was", "were", "from",
}


@dataclass
class ClassificationResult:
    file_id: int
    theme: str
    keywords: list[str]


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = _SLUG_RE.sub("-", text)
    return text.strip("-") or "senza-titolo"


def _document_for(record: FileRecord) -> str:
    text = record.content or ""
    stem = Path(record.filename).stem.replace("_", " ").replace("-", " ")
    # Il nome file (senza estensione) pesa nella classificazione: utile quando il
    # contenuto è vuoto o breve.
    return f"{stem} {stem} {text}"


def classify_files(
    records: list[FileRecord],
    num_themes: int | None = None,
    max_features: int = 4000,
    keywords_per_theme: int = 4,
) -> list[ClassificationResult]:
    """Raggruppa i file per argomento usando TF-IDF + KMeans.

    Ritorna una lista di ClassificationResult con tema (etichetta leggibile,
    derivata dalle parole chiave più rilevanti del cluster) e parole chiave.
    """
    usable = [r for r in records if (r.content and r.content.strip()) or r.filename]
    if not usable:
        return []

    if len(usable) == 1:
        r = usable[0]
        keywords = _top_words_single_doc(_document_for(r))
        theme = slugify("-".join(keywords[:keywords_per_theme])) if keywords else "generico"
        return [ClassificationResult(file_id=r.id, theme=theme, keywords=keywords)]

    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    documents = [_document_for(r) for r in usable]

    vectorizer = TfidfVectorizer(
        max_features=max_features,
        stop_words=list(STOPWORDS),
        token_pattern=r"(?u)\b[a-zA-Zàèéìòù][a-zA-Zàèéìòù0-9_]{2,}\b",
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(documents)
    vocab = vectorizer.get_feature_names_out()

    if matrix.shape[1] == 0:
        # Nessun termine significativo estratto: un unico tema generico.
        return [
            ClassificationResult(file_id=r.id, theme="generico", keywords=[])
            for r in usable
        ]

    n_docs = len(usable)
    if num_themes is None:
        num_themes = max(2, min(12, round(math.sqrt(n_docs / 2))))
    num_themes = max(1, min(num_themes, n_docs))

    if num_themes == 1:
        labels = [0] * n_docs
        centers = matrix.mean(axis=0)
        centers = centers.A if hasattr(centers, "A") else centers
    else:
        model = KMeans(n_clusters=num_themes, random_state=42, n_init=10)
        labels = model.fit_predict(matrix)
        centers = model.cluster_centers_

    results: list[ClassificationResult] = []
    theme_labels: dict[int, tuple[str, list[str]]] = {}

    for cluster_id in set(int(label) for label in labels):
        center = centers[cluster_id]
        top_indices = center.argsort()[::-1][:keywords_per_theme]
        keywords = [vocab[i] for i in top_indices if center[i] > 0]
        if not keywords:
            keywords = ["generico"]
        theme_labels[cluster_id] = (slugify("-".join(keywords)), keywords)

    for record, label in zip(usable, labels):
        theme, keywords = theme_labels[int(label)]
        results.append(ClassificationResult(file_id=record.id, theme=theme, keywords=keywords))

    return results


def _top_words_single_doc(text: str, top_n: int = 4) -> list[str]:
    words = re.findall(r"[a-zA-Zàèéìòù]{3,}", text.lower())
    counts: dict[str, int] = {}
    for word in words:
        if word in STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]] or ["generico"]
