# LYRICA

**LYRICA** is a lightweight computational lyrics analysis toolkit for album-level and discography-level text analysis.
The project does not use machine learning, neural networks, embeddings, or generative AI. It extracts deterministic statistical, lexical, structural, and information-theoretic descriptors from song lyrics.

## Documentation

[LYRICA Mathematical Background](/pdf/LIRICA.pdf)

## Current tools

### 1. `text_count.py`

Main lyrics analyzer.

It loads a TXT album file, splits it into songs, cleans metadata, and computes song-level descriptors:

* word count;
* unique words;
* lines and blocks;
* repeated lines;
* lexical density;
* approximate rule-based POS/action channels;
* Shannon entropy by lyrical blocks;
* Action Fisher between blocks;
* Lexical Fisher between blocks;
* Zipf-based rarity descriptors;
* rare word density;
* structural modifier and agency indicators.

Output:

* `*_analysis.txt`
* `*_song_statistics.csv`

Shannon Entropy

H = −Σ pᵢ log₂(pᵢ)

pᵢ = nᵢ / N

Lexical Fisher

F = Σ (Hᵢ₊₁ − Hᵢ)² / (Hᵢ + ε)

### 2. `lyrica_album_visualizer.py`

Album and discography visualization helper.

It reads exported LYRICA analysis files and visualizes song-level and album-level metrics.

Main functions:

* open one album folder;
* open full artist/discography root folder;
* parse all exported analysis files;
* compare albums;
* group songs by album;
* visualize Shannon, Fisher, lexical density, repetition, rarity and agency metrics;
* compute album-level Gini descriptors;
* export parsed CSV files;
* export PNG figures.

## Basic workflow

```text
Input TXT album files
        ↓
text_count.py
        ↓
analysis.txt + song_statistics.csv
        ↓
lyrica_album_visualizer.py
        ↓
album charts + discography comparison + CSV/PNG export
```

## Data note

The repository should not include copyrighted lyrics.
Users should provide their own TXT files for research purposes.
The exported descriptors are numerical/statistical summaries and are not sufficient to reconstruct or reproduce the original lyrics.

## Dependencies

```bash
pip install matplotlib wordfreq
```

`wordfreq` is optional. If it is not installed, Zipf-based rarity analysis is skipped.

## Run

```bash
python3 text_count.py
python3 lyrica_album_visualizer.py
```
## Shannon / Fisher Analysis
<img src="/images/Output_mean_shannon_by_song.png" width="40%">
<img src="/images/Output_mean_action_fisher_by_song.png" width="40%">


## Status

Current version: experimental research prototype.

The software is intended for reproducible computational analysis of lyrics at song, album, and discography level.
