import random
import string

THEME_WORDS = ["CYBER", "NEON", "ARENA", "DUEL", "NOVA", "PULSE", "GRID", "ORBIT"]
PLAYER_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars (0/O, 1/I)


def generate_room_code() -> str:
    theme = random.choice(THEME_WORDS)
    digits = "".join(random.choices(string.digits, k=6))
    return f"NDUO-{theme}-{digits}"


def generate_player_id() -> str:
    suffix = "".join(random.choices(PLAYER_ID_ALPHABET, k=6))
    return f"NDUO-{suffix}"
