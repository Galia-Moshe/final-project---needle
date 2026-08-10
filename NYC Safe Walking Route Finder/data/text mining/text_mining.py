import re
from concurrent.futures import ProcessPoolExecutor, as_completed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import spacy
from deep_translator import GoogleTranslator
from langdetect import DetectorFactory, detect
from wordcloud import WordCloud

# Fix seed for reproducible language detection
DetectorFactory.seed = 0

# ----------------------------------------------------
# 1. MULTILINGUAL KEYWORD CONFIGURATIONS
# ----------------------------------------------------
# Base lists maintained for the final Step 3 English SpaCy parsing
safety_adjectives = {
    "unsafe", "sketchy", "scared", "dangerous", "afraid", "suspicious",
    "shady", "creepy", "scary", "stressful", "unpleasant"
}
# REMOVED: "night" and "evening" - they are not crimes and cause massive False Positives
crime_events = {
    "robbed", "crime", "stolen", "thief", "attacked", "scam", "drugs", "homeless"
}
location_nouns = {
    "area", "street", "neighborhood", "alley", "block", "subway", "station",
    "surroundings", "location", "park", "walk", "place", "outside", "zone",
    "neighborhoods", "avenue", "corner"
}

# PIPELINE OPTIMIZATION: Updated multilingual bank (Removed all night/evening/tarde/nuit variants)
multilingual_keywords = {
    # --- English ---
    "unsafe", "sketchy", "sketchier", "scared", "scare", "scares", "scaring", "scary",
    "dangerous", "danger", "dangers", "afraid", "suspicious", "suspicion", "shady", "shade",
    "creepy", "creep", "robbed", "rob", "robbing", "robber", "robbers", "crime", "crimes",
    "criminal", "stolen", "steal", "steals", "stealing", "thief", "thieves", "attacked",
    "attack", "attacking", "attacks", "scam", "scams", "scammed", "scammer", "scammers",
    "stressful", "stress", "unpleasant", "drugs", "drug", "homeless", "homelessness",

    # --- Spanish (es) ---
    "inseguro", "insegura", "miedo", "asustado", "peligro", "peligroso", "peligrosa",
    "sospechoso", "sospechosa", "robo", "robado", "robada", "robar", "crimen", "criminal",
    "ladrón", "ladron", "ataque", "atacado", "estafa", "estafado", "estresante",
    "desagradable", "drogas", "droga", "vagabundo", "indigente",

    # --- French (fr) ---
    "dangereux", "dangereuse", "insécurité", "insécurisant", "peur", "effrayé", "suspect",
    "louche", "vol", "volé", "voler", "crime", "criminel", "voleur", "agression", "agressé",
    "attaqué", "arnaque", "arnaqué", "stressant", "désagréable", "drogue", "drogues",
    "sdf", "sans-abri",

    # --- Portuguese (pt) ---
    "inseguro", "insegura", "medo", "assustado", "perigo", "perigoso", "perigosa",
    "suspeito", "suspeita", "roubo", "roubado", "roubada", "roubar", "crime", "criminal",
    "ladrão", "ataque", "atacado", "golpe", "estresante", "desagradável", "drogas", "droga",
    "mendigo",

    # --- German (de) ---
    "unsicher", "angst", "gefährlich", "gefahr", "diebstahl", "gestohlen", "stehlen",
    "raub", "ausgeraubt", "verbrechen", "kriminelle", "krimineller", "dieb", "angriff",
    "angegriffen", "betrug", "betrogen", "stressig", "unangenehm", "drogen", "droge",
    "obdachlose", "obdachloser",

    # --- Romanian (ro) ---
    "nesigur", "nesigură", "frică", "speriat", "pericol", "periculos", "periculoasă",
    "suspect", "dubios", "jaf", "jefuit", "furat", "fura", "crimă", "criminal", "hoț",
    "atac", "atacat", "înșelătorie", "teapă", "stresant", "neplăcut", "droguri", "drog",
    "boschetar"
}

# Compile a global regular expression pattern for maximum execution speed
fast_multilingual_pattern = r"\b(?:" + "|".join(multilingual_keywords) + r")\b"


