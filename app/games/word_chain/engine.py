import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most links added wins

# A curated pool of common, simple English words with reasonable coverage
# across starting letters so the chain rarely dead-ends. All lowercase.
WORD_POOL = [
    "apple", "ant", "arrow", "arm", "art", "axe", "air", "apron", "avocado", "ash",
    "banana", "ball", "bat", "bear", "bell", "book", "box", "bridge", "bike", "bird",
    "cat", "car", "candy", "cloud", "coin", "cup", "crab", "crown", "cake", "coat",
    "dog", "door", "duck", "drum", "desk", "diamond", "dragon", "deer", "dance", "dust",
    "eagle", "egg", "ear", "earth", "east", "engine", "elbow", "energy", "elephant", "echo",
    "fish", "fox", "fan", "fire", "flag", "frog", "fruit", "forest", "feather", "fork",
    "goat", "gate", "game", "garden", "ghost", "grape", "guitar", "glass", "globe", "gold",
    "hat", "house", "horse", "hand", "heart", "honey", "hill", "hammer", "hero", "harp",
    "ice", "island", "iron", "ink", "idea", "insect", "igloo", "invite", "input", "ivy",
    "jar", "jacket", "jelly", "jungle", "jewel", "juice", "joke", "jet", "jigsaw", "jaguar",
    "kite", "king", "key", "kitten", "kettle", "knight", "koala", "kayak", "kangaroo", "kiwi",
    "lion", "lamp", "leaf", "lake", "lemon", "letter", "ladder", "light", "log", "lynx",
    "moon", "mouse", "mountain", "map", "mirror", "music", "monkey", "melon", "mask", "mint",
    "nest", "night", "nose", "net", "needle", "notebook", "north", "nut", "nurse", "novel",
    "owl", "ocean", "orange", "onion", "oven", "otter", "olive", "opal", "oasis", "orbit",
    "pig", "pencil", "piano", "plane", "pizza", "puzzle", "pond", "peach", "planet", "purse",
    "queen", "quilt", "quiz", "quail", "quartz", "question", "quiver", "quicksand", "quokka", "quote",
    "rabbit", "river", "ring", "rocket", "rose", "robot", "rain", "roof", "rope", "raven",
    "snake", "star", "sun", "shoe", "spoon", "spider", "swan", "sword", "sand", "storm",
    "tiger", "tree", "table", "train", "turtle", "tent", "tower", "toy", "trumpet", "torch",
    "umbrella", "unicorn", "uniform", "urn", "upstream", "utensil", "ukulele", "urban", "usher", "unit",
    "van", "vase", "violin", "valley", "village", "volcano", "vine", "vulture", "vest", "violet",
    "wolf", "window", "watch", "whale", "water", "wagon", "wheel", "web", "wing", "wind",
    "xray", "xylophone",
    "yak", "yarn", "yard", "year", "yolk", "yacht", "yeti", "yogurt", "yellow", "yell",
    "zebra", "zero", "zone", "zipper", "zoo", "zigzag",
]

WORD_SET = {w.lower() for w in WORD_POOL}
_BY_FIRST_LETTER: dict[str, list[str]] = {}
for _w in WORD_POOL:
    _BY_FIRST_LETTER.setdefault(_w[0], []).append(_w)

# Prefer starting the chain on words whose last letter has plenty of options.
_GOOD_STARTERS = [w for w in WORD_POOL if _BY_FIRST_LETTER.get(w[-1])]


class WordChainEngine(BaseGameEngine):
    """A shared chain: whoever is first to submit a valid word - starting
    with the current word's last letter, drawn from the known word list,
    and not already used this match - extends the chain and scores a
    point. Everything needed to render the current word is already public,
    so nothing needs sanitizing here."""

    game_key = GameKey.WORD_CHAIN
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        start = random.choice(_GOOD_STARTERS or WORD_POOL)
        return {"round": 1, "current_word": start, "used_words": [start]}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_word":
            return state
        payload = state["payload"]

        word = data.get("word")
        if not isinstance(word, str):
            raise ValueError("INVALID_WORD")
        word = word.strip().lower()

        if not word or not word.isalpha():
            raise ValueError("INVALID_WORD")
        if word[0] != payload["current_word"][-1]:
            raise ValueError("WRONG_LETTER")
        if word not in WORD_SET:
            raise ValueError("UNKNOWN_WORD")
        if word in payload["used_words"]:
            raise ValueError("ALREADY_USED")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        payload["current_word"] = word
        payload["used_words"].append(word)
        return state
