#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LYRICA v0.9 - Lyrics Computational Analyzer

Features:
- Load TXT album lyrics file
- Split album into songs by headers like: 1. Song Title
- Select song from list
- Show selected song text
- Show statistics in right panel
- Split blocks by blank lines
- Count lines, words, unique words, repeated words, repeated lines
- Approximate rule-based POS/action histogram, no AI
- Optional wordfreq lexical rarity if installed
- Metadata cleaning: removes bracketed author/bonus/version lines
- Lexical Fisher by POS rarity channels
- Album CSV export: one row per song
- Default output folder creation from Input/Artist/Album.txt

Run:
    python3 lyrica_v09_output_folders.py
"""

import re
import math
import csv
import os
import platform
import subprocess
import tkinter as tk

try:
    from wordfreq import zipf_frequency
    WORDFREQ_AVAILABLE = True
except Exception:
    zipf_frequency = None
    WORDFREQ_AVAILABLE = False

from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Album export prefix
ALBUM_NAME = None

def current_album_prefix():
    return ALBUM_NAME if ALBUM_NAME else "album"



# ============================================================
# BASIC TEXT IO
# ============================================================

def read_text_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def clean_footer(text):
    """Remove common DarkLyrics-like footers and credits."""
    stop_markers = [
        "Submits, comments, corrections",
        "METALLICA LYRICS",
        "Line-up:",
        "James Hetfield:",
        "Kirk Hammet:",
        "Kirk Hammett:",
        "Lars Ulrich:",
        "Jason Newsted:",
        "Robert Trujillo:",
        "Cliff Burton:",
        "Bob Rock",
        "Thanks to",
    ]

    lines = text.splitlines()
    cleaned = []

    for line in lines:
        if any(marker in line for marker in stop_markers):
            break
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def parse_songs(album_text):
    """
    Split album text into songs using headers like:
        1. Hit The Lights
        2. The Four Horsemen
    """
    album_text = clean_footer(album_text)

    pattern = re.compile(r"(?m)^\s*(\d+)\.\s+(.+?)\s*$")
    matches = list(pattern.finditer(album_text))
    songs = []

    for i, match in enumerate(matches):
        number = int(match.group(1))
        title = match.group(2).strip()

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(album_text)
        body = album_text[start:end].strip()

        songs.append({
            "number": number,
            "title": title,
            "text": body,
        })

    return songs


# ============================================================
# TOKENIZATION AND BLOCKS
# ============================================================


def is_metadata_line(line):
    """
    Remove non-lyrical metadata lines before analysis.

    Examples:
        [James Hetfield]
        [Lars Ulrich]
        [Bonus track]
        [Originally recorded by ...]
        ["Kill 'Em All" Version][James Hetfield]
        ====================
    """
    s = line.strip()

    if not s:
        return False

    # underline separators
    if re.match(r"^=+$", s):
        return True

    # any line made only of one or more bracketed fields:
    # [A]
    # [A][B]
    # ["Kill 'Em All" Version][James Hetfield]
    if re.match(r"^(?:\s*\[[^\]]*\]\s*)+$", s):
        return True

    # common metadata fragments outside brackets
    meta_patterns = [
        r"^bonus\s+track$",
        r"^originally\s+recorded\b",
        r"^recorded\s+by\b",
        r"^music\s+by\b",
        r"^lyrics\s+by\b",
        r"^words\s+and\s+music\s+by\b",
        r"^-+\s*words\s+and\s+music\s+by\b",
        r"^copyright\b",
        r"^©",
    ]

    sl = s.lower()
    for pat in meta_patterns:
        if re.search(pat, sl):
            return True

    return False


def clean_song_text_for_analysis(text):
    """
    Clean selected song body before display/statistics.
    Keeps blank lines because they define blocks.
    Removes bracket metadata and separator lines.
    Collapses excessive blank lines.
    """
    cleaned = []
    previous_blank = False

    for line in text.splitlines():
        if is_metadata_line(line):
            continue

        if not line.strip():
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue

        cleaned.append(line.rstrip())
        previous_blank = False

    return "\n".join(cleaned).strip()


def words_from_text(text):
    return re.findall(r"\b[A-Za-zА-Яа-я0-9']+\b", text)


def split_blocks(text):
    blocks = re.split(r"\n\s*\n+", text.strip())
    return [b.strip() for b in blocks if b.strip()]


def nonempty_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


# ============================================================
# APPROXIMATE RULE-BASED POS / ACTION TAGS
# No AI, no external dependency.
# This is intentionally simple and editable.
# ============================================================

PRONOUNS = {
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
}

NEGATIONS = {
    "no", "not", "never", "none", "nothing", "nowhere",
    "neither", "nor", "cannot", "can't", "won't", "don't",
    "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "ain't", "nope",
}

MODALS = {
    "can", "could", "may", "might", "must",
    "shall", "should", "will", "would",
}

AUXILIARIES = {
    "am", "is", "are", "was", "were",
    "be", "been", "being",
    "have", "has", "had",
    "do", "does", "did",
}

DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those",
    "each", "every", "some", "any", "all", "both", "few", "many",
}

PREPOSITIONS = {
    "in", "on", "at", "by", "for", "with", "from", "to", "of", "into",
    "through", "under", "over", "above", "below", "within", "without",
    "before", "after", "around", "across", "behind", "between", "among",
    "upon", "off", "out", "down", "up", "inside", "outside",
}

CONJUNCTIONS = {
    "and", "or", "but", "so", "yet", "because", "although", "though",
    "while", "when", "where", "if", "than", "as",
}

COMMON_VERBS = {
    "go", "goes", "went", "gone", "going",
    "come", "comes", "came", "coming",
    "get", "gets", "got", "gotten", "getting",
    "make", "makes", "made", "making",
    "take", "takes", "took", "taken", "taking",
    "see", "sees", "saw", "seen", "seeing",
    "know", "knows", "knew", "known", "knowing",
    "want", "wants", "wanted", "wanting",
    "need", "needs", "needed", "needing",
    "feel", "feels", "felt", "feeling",
    "run", "runs", "ran", "running",
    "hide", "hides", "hid", "hidden", "hiding",
    "follow", "follows", "followed", "following",
    "burn", "burns", "burned", "burnt", "burning",
    "die", "dies", "died", "dying",
    "live", "lives", "lived", "living",
    "kill", "kills", "killed", "killing",
    "fight", "fights", "fought", "fighting",
    "rock", "rocks", "rocked", "rocking",
    "start", "starts", "started", "starting",
    "stop", "stops", "stopped", "stopping",
    "hit", "hits", "hitting",
    "jump", "jumps", "jumped", "jumping",
    "pull", "pulls", "pulled", "pulling",
    "join", "joins", "joined", "joining",
    "tempt", "tempts", "tempted", "tempting",
    "feed", "feeds", "feeding", "fed",
    "obey", "obeys", "obeyed", "obeying",
    "belong", "belongs", "belonged", "belonging",
    "draw", "draws", "drew", "drawn", "drawing",
    "learn", "learns", "learned", "learnt", "learning",
    "shine", "shines", "shined", "shining",
    "show", "shows", "showed", "shown", "showing",
    "dub", "dubs", "dubbed", "dubbing",
    "roam", "roams", "roamed", "roaming",
    "tread", "treads", "trod", "trodden", "treading",
    "prepare", "prepares", "prepared", "preparing",
    "secure", "secures", "secured", "securing",
    "provoke", "provokes", "provoked", "provoking",
    "threaten", "threatens", "threatened", "threatening",
    "touch", "touches", "touched", "touching",
    "search", "searches", "searched", "searching",
    "crave", "craves", "craved", "craving",
    "save", "saves", "saved", "saving",
    "ask", "asks", "asked", "asking",
    "speak", "speaks", "spoke", "spoken", "speaking",
    "keep", "keeps", "kept", "keeping",
    "give", "gives", "gave", "given", "giving",
    "try", "tries", "tried", "trying",
    "care", "cares", "cared", "caring",
    "look", "looks", "looked", "looking",
    "call", "calls", "called", "calling",
    "say", "says", "said", "saying",
    "tell", "tells", "told", "telling",
    "bring", "brings", "brought", "bringing",
    "leave", "leaves", "left", "leaving",
}

ADJECTIVES_COMMON = {
    "new", "old", "young", "fiery", "sinful", "sweet", "lethal", "dead",
    "black", "white", "dark", "bright", "free", "wrong", "right", "insane",
    "pained", "bitter", "tired", "constant", "quick", "proud", "deadly",
    "human", "big", "small", "heavy", "wild", "clean", "dirty",
}

ADJ_SUFFIXES = (
    "ous", "ful", "less", "able", "ible", "ive",
    "al", "ic", "ical", "ish", "ary", "ory", "y",
)

VERB_SUFFIXES = (
    "ing", "ed", "en", "ize", "ise",
)

NOUN_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ity", "ence", "ance",
    "ship", "hood", "ism", "er", "or", "age", "ure", "dom",
)


TAG_KEYS = [
    "NOUN", "VERB", "ADJ", "ADV", "PRON", "NEG", "MODAL", "AUX",
    "DET", "PREP", "CONJ", "PAST", "PRESENT", "FUTURE", "UNKNOWN",
]


def classify_word(word):
    w = word.lower().strip("'")

    flags = {k: 0 for k in TAG_KEYS}

    if not w:
        return flags

    if w in PRONOUNS:
        flags["PRON"] = 1

    if w in NEGATIONS:
        flags["NEG"] = 1

    if w in MODALS:
        flags["MODAL"] = 1

    if w in AUXILIARIES:
        flags["AUX"] = 1

    if w in DETERMINERS:
        flags["DET"] = 1

    if w in PREPOSITIONS:
        flags["PREP"] = 1

    if w in CONJUNCTIONS:
        flags["CONJ"] = 1

    # tense-like channels
    if w in {"will", "shall", "gonna"}:
        flags["FUTURE"] = 1

    if w in {"was", "were", "had", "did", "went", "came", "saw", "knew", "felt", "took", "made", "said", "told", "left"} or w.endswith("ed"):
        flags["PAST"] = 1

    if w in {"am", "is", "are", "do", "does", "have", "has"}:
        flags["PRESENT"] = 1

    # lexical channels
    if w.endswith("ly"):
        flags["ADV"] = 1

    if w in COMMON_VERBS or w.endswith(VERB_SUFFIXES):
        flags["VERB"] = 1
        if not flags["PAST"] and not flags["FUTURE"]:
            flags["PRESENT"] = 1

    if w in ADJECTIVES_COMMON or w.endswith(ADJ_SUFFIXES):
        flags["ADJ"] = 1

    if w.endswith(NOUN_SUFFIXES):
        flags["NOUN"] = 1

    # fallback: content word unknown -> noun-like
    function_like = (
        flags["PRON"] or flags["NEG"] or flags["MODAL"] or flags["AUX"] or
        flags["DET"] or flags["PREP"] or flags["CONJ"]
    )
    content_like = flags["NOUN"] or flags["VERB"] or flags["ADJ"] or flags["ADV"]

    if not function_like and not content_like:
        flags["NOUN"] = 1
        flags["UNKNOWN"] = 1

    return flags


def compute_pos_stats(words):
    totals = {k: 0 for k in TAG_KEYS}

    for w in words:
        flags = classify_word(w)
        for k in totals:
            totals[k] += flags[k]

    return totals


# ============================================================
# STATISTICS
# ============================================================


def shannon_entropy_from_counts(counts):
    """
    Shannon entropy in bits from a list of non-negative counts.
    """
    total = sum(counts)
    if total <= 0:
        return 0.0

    import math
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return h


def normalize_counts(counts):
    """
    Convert counts to probability vector.
    """
    total = sum(counts)
    if total <= 0:
        return [0.0 for _ in counts]
    return [c / total for c in counts]


def action_vector_from_pos(pos):
    """
    Action profile for Fisher-like block transition metric.
    Vector: VERB, AUX, MODAL, NEG, PRESENT, PAST, FUTURE.
    """
    keys = ["VERB", "AUX", "MODAL", "NEG", "PRESENT", "PAST", "FUTURE"]
    return [float(pos.get(k, 0)) for k in keys]


def fisher_distance_between_vectors(v1, v2, normalize=True):
    """
    Simple Fisher-like transition strength between two action vectors.

    normalize=True compares the action profile shape, not only block size.
    """
    if normalize:
        v1 = normalize_counts(v1)
        v2 = normalize_counts(v2)

    return sum((a - b) ** 2 for a, b in zip(v1, v2))




def is_content_word(word):
    """
    Content word for lexical rarity:
    noun-like, verb-like, adjective or adverb.
    Function words are ignored.
    """
    flags = classify_word(word)
    return bool(
        flags.get("NOUN", 0) or
        flags.get("VERB", 0) or
        flags.get("ADJ", 0) or
        flags.get("ADV", 0)
    )


def zipf_to_probability(zipf_value):
    """
    wordfreq Zipf scale is approximately log10(frequency per billion words).
    Therefore p(word) ~= 10^(Zipf - 9).
    """
    if zipf_value <= 0:
        return 0.0
    return 10.0 ** (zipf_value - 9.0)


def zipf_to_information_bits(zipf_value):
    """
    Self-information I(w) = -log2(p(w)).
    """
    p = zipf_to_probability(zipf_value)
    if p <= 0:
        return 0.0
    return -math.log2(p)


def compute_lexical_rarity_stats(words):
    """
    Optional global English rarity statistics using the wordfreq package.

    Install:
        pip install wordfreq

    The function returns Zipf-based rarity only for content words.
    Lower Zipf = rarer word.
    """
    result = {
        "available": WORDFREQ_AVAILABLE,
        "content_count": 0,
        "avg_zipf": 0.0,
        "median_zipf": 0.0,
        "min_zipf": 0.0,
        "avg_info_bits": 0.0,
        "rare_count": 0,
        "very_rare_count": 0,
        "rare_density": 0.0,
        "very_rare_density": 0.0,
        "rare_words": [],
    }

    if not WORDFREQ_AVAILABLE:
        return result

    seen = {}
    rows = []

    for w in words:
        wl = w.lower().strip("'")
        if not wl:
            continue
        if not is_content_word(wl):
            continue

        # avoid counting the same word many times in the rare-word list,
        # but keep repeated words in mean calculations
        z = float(zipf_frequency(wl, "en"))
        if z <= 0:
            # unknown to wordfreq: treat as very rare, but keep visible
            z = 0.0

        info = zipf_to_information_bits(z) if z > 0 else 0.0
        rows.append((wl, z, info))

        if wl not in seen or z < seen[wl][0]:
            seen[wl] = (z, info)

    if not rows:
        return result

    zipfs = [r[1] for r in rows]
    infos = [r[2] for r in rows]

    zipfs_sorted = sorted(zipfs)
    n = len(zipfs_sorted)
    if n % 2:
        median = zipfs_sorted[n // 2]
    else:
        median = 0.5 * (zipfs_sorted[n // 2 - 1] + zipfs_sorted[n // 2])

    rare_rows = [(w, z, info) for w, z, info in rows if z < 3.0]
    very_rare_rows = [(w, z, info) for w, z, info in rows if z < 2.5]

    unique_rare = sorted(
        [(w, z, info) for w, (z, info) in seen.items() if z < 3.0],
        key=lambda x: (x[1], x[0])
    )

    result.update({
        "content_count": len(rows),
        "avg_zipf": sum(zipfs) / len(zipfs),
        "median_zipf": median,
        "min_zipf": min(zipfs),
        "avg_info_bits": sum(infos) / len(infos) if infos else 0.0,
        "rare_count": len(rare_rows),
        "very_rare_count": len(very_rare_rows),
        "rare_density": len(rare_rows) / len(rows),
        "very_rare_density": len(very_rare_rows) / len(rows),
        "rare_words": unique_rare[:30],
    })

    return result



def primary_content_channel(word):
    """
    Return primary lexical channel for Lexical Fisher.
    Priority: ADJ, ADV, VERB, NOUN.
    """
    flags = classify_word(word)
    if flags.get("ADJ", 0):
        return "ADJ"
    if flags.get("ADV", 0):
        return "ADV"
    if flags.get("VERB", 0):
        return "VERB"
    if flags.get("NOUN", 0):
        return "NOUN"
    return None


def compute_lexical_channel_vector(words):
    """
    Block-level lexical register vector using wordfreq.

    Vector:
    [NOUN_avg_info, VERB_avg_info, ADJ_avg_info, ADV_avg_info,
     NOUN_density,  VERB_density,  ADJ_density,  ADV_density]
    """
    keys = ["NOUN", "VERB", "ADJ", "ADV"]
    buckets = {k: [] for k in keys}
    total_words = len(words)

    empty_summary = {
        k: {"count": 0, "avg_zipf": 0.0, "avg_info": 0.0, "density": 0.0}
        for k in keys
    }

    if not WORDFREQ_AVAILABLE or total_words <= 0:
        return [0.0] * 8, empty_summary

    for w in words:
        wl = w.lower().strip("'")
        if not wl:
            continue

        ch = primary_content_channel(wl)
        if ch is None:
            continue

        z = float(zipf_frequency(wl, "en"))
        if z <= 0:
            continue

        info = zipf_to_information_bits(z)
        buckets[ch].append((z, info))

    summary = {}
    vector = []

    for k in keys:
        vals = buckets[k]
        if vals:
            avg_zipf = sum(v[0] for v in vals) / len(vals)
            avg_info = sum(v[1] for v in vals) / len(vals)
        else:
            avg_zipf = 0.0
            avg_info = 0.0

        density = len(vals) / total_words if total_words else 0.0
        summary[k] = {
            "count": len(vals),
            "avg_zipf": avg_zipf,
            "avg_info": avg_info,
            "density": density,
        }
        vector.append(avg_info)

    for k in keys:
        vector.append(summary[k]["density"])

    return vector, summary


def lexical_fisher_between_vectors(v1, v2):
    """
    Fisher-like distance for lexical register changes between blocks.
    """
    return sum((a - b) ** 2 for a, b in zip(v1, v2))


def is_noun_like(word):
    """
    Old-school noun-like detector.
    A word is noun-like if it is tagged as NOUN or UNKNOWN-as-NOUN.
    """
    flags = classify_word(word)
    return bool(flags.get("NOUN", 0))


def is_adj_or_adv(word):
    """
    Descriptive modifier detector.
    We use ADJ and ADV as local gain-like descriptors.
    """
    flags = classify_word(word)
    return bool(flags.get("ADJ", 0) or flags.get("ADV", 0))


def is_verb_like(word):
    """
    Action detector.
    """
    flags = classify_word(word)
    return bool(flags.get("VERB", 0))


def compute_structural_weight_stats(words):
    """
    Detect simple structural intensification and agency.

    1) Description gain:
       ADJ/ADV before NOUN-like word increases the noun structural weight.
       Example: "dark night" -> night receives +1 structural weight.

    2) Agency:
       NOUN-like word followed by a VERB-like word in a short window is counted
       as an active structural node.
       Example: "death comes" -> death is an agent-like noun.

    This is not semantic interpretation. It is only a deterministic structural
    count based on local word roles.
    """
    words_l = [w.lower().strip("'") for w in words if w.strip("'")]
    n = len(words_l)

    modifier_links = 0
    agent_links = 0
    weighted_counts = {}

    # base word histogram
    for w in words_l:
        weighted_counts[w] = weighted_counts.get(w, 0.0) + 1.0

    # ADJ/ADV -> nearest following noun-like within 2 words
    for i, w in enumerate(words_l):
        if not is_adj_or_adv(w):
            continue

        for j in range(i + 1, min(i + 3, n)):
            target = words_l[j]
            if is_noun_like(target):
                weighted_counts[target] = weighted_counts.get(target, 0.0) + 1.0
                modifier_links += 1
                break

    # NOUN-like -> following VERB-like within 3 words
    for i, w in enumerate(words_l):
        if not is_noun_like(w):
            continue

        for j in range(i + 1, min(i + 4, n)):
            if is_verb_like(words_l[j]):
                agent_links += 1
                break

    noun_count = sum(1 for w in words_l if is_noun_like(w))
    adj_adv_count = sum(1 for w in words_l if is_adj_or_adv(w))

    weighted_shannon = shannon_entropy_from_counts(list(weighted_counts.values()))

    return {
        "modifier_links": modifier_links,
        "agent_links": agent_links,
        "noun_count": noun_count,
        "adj_adv_count": adj_adv_count,
        "weighted_noun_mass": noun_count + modifier_links,
        "weighted_counts": weighted_counts,
        "weighted_shannon": weighted_shannon,
    }


def compute_block_information_stats(blocks):
    """
    Shannon is calculated from word-frequency distribution inside each block.
    Fisher-like transition is calculated from action vectors between adjacent blocks.
    """
    block_rows = []

    for i, block in enumerate(blocks, start=1):
        words = words_from_text(block)

        word_freq = {}
        for w in words:
            wl = w.lower()
            word_freq[wl] = word_freq.get(wl, 0) + 1

        h_words = shannon_entropy_from_counts(list(word_freq.values()))
        pos = compute_pos_stats(words)
        action_vec = action_vector_from_pos(pos)
        structural = compute_structural_weight_stats(words)
        lexical_vec, lexical_summary = compute_lexical_channel_vector(words)

        block_rows.append({
            "index": i,
            "words": len(words),
            "unique": len(word_freq),
            "shannon_words": h_words,
            "weighted_shannon_words": structural["weighted_shannon"],
            "modifier_links": structural["modifier_links"],
            "agent_links": structural["agent_links"],
            "weighted_noun_mass": structural["weighted_noun_mass"],
            "lexical_vec": lexical_vec,
            "lexical_summary": lexical_summary,
            "pos": pos,
            "action_vec": action_vec,
        })

    transitions = []
    for i in range(len(block_rows) - 1):
        f = fisher_distance_between_vectors(
            block_rows[i]["action_vec"],
            block_rows[i + 1]["action_vec"],
            normalize=True
        )
        f_lex = lexical_fisher_between_vectors(
            block_rows[i]["lexical_vec"],
            block_rows[i + 1]["lexical_vec"]
        )

        transitions.append({
            "from": block_rows[i]["index"],
            "to": block_rows[i + 1]["index"],
            "fisher_action": f,
            "fisher_lexical": f_lex,
        })

    return block_rows, transitions



def compute_song_summary_row(song, clean_text=None):
    """
    Compact machine-readable summary for album export.
    One row = one song.
    """
    title = song["title"]
    number = song["number"]

    if clean_text is None:
        clean_text = clean_song_text_for_analysis(song["text"])

    lines = nonempty_lines(clean_text)
    blocks = split_blocks(clean_text)
    words = words_from_text(clean_text)

    word_count = len(words)
    unique_words = len(set(w.lower() for w in words))
    line_count = len(lines)
    block_count = len(blocks)
    char_count = len(clean_text)

    words_per_line = [len(words_from_text(line)) for line in lines]
    avg_words_per_line = sum(words_per_line) / len(words_per_line) if words_per_line else 0.0

    repeated_lines = {}
    for line in lines:
        key = line.lower()
        repeated_lines[key] = repeated_lines.get(key, 0) + 1
    repeated_lines = {line: c for line, c in repeated_lines.items() if c > 1}
    repeated_line_mass = sum(repeated_lines.values()) / line_count if line_count else 0.0

    lexical_density = unique_words / word_count if word_count else 0.0

    pos = compute_pos_stats(words)
    structural_total = compute_structural_weight_stats(words)
    rarity_total = compute_lexical_rarity_stats(words)
    channel_vec, channel_summary = compute_lexical_channel_vector(words)

    block_info, block_transitions = compute_block_information_stats(blocks)

    h_vals = [row["shannon_words"] for row in block_info]
    mean_h = sum(h_vals) / len(h_vals) if h_vals else 0.0
    min_h = min(h_vals) if h_vals else 0.0
    max_h = max(h_vals) if h_vals else 0.0

    f_vals = [tr["fisher_action"] for tr in block_transitions]
    mean_f = sum(f_vals) / len(f_vals) if f_vals else 0.0
    min_f = min(f_vals) if f_vals else 0.0
    max_f = max(f_vals) if f_vals else 0.0

    lf_vals = [tr.get("fisher_lexical", 0.0) for tr in block_transitions]
    mean_lf = sum(lf_vals) / len(lf_vals) if lf_vals else 0.0
    min_lf = min(lf_vals) if lf_vals else 0.0
    max_lf = max(lf_vals) if lf_vals else 0.0

    def pct(key):
        return (pos.get(key, 0) / word_count * 100.0) if word_count else 0.0

    return {
        "number": number,
        "title": title,
        "blocks": block_count,
        "lines": line_count,
        "words": word_count,
        "unique_words": unique_words,
        "characters": char_count,
        "avg_words_per_line": avg_words_per_line,
        "lexical_density": lexical_density,
        "repeated_line_mass": repeated_line_mass,

        "mean_block_shannon": mean_h,
        "min_block_shannon": min_h,
        "max_block_shannon": max_h,
        "shannon_range": max_h - min_h if h_vals else 0.0,

        "mean_action_fisher": mean_f,
        "min_action_fisher": min_f,
        "max_action_fisher": max_f,
        "action_fisher_range": max_f - min_f if f_vals else 0.0,

        "mean_lexical_fisher": mean_lf,
        "min_lexical_fisher": min_lf,
        "max_lexical_fisher": max_lf,
        "lexical_fisher_range": max_lf - min_lf if lf_vals else 0.0,

        "noun_pct": pct("NOUN"),
        "verb_pct": pct("VERB"),
        "adj_pct": pct("ADJ"),
        "adv_pct": pct("ADV"),
        "pron_pct": pct("PRON"),
        "neg_pct": pct("NEG"),
        "modal_pct": pct("MODAL"),
        "aux_pct": pct("AUX"),
        "present_pct": pct("PRESENT"),
        "past_pct": pct("PAST"),
        "future_pct": pct("FUTURE"),
        "unknown_pct": pct("UNKNOWN"),

        "avg_zipf": rarity_total.get("avg_zipf", 0.0),
        "median_zipf": rarity_total.get("median_zipf", 0.0),
        "min_zipf": rarity_total.get("min_zipf", 0.0),
        "avg_info_bits": rarity_total.get("avg_info_bits", 0.0),
        "rare_count": rarity_total.get("rare_count", 0),
        "very_rare_count": rarity_total.get("very_rare_count", 0),
        "rare_density": rarity_total.get("rare_density", 0.0),
        "very_rare_density": rarity_total.get("very_rare_density", 0.0),

        "noun_avg_zipf": channel_summary["NOUN"]["avg_zipf"],
        "verb_avg_zipf": channel_summary["VERB"]["avg_zipf"],
        "adj_avg_zipf": channel_summary["ADJ"]["avg_zipf"],
        "adv_avg_zipf": channel_summary["ADV"]["avg_zipf"],

        "noun_info_bits": channel_summary["NOUN"]["avg_info"],
        "verb_info_bits": channel_summary["VERB"]["avg_info"],
        "adj_info_bits": channel_summary["ADJ"]["avg_info"],
        "adv_info_bits": channel_summary["ADV"]["avg_info"],

        "modifier_links": structural_total["modifier_links"],
        "agent_links": structural_total["agent_links"],
        "base_noun_count": structural_total["noun_count"],
        "weighted_noun_mass": structural_total["weighted_noun_mass"],
        "modifier_density": structural_total["modifier_links"] / word_count if word_count else 0.0,
        "agent_density": structural_total["agent_links"] / word_count if word_count else 0.0,
        "agency_noun_ratio": structural_total["agent_links"] / structural_total["noun_count"] if structural_total["noun_count"] else 0.0,

        "top_repeated_lines": "; ".join(
            f"{c}x {line}" for line, c in sorted(repeated_lines.items(), key=lambda x: x[1], reverse=True)[:5]
        ),
    }



# ============================================================
# OUTPUT FOLDER HELPERS
# ============================================================

PROJECT_ROOT_NAME = "Lyrics_Analyzer"


def safe_filename(name):
    """
    Safe file/folder name, old-school and readable.
    """
    s = str(name).strip()
    s = re.sub(r"[\\/:*?\"<>|]+", "_", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_") or "untitled"


def find_project_root_from_file(path):
    """
    Find Lyrics_Analyzer root by walking upward from selected input file.
    If not found, use current working directory.
    """
    p = Path(path).resolve()

    for parent in [p.parent] + list(p.parents):
        if parent.name == PROJECT_ROOT_NAME:
            return parent

    cwd = Path.cwd().resolve()
    if cwd.name == PROJECT_ROOT_NAME:
        return cwd
    if cwd.name == "bin" and cwd.parent.name == PROJECT_ROOT_NAME:
        return cwd.parent

    return cwd


def infer_artist_from_input_path(path, project_root):
    """
    Expected:
        Lyrics_Analyzer/Input/Metallica/1983_Kill_Em_All.txt

    Artist is the first folder after Input.
    """
    p = Path(path).resolve()

    try:
        rel = p.relative_to(project_root.resolve())
        parts = rel.parts
        if len(parts) >= 3 and parts[0] == "Input":
            return safe_filename(parts[1])
    except Exception:
        pass

    return safe_filename(p.parent.name)


def infer_album_name_from_input_path(path):
    """
    Album name comes from TXT filename stem.
    """
    return safe_filename(Path(path).stem)


def default_output_folder_for_album(input_path):
    """
    Map input album TXT file to default output folder.

    Input:
        Lyrics_Analyzer/Input/Metallica/1983_Kill_Em_All.txt

    Output:
        Lyrics_Analyzer/Output/Metallica/1983_Kill_Em_All/
    """
    project_root = find_project_root_from_file(input_path)
    artist = infer_artist_from_input_path(input_path, project_root)
    album = infer_album_name_from_input_path(input_path)

    return project_root / "Output" / artist / album


def open_folder_in_file_manager(path):
    """
    Open output folder in the OS file manager.
    """
    folder = str(Path(path).resolve())

    try:
        system = platform.system().lower()

        if system == "linux":
            subprocess.Popen(["xdg-open", folder])
        elif system == "darwin":
            subprocess.Popen(["open", folder])
        elif system == "windows":
            os.startfile(folder)
        else:
            return False

        return True
    except Exception:
        return False


def write_text_output(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def export_album_statistics_to_folder(folder, songs):
    """
    Export album-level statistics into selected album output folder.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    stats_path = folder / f"{current_album_prefix()}_song_statistics.csv"
    count = export_album_csv(stats_path, songs)

    return {
        "count": count,
        "song_statistics": stats_path,
    }