# ----------------------------------------------------
# 2. MULTIPROCESSING WORKERS
# ----------------------------------------------------
def worker_fast_keyword_filter(chunk_tuple):
    """Step 1 Worker: Scans raw strings instantly using pre-compiled multilingual regex."""
    index, comments, pattern = chunk_tuple
    compiled_regex = re.compile(pattern, re.IGNORECASE)
    keep_mask = []

    for text in comments:
        if not isinstance(text, str) or len(text.strip()) == 0:
            keep_mask.append(False)
            continue

        # Clean HTML breaks here to prevent regex token binding issues
        clean_text = text.replace("<br/>", " ").replace("<br>", " ")
        if compiled_regex.search(clean_text):
            keep_mask.append(True)
        else:
            keep_mask.append(False)

    return index, keep_mask


def worker_lang_and_translate_candidates(chunk_tuple):
    """Step 2 Worker: Detects languages and translates targets."""
    index, comments = chunk_tuple
    translator = GoogleTranslator(source="auto", target="en")
    target_langs = {"es", "fr", "pt", "de", "ro"}

    processed_comments = []
    keep_mask = []

    for text in comments:
        # Standardize spaces and remove HTML junk before translation/detection
        clean_text = text.replace("<br/>", " ").replace("<br>", " ")
        try:
            lang = detect(clean_text[:200])
        except:
            lang = "unknown"

        if lang == "en":
            processed_comments.append(clean_text)
            keep_mask.append(True)
        elif lang in target_langs:
            try:
                translated = translator.translate(clean_text)
                processed_comments.append(translated)
                keep_mask.append(True)
            except:
                processed_comments.append("")
                keep_mask.append(False)
        else:
            processed_comments.append("")
            keep_mask.append(False)

    return index, processed_comments, keep_mask


def process_spacy_doc(doc):
    """Step 3 Core NLP Dependency Tree Parser (Applied on case-insensitive clean text)."""
    if not doc or len(doc) == 0:
        return [], 0

    filtered_tokens = [
        token.text
        for token in doc
        if not token.is_stop and not token.is_punct and not token.is_space
    ]
    is_unsafe = 0

    for token in doc:
        # Use token.lower_ to make it completely case-insensitive
        token_lower = token.lower_

        if token_lower in safety_adjectives:
            if token.pos_ == "ADJ" and token.head.lower_ in location_nouns:
                is_unsafe = 1
                break
            if token.head.pos_ in ["VERB", "AUX"]:
                for child in token.head.children:
                    if (
                        child.dep_ in ["nsubj", "nsubjpass"]
                        and child.lower_ in location_nouns
                    ):
                        is_unsafe = 1
                        break
            if is_unsafe:
                break
        elif token_lower in crime_events:
            if any(t.lower_ in location_nouns for t in token.sent):
                is_unsafe = 1
                break

    return filtered_tokens, is_unsafe


