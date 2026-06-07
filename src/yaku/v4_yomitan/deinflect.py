from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class DeinflectionCandidate:
    term: str
    rules: list[str]
    reasons: list[str]


# A list of deinflection rules: (kana_in, kana_out, rules_in, rules_out, reason)
RULES: list[tuple[str, str, set[str], set[str], str]] = []

# 1. Ichidan verbs (v1)
RULES.extend([
    ("て", "る", {"v1"}, {"v1"}, "te"),
    ("た", "る", {"v1"}, {"v1"}, "past"),
    ("たら", "る", {"v1"}, {"v1"}, "conditional"),
    ("たり", "る", {"v1"}, {"v1"}, "representative"),
    ("ます", "る", {"v1"}, {"v1"}, "polite"),
    ("ました", "る", {"v1"}, {"v1"}, "polite past"),
    ("ません", "る", {"v1"}, {"v1"}, "polite negative"),
    ("ましょう", "る", {"v1"}, {"v1"}, "polite volitional"),
    ("ない", "る", {"adj-i"}, {"v1"}, "negative"),
    ("なかった", "る", {"v1"}, {"v1"}, "negative past"),
    ("ず", "る", {"v1"}, {"v1"}, "negative"),
    ("ぬ", "る", {"v1"}, {"v1"}, "negative"),
    ("ん", "る", {"v1"}, {"v1"}, "negative"),
    ("れば", "る", {"v1"}, {"v1"}, "conditional"),
    ("よう", "る", {"v1"}, {"v1"}, "volitional"),
    ("ろ", "る", {"v1"}, {"v1"}, "imperative"),
    ("よ", "る", {"v1"}, {"v1"}, "imperative"),
    ("させる", "る", {"v1"}, {"v1"}, "causative"),
    ("られる", "る", {"v1"}, {"v1"}, "passive or potential"),
    ("たい", "る", {"adj-i"}, {"v1"}, "desire"),
    ("ながら", "る", {"v1"}, {"v1"}, "while"),
])

# 2. i-adjectives (adj-i)
RULES.extend([
    ("かった", "い", {"adj-i"}, {"adj-i"}, "past"),
    ("くて", "い", {"adj-i"}, {"adj-i"}, "te"),
    ("くない", "い", {"adj-i"}, {"adj-i"}, "negative"),
    ("くなかった", "い", {"adj-i"}, {"adj-i"}, "negative past"),
    ("ければ", "い", {"adj-i"}, {"adj-i"}, "conditional"),
    ("そう", "い", {"adj-i"}, {"adj-i"}, "conjecture"),
])

# 3. Godan verbs (v5)
GODAN_ENDINGS = ["う", "く", "ぐ", "す", "つ", "ぬ", "ぶ", "む", "る"]
GODAN_I = ["い", "き", "ぎ", "し", "ち", "に", "び", "み", "り"]
GODAN_A = ["わ", "か", "が", "さ", "た", "な", "ば", "ま", "ら"]
GODAN_O = ["お", "こ", "ご", "そ", "と", "の", "ぼ", "も", "ろ"]
GODAN_E = ["え", "け", "げ", "せ", "て", "ね", "べ", "め", "れ"]

# Polite forms
for ending, i_row in zip(GODAN_ENDINGS, GODAN_I):
    RULES.append((i_row + "ます", ending, {"v5"}, {"v5"}, "polite"))
    RULES.append((i_row + "ました", ending, {"v5"}, {"v5"}, "polite past"))
    RULES.append((i_row + "ません", ending, {"v5"}, {"v5"}, "polite negative"))
    RULES.append((i_row + "ましょう", ending, {"v5"}, {"v5"}, "polite volitional"))
    RULES.append((i_row + "ながら", ending, {"v5"}, {"v5"}, "while"))

