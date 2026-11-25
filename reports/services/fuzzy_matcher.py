"""RapidFuzz yordamida o'xshash tovar nomlarini birlashtirish moduli."""

from rapidfuzz import fuzz, process


def deduplicate_names(names: list[str], threshold: int = 92) -> tuple[dict[str, str], int]:
    """
    O'xshash tovar nomlarini (>= threshold%) bitta kanonik nomga birlashtiradi.
    Qaytaradi: ({asl_nom: kanonik_nom}, birlashtirilgan_nomlar_soni).
    """
    canonicals: list[str] = []
    mapping: dict[str, str] = {}
    merged_count = 0

    for raw in names:
        clean = " ".join(str(raw or "").split())
        if not clean:
            mapping[raw] = ""
            continue
        if not canonicals:
            canonicals.append(clean)
            mapping[raw] = clean
            continue

        match = process.extractOne(
            clean,
            canonicals,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
        )
        if match:
            canonical = match[0]
            mapping[raw] = canonical
            if canonical != clean:
                merged_count += 1
        else:
            canonicals.append(clean)
            mapping[raw] = clean

    return mapping, merged_count