# ----------------------------------------------------
# 3. MAIN RUN PIPELINE
# ----------------------------------------------------
if __name__ == "__main__":
    num_cores = 8
    chunk_size = 10000

    print("--- Starting Optimized Multilingual Text Mining Pipeline ---")
    print("Loading dataset...")
    df = pd.read_csv("merged_dataset.csv")
    total_initial_rows = len(df)
    print(f"Total reviews loaded: {total_initial_rows:,}\n")

    # ----------------------------------------------------
    # STEP 1: HIGH-SPEED MULTILINGUAL KEYWORD FILTER (ALL ROWS)
    # ----------------------------------------------------
    print(f"1. Scanning all {total_initial_rows:,} rows via high-speed Regex Filter...")

    indices_step1 = np.array_split(df.index, max(1, total_initial_rows // chunk_size))
    futures_step1 = []

    with ProcessPoolExecutor(max_workers=num_cores) as executor:
        for chunk_idx in indices_step1:
            chunk_comments = df.loc[chunk_idx, "comments"].fillna("").astype(str).tolist()
            futures_step1.append(
                executor.submit(
                    worker_fast_keyword_filter,
                    (chunk_idx, chunk_comments, fast_multilingual_pattern),
                )
            )

    processed_count_step1 = 0
    candidate_indices = []

    for future in as_completed(futures_step1):
        chunk_idx, keep_mask = future.result()
        processed_count_step1 += len(chunk_idx)

        for idx, keep in zip(chunk_idx, keep_mask):
            if keep:
                candidate_indices.append(idx)

        if processed_count_step1 % 50000 == 0 or processed_count_step1 == total_initial_rows:
            print(f" [Step 1 Progress]: Scanned {processed_count_step1:,} / {total_initial_rows:,} rows...")

    df_candidates = df.loc[candidate_indices].copy()
    total_candidates = len(df_candidates)
    print(f"-> Step 1 Complete. Found {total_candidates:,} keyword-matched candidates. Dropped {total_initial_rows - total_candidates:,} reviews.\n")

    # ----------------------------------------------------
    # STEP 2: LANGUAGE DETECTION & TRANSLATION (CANDIDATES ONLY)
    # ----------------------------------------------------
    print(f"2. Running Language Detection & Translation ONLY on {total_candidates:,} high-risk candidates...")

    indices_step2 = np.array_split(df_candidates.index, max(1, total_candidates // 2000))
    futures_step2 = []

    with ProcessPoolExecutor(max_workers=num_cores) as executor:
        for chunk_idx in indices_step2:
            chunk_comments = df_candidates.loc[chunk_idx, "comments"].fillna("").astype(str).tolist()
            futures_step2.append(
                executor.submit(
                    worker_lang_and_translate_candidates, (chunk_idx, chunk_comments)
                )
            )

    processed_count_step2 = 0
    final_indices = []
    final_comments = []

    for future in as_completed(futures_step2):
        chunk_idx, processed_comments, keep_mask = future.result()
        processed_count_step2 += len(chunk_idx)

        for idx, comment, keep in zip(chunk_idx, processed_comments, keep_mask):
            if keep:
                final_indices.append(idx)
                final_comments.append(comment)

        print(f" [Step 2 Progress]: Processed Translation for {processed_count_step2:,} / {total_candidates:,} candidates...")

    df_step2 = pd.DataFrame({"comments_processed": final_comments}, index=final_indices)
    df_step2 = df_step2.join(df_candidates[["listing_id", "latitude", "longitude"]])
    total_step2_rows = len(df_step2)
    print(f"-> Step 2 Complete. Kept {total_step2_rows:,} English or successfully translated reviews.\n")

    # ----------------------------------------------------
    # STEP 3: SPACY DEPENDENCY PARSING
    # ----------------------------------------------------
    print(f"3. Running SpaCy Dependency Parsing on {total_step2_rows:,} verified English candidates...")

    print("Loading SpaCy NLP model...")
    nlp = spacy.load("en_core_web_sm")

    tokens_list = []
    is_unsafe_list = []

    for i, doc in enumerate(
        nlp.pipe(
            df_step2["comments_processed"].tolist(),
            batch_size=500,
            n_process=num_cores,
            disable=["ner", "lemmatizer"],
        )
    ):
        tokens, is_unsafe = process_spacy_doc(doc)
        tokens_list.append(tokens)
        is_unsafe_list.append(is_unsafe)

        if (i + 1) % 1000 == 0 or (i + 1) == total_step2_rows:
            print(f" [Step 3 Progress]: Parsing Dependency Tree {i + 1:,} / {total_step2_rows:,} reviews...")

    df_step2["is_unsafe"] = is_unsafe_list

    # ----------------------------------------------------
    # STEP 4: FORMAT AND EXPORT UN-GROUPED GRAIN DATA
    # ----------------------------------------------------
    print("\n4. Formatting final output dataset at review level...")

    final_output = df_step2[["listing_id", "comments_processed", "longitude", "latitude", "is_unsafe"]]
    output_filename = "processed_safety_reviews.csv"
    final_output.to_csv(output_filename, index=False)

    print("\n" + "=" * 50)
    print(f"SUCCESS! Created '{output_filename}'")
    print(f"Exported {len(final_output):,} review rows containing listing IDs, comments, coordinates and safety flags.")
    print("=" * 50)