# Negative, passive, causative
for ending, a_row in zip(GODAN_ENDINGS, GODAN_A):
    RULES.append((a_row + "ない", ending, {"adj-i"}, {"v5"}, "negative"))
    RULES.append((a_row + "なかった", ending, {"v5"}, {"v5"}, "negative past"))
    RULES.append((a_row + "ず", ending, {"v5"}, {"v5"}, "negative"))
    RULES.append((a_row + "ぬ", ending, {"v5"}, {"v5"}, "negative"))
    RULES.append((a_row + "ん", ending, {"v5"}, {"v5"}, "negative"))
    RULES.append((a_row + "れる", ending, {"v1"}, {"v5"}, "passive or potential"))
    RULES.append((a_row + "せる", ending, {"v1"}, {"v5"}, "causative"))
    RULES.append((a_row + "られる", ending, {"v1"}, {"v5"}, "passive or potential"))
    RULES.append((a_row + "させる", ending, {"v1"}, {"v5"}, "causative"))

# Volitional
for ending, o_row in zip(GODAN_ENDINGS, GODAN_O):
    RULES.append((o_row + "う", ending, {"v5"}, {"v5"}, "volitional"))

# Conditional, imperative, potential
for ending, e_row in zip(GODAN_ENDINGS, GODAN_E):
    RULES.append((e_row + "ば", ending, {"v5"}, {"v5"}, "conditional"))
    RULES.append((e_row, ending, {"v5"}, {"v5"}, "imperative"))
    RULES.append((e_row + "る", ending, {"v1"}, {"v5"}, "potential"))

# Te / Ta forms (euphony)
for ending in ["う", "つ", "る"]:
    RULES.append(("って", ending, {"v5"}, {"v5"}, "te"))
    RULES.append(("った", ending, {"v5"}, {"v5"}, "past"))
    RULES.append(("ったら", ending, {"v5"}, {"v5"}, "conditional"))
    RULES.append(("ったり", ending, {"v5"}, {"v5"}, "representative"))

for ending in ["む", "ぶ", "ぬ"]:
    RULES.append(("んで", ending, {"v5"}, {"v5"}, "te"))
    RULES.append(("んだ", ending, {"v5"}, {"v5"}, "past"))
    RULES.append(("んだら", ending, {"v5"}, {"v5"}, "conditional"))
    RULES.append(("んだり", ending, {"v5"}, {"v5"}, "representative"))

RULES.extend([
    ("いて", "く", {"v5"}, {"v5"}, "te"),
    ("いた", "く", {"v5"}, {"v5"}, "past"),
    ("いたら", "く", {"v5"}, {"v5"}, "conditional"),
    ("いたり", "く", {"v5"}, {"v5"}, "representative"),
    # 行く exception
    ("って", "く", {"v5"}, {"v5"}, "te"),
    ("った", "く", {"v5"}, {"v5"}, "past"),
    ("いで", "ぐ", {"v5"}, {"v5"}, "te"),
    ("いだ", "ぐ", {"v5"}, {"v5"}, "past"),
    ("いだら", "ぐ", {"v5"}, {"v5"}, "conditional"),
    ("いだり", "ぐ", {"v5"}, {"v5"}, "representative"),
    ("して", "す", {"v5"}, {"v5"}, "te"),
    ("した", "す", {"v5"}, {"v5"}, "past"),
    ("したら", "す", {"v5"}, {"v5"}, "conditional"),
    ("したり", "す", {"v5"}, {"v5"}, "representative"),
])

# 4. Suru verbs (vs)
RULES.extend([
    ("して", "する", {"vs"}, {"vs"}, "te"),
    ("した", "する", {"vs"}, {"vs"}, "past"),
    ("したら", "する", {"vs"}, {"vs"}, "conditional"),
    ("したり", "する", {"vs"}, {"vs"}, "representative"),
    ("します", "する", {"vs"}, {"vs"}, "polite"),
    ("しました", "する", {"vs"}, {"vs"}, "polite past"),
    ("しません", "する", {"vs"}, {"vs"}, "polite negative"),
    ("しましょう", "する", {"vs"}, {"vs"}, "polite volitional"),
    ("しない", "する", {"adj-i"}, {"vs"}, "negative"),
    ("しなかった", "する", {"vs"}, {"vs"}, "negative past"),
    ("せず", "する", {"vs"}, {"vs"}, "negative"),
    ("され", "する", {"v1"}, {"vs"}, "passive or potential"),
    ("させ", "する", {"v1"}, {"vs"}, "causative"),
    ("すれ", "する", {"vs"}, {"vs"}, "conditional"),
    ("しよ", "する", {"vs"}, {"vs"}, "volitional"),
    ("しろ", "する", {"vs"}, {"vs"}, "imperative"),
    ("せよ", "する", {"vs"}, {"vs"}, "imperative"),
])