def export_album_csv(path, songs):
    """
    Export one CSV file with one row per song.
    """
    rows = []
    for song in songs:
        clean_text = clean_song_text_for_analysis(song["text"])
        rows.append(compute_song_summary_row(song, clean_text))

    if not rows:
        return 0

    fieldnames = list(rows[0].keys())

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def compute_stats(song_title, text):
    lines = nonempty_lines(text)
    blocks = split_blocks(text)
    words = words_from_text(text)

    word_count = len(words)
    unique_words = len(set(w.lower() for w in words))
    char_count = len(text)
    line_count = len(lines)
    block_count = len(blocks)

    words_per_line = [len(words_from_text(line)) for line in lines]
    avg_words_per_line = sum(words_per_line) / len(words_per_line) if words_per_line else 0.0

    word_freq = {}
    for w in words:
        wl = w.lower()
        word_freq[wl] = word_freq.get(wl, 0) + 1

    repeated_words = {w: c for w, c in word_freq.items() if c > 1}
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

    repeated_lines = {}
    for line in lines:
        key = line.lower()
        repeated_lines[key] = repeated_lines.get(key, 0) + 1
    repeated_lines = {line: c for line, c in repeated_lines.items() if c > 1}

    repeated_line_mass = sum(repeated_lines.values()) / line_count if line_count else 0.0
    lexical_density = unique_words / word_count if word_count else 0.0

    pos = compute_pos_stats(words)
    structural_total = compute_structural_weight_stats(words)
    rarity_total = compute_lexical_rarity_stats(words)

    stats = []
    stats.append(f"SONG: {song_title}")
    stats.append("=" * 32)
    stats.append("")
    stats.append("GENERAL")
    stats.append("=" * 40)
    stats.append(f"Blocks / paragraphs : {block_count}")
    stats.append(f"Lines               : {line_count}")
    stats.append(f"Words               : {word_count}")
    stats.append(f"Unique words        : {unique_words}")
    stats.append(f"Characters          : {char_count}")
    stats.append(f"Avg words per line  : {avg_words_per_line:.2f}")
    stats.append(f"Lexical density     : {lexical_density:.3f}")
    stats.append(f"Repeated line mass  : {repeated_line_mass:.3f}")

    stats.append("")
    stats.append("BLOCK SIZES")
    stats.append("=" * 40)
    for i, block in enumerate(blocks, start=1):
        bw = len(words_from_text(block))
        bl = len(nonempty_lines(block))
        stats.append(f"Block {i:02d}: {bw:3d} words | {bl:2d} lines")


    block_info, block_transitions = compute_block_information_stats(blocks)

    stats.append("")
    stats.append("BLOCK SHANNON WORD ENTROPY")
    stats.append("=" * 40)
    if block_info:
        for row in block_info:
            stats.append(
                f"Block {row['index']:02d}: "
                f"H={row['shannon_words']:.3f} bits | "
                f"words={row['words']:3d} | "
                f"unique={row['unique']:3d}"
            )
    else:
        stats.append("No blocks.")


    stats.append("")
    stats.append("STRUCTURAL GAIN / WEIGHTED SHANNON")
    stats.append("=" * 40)
    stats.append("Rule: ADJ/ADV -> NOUN adds +1 noun weight")
    stats.append("Rule: NOUN -> VERB marks agent-like noun")
    if block_info:
        for row in block_info:
            gain = row["weighted_shannon_words"] - row["shannon_words"]
            stats.append(
                f"Block {row['index']:02d}: "
                f"Hw={row['weighted_shannon_words']:.3f} bits | "
                f"gain={gain:+.3f} | "
                f"mods={row['modifier_links']:2d} | "
                f"agents={row['agent_links']:2d} | "
                f"weighted_noun={row['weighted_noun_mass']:3d}"
            )
    else:
        stats.append("No blocks.")


    stats.append("")
    stats.append("LEXICAL CHANNELS BY BLOCK")
    stats.append("=" * 40)
    stats.append("Channels: NOUN, VERB, ADJ, ADV")
    stats.append("Format: avg information bits / density")
    if not WORDFREQ_AVAILABLE:
        stats.append("wordfreq module not installed.")
    elif block_info:
        for row in block_info:
            ls = row["lexical_summary"]
            stats.append(
                f"Block {row['index']:02d}: "
                f"N={ls['NOUN']['avg_info']:5.2f}b/{ls['NOUN']['density']:.2f} "
                f"V={ls['VERB']['avg_info']:5.2f}b/{ls['VERB']['density']:.2f} "
                f"A={ls['ADJ']['avg_info']:5.2f}b/{ls['ADJ']['density']:.2f} "
                f"R={ls['ADV']['avg_info']:5.2f}b/{ls['ADV']['density']:.2f}"
            )
    else:
        stats.append("No blocks.")

    stats.append("")
    stats.append("LEXICAL FISHER BETWEEN BLOCKS")
    stats.append("=" * 40)
    stats.append("Vector: [N_info, V_info, ADJ_info, ADV_info, N_den, V_den, ADJ_den, ADV_den]")
    if not WORDFREQ_AVAILABLE:
        stats.append("wordfreq module not installed.")
    elif block_transitions:
        for tr in block_transitions:
            stats.append(
                f"B{tr['from']:02d} -> B{tr['to']:02d}: "
                f"F_lexical={tr['fisher_lexical']:.6f}"
            )
    else:
        stats.append("Not enough blocks.")

    stats.append("")
    stats.append("ACTION FISHER BETWEEN BLOCKS")
    stats.append("=" * 40)
    stats.append("Vector: [VERB, AUX, MODAL, NEG, PRESENT, PAST, FUTURE]")
    if block_transitions:
        for tr in block_transitions:
            stats.append(
                f"B{tr['from']:02d} -> B{tr['to']:02d}: "
                f"F_action={tr['fisher_action']:.6f}"
            )
    else:
        stats.append("Not enough blocks.")

    if block_info:
        h_vals = [row["shannon_words"] for row in block_info]
        avg_h = sum(h_vals) / len(h_vals)
        max_h = max(h_vals)
        min_h = min(h_vals)

        stats.append("")
        stats.append("BLOCK INFORMATION SUMMARY")
        stats.append("=" * 40)
        stats.append(f"Mean block Shannon : {avg_h:.3f} bits")
        stats.append(f"Min block Shannon  : {min_h:.3f} bits")
        stats.append(f"Max block Shannon  : {max_h:.3f} bits")
        stats.append(f"Shannon range      : {(max_h - min_h):.3f} bits")

        if block_transitions:
            f_vals = [tr["fisher_action"] for tr in block_transitions]
            avg_f = sum(f_vals) / len(f_vals)
            max_f = max(f_vals)
            min_f = min(f_vals)
            stats.append(f"Mean action Fisher : {avg_f:.6f}")
            stats.append(f"Min action Fisher  : {min_f:.6f}")
            stats.append(f"Max action Fisher  : {max_f:.6f}")
            stats.append(f"Fisher range       : {(max_f - min_f):.6f}")

            if WORDFREQ_AVAILABLE:
                lf_vals = [tr["fisher_lexical"] for tr in block_transitions]
                avg_lf = sum(lf_vals) / len(lf_vals)
                max_lf = max(lf_vals)
                min_lf = min(lf_vals)
                stats.append(f"Mean lexical Fisher: {avg_lf:.6f}")
                stats.append(f"Min lexical Fisher : {min_lf:.6f}")
                stats.append(f"Max lexical Fisher : {max_lf:.6f}")
                stats.append(f"Lex Fisher range   : {(max_lf - min_lf):.6f}")

    stats.append("")
    stats.append("APPROX POS / ACTION HISTOGRAM")
    stats.append("=" * 40)
    for key in ["NOUN", "VERB", "ADJ", "ADV", "PRON", "NEG", "MODAL", "AUX", "DET", "PREP", "CONJ"]:
        pct = (pos[key] / word_count * 100.0) if word_count else 0.0
        stats.append(f"{key:<10} {pos[key]:4d}  {pct:6.2f}%")

    stats.append("")
    stats.append("APPROX TENSE CHANNELS")
    stats.append("=" * 40)
    for key in ["PAST", "PRESENT", "FUTURE"]:
        pct = (pos[key] / word_count * 100.0) if word_count else 0.0
        stats.append(f"{key:<10} {pos[key]:4d}  {pct:6.2f}%")

    stats.append("")
    stats.append("UNKNOWN AS NOUN-LIKE")
    stats.append("=" * 40)
    pct_unknown = (pos["UNKNOWN"] / word_count * 100.0) if word_count else 0.0
    stats.append(f"UNKNOWN   {pos['UNKNOWN']:4d}  {pct_unknown:6.2f}%")



    stats.append("")
    stats.append("LEXICAL RARITY / WORDFREQ")
    stats.append("=" * 40)
    if not rarity_total["available"]:
        stats.append("wordfreq module not installed.")
        stats.append("Install with:")
        stats.append("    pip install wordfreq")
    else:
        stats.append("Reference: wordfreq Zipf scale, English")
        stats.append("Lower Zipf = rarer word")
        stats.append(f"Content words        : {rarity_total['content_count']}")
        stats.append(f"Average Zipf         : {rarity_total['avg_zipf']:.3f}")
        stats.append(f"Median Zipf          : {rarity_total['median_zipf']:.3f}")
        stats.append(f"Minimum Zipf         : {rarity_total['min_zipf']:.3f}")
        stats.append(f"Avg information bits : {rarity_total['avg_info_bits']:.3f}")
        stats.append(f"Rare words < 3.0     : {rarity_total['rare_count']}")
        stats.append(f"Very rare < 2.5      : {rarity_total['very_rare_count']}")
        stats.append(f"Rare density         : {rarity_total['rare_density']:.3f}")
        stats.append(f"Very rare density    : {rarity_total['very_rare_density']:.3f}")


        channel_vec, channel_summary = compute_lexical_channel_vector(words)
        stats.append("")
        stats.append("LEXICAL RARITY BY POS CHANNEL")
        stats.append("=" * 40)
        stats.append("Format: count | density | avg Zipf | avg information bits")
        for k in ["NOUN", "VERB", "ADJ", "ADV"]:
            s = channel_summary[k]
            stats.append(
                f"{k:<5} {s['count']:4d} | "
                f"{s['density']:.3f} | "
                f"Zipf={s['avg_zipf']:.3f} | "
                f"I={s['avg_info']:.3f} bits"
            )

        stats.append("")
        stats.append("RAREST CONTENT WORDS")
        stats.append("=" * 40)
        if rarity_total["rare_words"]:
            for w, z, info in rarity_total["rare_words"]:
                if z > 0:
                    stats.append(f"{w:<20} Zipf={z:5.2f}  I={info:6.2f} bits")
                else:
                    stats.append(f"{w:<20} Zipf= n/a   I=  n/a")
        else:
            stats.append("No rare content words under Zipf < 3.0.")

    stats.append("")
    stats.append("STRUCTURAL INTENSIFICATION")
    stats.append("=" * 40)
    stats.append("ADJ/ADV -> NOUN links increase noun weight")
    stats.append(f"Modifier links       : {structural_total['modifier_links']}")
    stats.append(f"Agent-like noun links: {structural_total['agent_links']}")
    stats.append(f"Base noun count      : {structural_total['noun_count']}")
    stats.append(f"Weighted noun mass   : {structural_total['weighted_noun_mass']}")
    if word_count:
        stats.append(f"Modifier density     : {structural_total['modifier_links'] / word_count:.3f}")
        stats.append(f"Agent density        : {structural_total['agent_links'] / word_count:.3f}")
    if structural_total['noun_count']:
        stats.append(f"Agency / noun ratio  : {structural_total['agent_links'] / structural_total['noun_count']:.3f}")

    stats.append("")
    stats.append("WORDS PER LINE")
    stats.append("=" * 40)
    for i, n in enumerate(words_per_line, start=1):
        stats.append(f"{i:03d}. {n:2d} words")

    stats.append("")
    stats.append("TOP WORDS")
    stats.append("=" * 40)
    for word, count in top_words[:30]:
        stats.append(f"{word:<22} {count}")

    stats.append("")
    stats.append("REPEATED WORDS")
    stats.append("=" * 40)
    for word, count in sorted(repeated_words.items(), key=lambda x: x[1], reverse=True)[:40]:
        stats.append(f"{word:<22} {count}")

    stats.append("")
    stats.append("REPEATED LINES")
    stats.append("=" * 40)
    if repeated_lines:
        for line, count in sorted(repeated_lines.items(), key=lambda x: x[1], reverse=True):
            stats.append(f"[{count}x] {line}")
    else:
        stats.append("No repeated lines.")

    return "\n".join(stats)


# ============================================================
# GUI
# ============================================================

class LyricsViewer(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("LYRICA v0.9 - Lyrics Computational Analyzer")
        self.geometry("1500x780")

        self.songs = []
        self.current_file = None

        self.create_widgets()

    def create_widgets(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        self.btn_open = ttk.Button(top, text="Open TXT album", command=self.open_file)
        self.btn_open.pack(side="left")

        self.btn_export = ttk.Button(top, text="Export Album", command=self.export_album_statistics)
        self.btn_export.pack(side="left", padx=8)

        self.lbl_file = ttk.Label(top, text="No file loaded")
        self.lbl_file.pack(side="left", padx=12)

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(main)
        middle = ttk.Frame(main)
        right = ttk.Frame(main)

        main.add(left, weight=1)
        main.add(middle, weight=4)
        main.add(right, weight=2)

        ttk.Label(left, text="Songs").pack(anchor="w")

        self.song_list = tk.Listbox(left, height=30, exportselection=False)
        self.song_list.pack(fill="both", expand=True)
        self.song_list.bind("<<ListboxSelect>>", self.on_song_select)

        ttk.Label(middle, text="Selected song text").pack(anchor="w")

        text_frame = ttk.Frame(middle)
        text_frame.pack(fill="both", expand=True)

        self.text = tk.Text(
            text_frame,
            wrap="word",
            font=("DejaVu Sans Mono", 12),
        )
        self.text.pack(side="left", fill="both", expand=True)

        text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        text_scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=text_scroll.set)

        ttk.Label(right, text="Statistics").pack(anchor="w")

        stat_frame = ttk.Frame(right)
        stat_frame.pack(fill="both", expand=True)

        self.stats_text = tk.Text(
            stat_frame,
            wrap="none",
            font=("DejaVu Sans Mono", 10),
        )
        self.stats_text.pack(side="left", fill="both", expand=True)

        stat_scroll_y = ttk.Scrollbar(stat_frame, orient="vertical", command=self.stats_text.yview)
        stat_scroll_y.pack(side="right", fill="y")
        self.stats_text.configure(yscrollcommand=stat_scroll_y.set)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=4)

        self.lbl_stats = ttk.Label(bottom, text="Songs: 0")
        self.lbl_stats.pack(side="left")

    def open_file(self):
        initial_dir = Path.cwd()
        if (initial_dir / "Input").exists():
            initial_dir = initial_dir / "Input"
        elif initial_dir.name == "bin" and (initial_dir.parent / "Input").exists():
            initial_dir = initial_dir.parent / "Input"

        path = filedialog.askopenfilename(
            title="Select lyrics txt file",
            initialdir=str(initial_dir),
            filetypes=[
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )

        if not path:
            return

        try:
            raw = read_text_file(path)
            songs = parse_songs(raw)

            if not songs:
                messagebox.showwarning(
                    "No songs found",
                    "No song headers were found. Expected format: 1. Song Title",
                )
                return

            global ALBUM_NAME
            ALBUM_NAME = infer_album_name_from_input_path(path)
            self.current_file = path
            self.songs = songs

            self.refresh_song_list()

            self.lbl_file.config(text=path)
            self.lbl_stats.config(text=f"Songs: {len(self.songs)}")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_album_statistics(self):
        if not self.songs:
            messagebox.showwarning("No album loaded", "Please open a TXT album file first.")
            return

        if not self.current_file:
            messagebox.showwarning("No input file", "Input album file path is missing.")
            return

        default_folder = default_output_folder_for_album(self.current_file)

        proceed = messagebox.askyesno(
            "Export Album",
            "Do you want to export the album analysis?\n\n"
            f"Default output folder:\n{default_folder}"
        )
        if not proceed:
            return

        if not default_folder.exists():
            create = messagebox.askyesno(
                "Create Output Folder",
                "The output folder does not exist.\n\n"
                f"Create it now?\n\n{default_folder}"
            )
            if not create:
                return

            try:
                default_folder.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Folder creation error", str(e))
                return

        try:
            result = export_album_statistics_to_folder(default_folder, self.songs)

            analysis_lines = []
            analysis_lines.append("LYRICA")
            analysis_lines.append("Lyrics Computational Analyzer")
            analysis_lines.append("=" * 40)
            analysis_lines.append("")
            analysis_lines.append(f"Input file: {self.current_file}")
            analysis_lines.append(f"Songs: {len(self.songs)}")
            analysis_lines.append("")
            analysis_lines.append("=" * 40)
            analysis_lines.append("SONG ANALYSES")
            analysis_lines.append("=" * 40)
            analysis_lines.append("")

            for song in self.songs:
                clean_text = clean_song_text_for_analysis(song["text"])
                analysis_lines.append(compute_stats(song["title"], clean_text))
                analysis_lines.append("")
                analysis_lines.append("=" * 80)
                analysis_lines.append("")

            analysis_path = default_folder / f"{current_album_prefix()}_analysis.txt"
            write_text_output(analysis_path, "\n".join(analysis_lines))

            msg = (
                f"Export complete.\n\n"
                f"Songs exported: {result['count']}\n\n"
                f"Folder:\n{default_folder}\n\n"
                f"Files:\n"
                f"- {current_album_prefix()}_song_statistics.csv\n"
                f"- {current_album_prefix()}_analysis.txt\n\n"
                f"Open output folder?"
            )

            open_now = messagebox.askyesno("Export complete", msg)
            if open_now:
                open_folder_in_file_manager(default_folder)

        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def refresh_song_list(self):
        self.song_list.delete(0, tk.END)

        for song in self.songs:
            label = f"{song['number']}. {song['title']}"
            self.song_list.insert(tk.END, label)

        if self.songs:
            self.song_list.selection_clear(0, tk.END)
            self.song_list.selection_set(0)
            self.song_list.activate(0)
            self.show_song(0)

    def on_song_select(self, event):
        selection = self.song_list.curselection()
        if not selection:
            return

        self.show_song(selection[0])

    def show_song(self, index):
        song = self.songs[index]

        header = f"{song['number']}. {song['title']}\n"
        header += "=" * len(header.strip()) + "\n\n"
        clean_text = clean_song_text_for_analysis(song["text"])
        content = header + clean_text

        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, content)

        stats = compute_stats(song["title"], clean_text)
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.insert(tk.END, stats)

        words = words_from_text(clean_text)
        blocks = split_blocks(clean_text)
        lines = nonempty_lines(clean_text)

        self.lbl_stats.config(
            text=(
                f"Songs: {len(self.songs)} | "
                f"Selected: {song['title']} | "
                f"Blocks: {len(blocks)} | "
                f"Lines: {len(lines)} | "
                f"Words: {len(words)}"
            )
        )


def main():
    app = LyricsViewer()
    app.mainloop()


if __name__ == "__main__":
    main()