# 5. Kuru verbs (vk)
RULES.extend([
    ("来て", "来る", {"vk"}, {"vk"}, "te"),
    ("来た", "来る", {"vk"}, {"vk"}, "past"),
    ("来たら", "来る", {"vk"}, {"vk"}, "conditional"),
    ("来たり", "来る", {"vk"}, {"vk"}, "representative"),
    ("来ます", "来る", {"vk"}, {"vk"}, "polite"),
    ("来ました", "来る", {"vk"}, {"vk"}, "polite past"),
    ("来ません", "来る", {"vk"}, {"vk"}, "polite negative"),
    ("来ましょう", "来る", {"vk"}, {"vk"}, "polite volitional"),
    ("来ない", "来る", {"adj-i"}, {"vk"}, "negative"),
    ("来なかった", "来る", {"vk"}, {"vk"}, "negative past"),
    ("来られ", "来る", {"v1"}, {"vk"}, "passive or potential"),
    ("来させ", "来る", {"v1"}, {"vk"}, "causative"),
    ("来よ", "来る", {"vk"}, {"vk"}, "volitional"),
    
    ("きて", "くる", {"vk"}, {"vk"}, "te"),
    ("きた", "くる", {"vk"}, {"vk"}, "past"),
    ("kitaら", "くる", {"vk"}, {"vk"}, "conditional"), # note: standard hiragana is きたら
    ("きたら", "くる", {"vk"}, {"vk"}, "conditional"),
    ("きたり", "くる", {"vk"}, {"vk"}, "representative"),
    ("きます", "くる", {"vk"}, {"vk"}, "polite"),
    ("きました", "くる", {"vk"}, {"vk"}, "polite past"),
    ("きません", "くる", {"vk"}, {"vk"}, "polite negative"),
    ("きましょう", "くる", {"vk"}, {"vk"}, "polite volitional"),
    ("こない", "くる", {"adj-i"}, {"vk"}, "negative"),
    ("こなかった", "くる", {"vk"}, {"vk"}, "negative past"),
    ("こられ", "くる", {"v1"}, {"vk"}, "passive or potential"),
    ("こさせ", "くる", {"v1"}, {"vk"}, "causative"),
    ("こよ", "くる", {"vk"}, {"vk"}, "volitional"),
])


def deinflect(surface: str) -> list[DeinflectionCandidate]:
    """Recursively deinflects a Japanese word returning all possible root form candidates."""
    initial_rules = {"v1", "v5", "adj-i", "vs", "vk"}
    candidates = [DeinflectionCandidate(surface, list(initial_rules), [])]
    
    queue = [(surface, initial_rules, [])]
    visited = {(surface, frozenset(initial_rules))}
    
    while queue:
        curr_term, curr_rules, curr_reasons = queue.pop(0)
        
        for kana_in, kana_out, r_in, r_out, reason in RULES:
            if curr_term.endswith(kana_in):
                if r_in.intersection(curr_rules):
                    new_term = curr_term[:-len(kana_in)] + kana_out
                    if not new_term:
                        continue
                    
                    new_rules = r_out
                    new_reasons = curr_reasons + [reason]
                    state = (new_term, frozenset(new_rules))
                    if state not in visited:
                        visited.add(state)
                        candidate = DeinflectionCandidate(new_term, list(new_rules), new_reasons)
                        candidates.append(candidate)
                        queue.append((new_term, new_rules, new_reasons))
                        
    return candidates
