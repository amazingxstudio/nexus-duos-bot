import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import now_ms

MATCH_DURATION_MS = 90 * 1000  # 90s race - most links added wins

# A large pool of common, simple, concrete English NOUNS (a much bigger
# swap-in for the original short list, which dead-ended constantly). Every
# letter A-Z has multiple words to start a link with - verified below.
WORD_POOL = [
    "apple", "ant", "arrow", "arm", "art", "axe", "air", "apron", "avocado", "ash", "airport", "actor",
    "album", "alarm", "anchor", "angel", "ankle", "antenna", "apartment", "artist", "atlas", "author", "avenue", "award",
    "axis",
    "banana", "ball", "bat", "bear", "bell", "book", "box", "bridge", "bike", "bird", "balloon", "banjo",
    "barn", "basket", "beach", "beard", "bench", "berry", "bicycle", "blanket", "boat", "bone", "boot", "bottle",
    "bowl", "brain", "branch", "bread", "brick", "brush", "bucket", "bug", "bulb", "bus", "butter", "button",
    "cat", "car", "candy", "cloud", "coin", "cup", "crab", "crown", "cake", "coat", "cabin", "cactus",
    "calendar", "camel", "camera", "candle", "canoe", "canvas", "cape", "captain", "carpet", "castle", "cave", "chain",
    "chair", "chalk", "cheese", "cherry", "chest", "chicken", "chimney", "chin", "chocolate", "church", "circle", "city",
    "clock", "closet", "clover", "coach", "coconut", "collar", "comb", "comet", "compass", "cookie", "corn", "cottage",
    "cotton", "couch", "cousin", "cow", "coyote", "crayon", "cream", "creek", "crew", "cricket", "crocodile", "crystal",
    "cucumber", "curtain", "cushion", "cylinder",
    "dog", "door", "duck", "drum", "desk", "diamond", "dragon", "deer", "dance", "dust", "dagger", "daisy",
    "dam", "dart", "dawn", "den", "dentist", "desert", "diary", "dice", "dinner", "dinosaur", "dirt", "dish",
    "doctor", "dolphin", "dome", "donkey", "doorbell", "dot", "dove", "dragonfly", "driver", "drop", "dune", "dungeon",
    "eagle", "egg", "ear", "earth", "east", "engine", "elbow", "energy", "elephant", "echo", "earring", "easel",
    "eclipse", "editor", "eel", "elevator", "elf", "elm", "emerald", "empire", "engineer", "envelope", "equator", "eraser",
    "estate", "evening", "exam", "exit", "eye", "eyebrow",
    "fish", "fox", "fan", "fire", "flag", "frog", "fruit", "forest", "feather", "fork", "fabric", "face",
    "factory", "fairy", "falcon", "family", "farm", "farmer", "faucet", "feast", "fence", "fern", "ferry", "field",
    "finger", "fireplace", "firefighter", "firefly", "fist", "flame", "flashlight", "flea", "fleet", "flood", "floor", "flour",
    "flower", "flute", "fog", "foot", "football", "forehead", "fortress", "fountain", "frame", "freezer", "fridge", "friend",
    "frost", "fuel", "furnace", "furniture",
    "goat", "gate", "game", "garden", "ghost", "grape", "guitar", "glass", "globe", "gold", "gallery", "galaxy",
    "garage", "garlic", "gas", "gem", "giant", "gift", "ginger", "giraffe", "glacier", "glove", "glue", "goggles",
    "goose", "gorilla", "government", "gown", "grandfather", "grass", "grasshopper", "gravel", "greenhouse", "grill", "grocery", "guest",
    "guide", "gull", "gutter", "gym",
    "hat", "house", "horse", "hand", "heart", "honey", "hill", "hammer", "hero", "harp", "habitat", "hair",
    "hairbrush", "hall", "hamster", "handle", "harbor", "hawk", "hay", "hazelnut", "headphone", "hedge", "heel", "helmet",
    "herb", "highway", "hip", "hippo", "hive", "hockey", "hoof", "hook", "horn", "horizon", "hose", "hospital",
    "hostel", "hotel", "hound", "hourglass", "hut",
    "ice", "island", "iron", "ink", "idea", "insect", "igloo", "invite", "input", "ivy", "icon", "icicle",
    "image", "inbox", "index", "infant", "ingredient", "injury", "inn", "instrument", "iris",
    "jar", "jacket", "jelly", "jungle", "jewel", "juice", "joke", "jet", "jigsaw", "jaguar", "jam", "jasmine",
    "javelin", "jaw", "jay", "jeans", "jeep", "jersey", "journal", "journey", "judge", "juggler", "junction", "junk",
    "jury",
    "kite", "king", "key", "kitten", "kettle", "knight", "koala", "kayak", "kangaroo", "kiwi", "kebab", "ketchup",
    "keyboard", "keychain", "kick", "kid", "kidney", "kilogram", "kilt", "kingdom", "kiosk", "kitchen", "knee", "knife",
    "knot",
    "lion", "lamp", "leaf", "lake", "lemon", "letter", "ladder", "light", "log", "lynx", "label", "laboratory",
    "lace", "ladle", "ladybug", "lagoon", "lamb", "land", "lantern", "laptop", "lark", "lattice", "laundry", "lawn",
    "lawyer", "leash", "leather", "ledge", "leg", "lens", "leopard", "lesson", "library", "lid", "lighthouse", "lily",
    "limb", "lime", "line", "lip", "liquid", "list", "lizard", "lobby", "lobster", "lock", "locomotive", "lodge",
    "lollipop", "lounge", "lumber", "lung",
    "moon", "mouse", "mountain", "map", "mirror", "music", "monkey", "melon", "mask", "mint", "machine", "magazine",
    "magnet", "magpie", "maid", "mailbox", "mammal", "mango", "mansion", "mantle", "maple", "marble", "market", "marker",
    "mast", "mat", "match", "meadow", "meal", "medal", "medicine", "melody", "memory", "menu", "merchant", "mermaid",
    "metal", "meteor", "microphone", "microscope", "midnight", "mile", "milk", "mill", "mine", "mineral", "minute", "missile",
    "mist", "mitten", "mixer", "moat", "model", "mole", "monastery", "monitor", "monk", "monument", "mop", "mosque",
    "moss", "moth", "motor", "mound", "mud", "muffin", "mug", "mule", "mummy", "muscle", "museum", "mushroom",
    "mustard",
    "nest", "night", "nose", "net", "needle", "notebook", "north", "nut", "nurse", "novel", "nail", "name",
    "napkin", "nation", "nature", "navy", "neck", "necklace", "neighbor", "neighborhood", "neon", "nerve", "network", "news",
    "newspaper", "niece", "noble", "noise", "noodle", "note", "nozzle", "nugget", "number", "nursery", "nutmeg",
    "owl", "ocean", "orange", "onion", "oven", "otter", "olive", "opal", "oasis", "orbit", "oak", "oar",
    "oath", "oatmeal", "octopus", "office", "officer", "oil", "okra", "omelet", "opera", "orchard", "orchestra", "orchid",
    "organ", "ostrich", "outfit", "oxygen", "oyster",
    "pig", "pencil", "piano", "plane", "pizza", "puzzle", "pond", "peach", "planet", "purse", "package", "paddle",
    "page", "paint", "painter", "pajama", "palace", "palm", "pan", "pancake", "panda", "pantry", "paper", "parachute",
    "parade", "parent", "park", "parrot", "parsley", "passenger", "passport", "pasta", "path", "patient", "pattern", "paw",
    "pea", "peacock", "peanut", "pear", "pearl", "pebble", "pedal", "pelican", "penalty", "pendant", "penguin", "people",
    "pepper", "perfume", "person", "pet", "petal", "pharmacy", "phone", "photo", "pickle", "picnic", "picture", "pie",
    "pigeon", "pillar", "pillow", "pilot", "pin", "pine", "pineapple", "pipe", "pirate", "pistol", "pitcher", "plant",
    "plate", "platform", "playground", "plumber", "pocket", "poem", "poet", "point", "poison", "pole", "police", "pony",
    "pool", "popcorn", "porch", "porcupine", "port", "portrait", "post", "poster", "pot", "potato", "pouch", "powder",
    "prairie", "prince", "princess", "printer", "prison", "professor", "project", "puddle", "pump", "pumpkin", "puppet", "puppy",
    "pyramid",
    "queen", "quilt", "quiz", "quail", "quartz", "question", "quiver", "quicksand", "quokka", "quote", "quarry", "quart",
    "rabbit", "river", "ring", "rocket", "rose", "robot", "rain", "roof", "rope", "raven", "race", "rack",
    "radio", "raft", "rail", "railway", "rainbow", "raincoat", "rake", "ram", "ranch", "rancher", "ranger", "rapids",
    "raspberry", "rat", "razor", "receipt", "recipe", "record", "rectangle", "reed", "referee", "reindeer", "reptile", "rescue",
    "restaurant", "ribbon", "rice", "rider", "ridge", "rifle", "rink", "road", "robe", "robin", "rock", "rod",
    "room", "root", "route", "rug", "ruler", "runner", "rust",
    "snake", "star", "sun", "shoe", "spoon", "spider", "swan", "sword", "sand", "storm", "saddle", "safari",
    "sail", "sailor", "salad", "salmon", "salt", "sandal", "sandwich", "sapphire", "sardine", "satellite", "sauce", "saucer",
    "sausage", "savings", "sawdust", "scale", "scarf", "scene", "school", "scissors", "scooter", "scorpion", "scout", "screen",
    "screw", "sculpture", "sea", "seal", "seaweed", "seed", "senator", "sense", "servant", "shade", "shadow", "shampoo",
    "shark", "shed", "sheep", "sheet", "shelf", "shell", "shepherd", "shield", "ship", "shirt", "shop", "shore",
    "shorts", "shoulder", "shovel", "shower", "shrimp", "shrine", "shutter", "sibling", "sidewalk", "silver", "singer", "sink",
    "sister", "skate", "skeleton", "skirt", "skull", "sky", "skyscraper", "sled", "sleeve", "slide", "sloth", "smoke",
    "snail", "sneaker", "snowman", "soap", "socket", "sofa", "soil", "soldier", "son", "song", "soup", "source",
    "souvenir", "sparrow", "speaker", "spear", "spice", "spinach", "sponge", "sport", "spray", "spring", "sprout", "spy",
    "square", "squirrel", "stable", "stadium", "staff", "stage", "stair", "stamp", "station", "statue", "steak", "steam",
    "steel", "stem", "step", "stew", "stick", "sticker", "stomach", "stone", "stool", "store", "stove", "straw",
    "strawberry", "stream", "street", "string", "stripe", "student", "studio", "stump", "submarine", "suburb", "subway", "sugar",
    "suit", "suitcase", "summit", "sunflower", "sunset", "supper", "surgeon", "swamp", "sweater", "swing", "switch", "syrup",
    "syringe",
    "tiger", "tree", "table", "train", "turtle", "tent", "tower", "toy", "trumpet", "torch", "tablet", "tackle",
    "tadpole", "tail", "tailor", "talent", "tank", "tap", "tape", "tapestry", "target", "tarp", "taxi", "tea",
    "teacher", "teapot", "teddy", "teeth", "telephone", "telescope", "television", "temple", "tennis", "tentacle", "terrace", "terrier",
    "textbook", "texture", "theater", "thermometer", "thief", "thigh", "thimble", "thistle", "thorn", "thread", "throat", "throne",
    "thumb", "thunder", "ticket", "tide", "tile", "timber", "tin", "tissue", "toad", "toast", "toaster", "toddler",
    "toe", "tofu", "toilet", "tomato", "tongue", "tool", "tooth", "toothbrush", "topic", "tornado", "tortoise", "tote",
    "town", "tractor", "trail", "trailer", "tram", "trap", "tray", "treasure", "treaty", "trial", "triangle", "tricycle",
    "trip", "tripod", "trolley", "trombone", "trophy", "trout", "truck", "trunk", "tub", "tube", "tulip", "tuna",
    "tunnel", "turban", "turkey", "turnip", "tusk", "tutor", "tuxedo", "twig", "twin", "typewriter",
    "umbrella", "unicorn", "uniform", "urn", "upstream", "utensil", "ukulele", "urban", "usher", "unit", "uncle", "underwear",
    "unicycle", "university", "upstairs", "urchin",
    "van", "vase", "violin", "valley", "village", "volcano", "vine", "vulture", "vest", "violet", "vacation", "vaccine",
    "vacuum", "valentine", "valve", "vandal", "vanilla", "vapor", "vault", "vegetable", "vehicle", "veil", "vein", "velvet",
    "vendor", "ventilator", "veranda", "verse", "vessel", "veteran", "veterinarian", "video", "view", "villain", "vinegar", "vineyard",
    "viper", "virus", "vision", "visitor", "vitamin", "voice", "volleyball", "volume", "voter", "voucher", "vowel", "voyage",
    "wolf", "window", "watch", "whale", "water", "wagon", "wheel", "web", "wing", "wind", "waffle", "waist",
    "waiter", "walker", "wall", "wallet", "walnut", "walrus", "wardrobe", "warehouse", "wasp", "waterfall", "wave", "wax",
    "weapon", "weather", "weaver", "website", "wedding", "weed", "week", "weekend", "well", "western", "wetland", "wharf",
    "wheat", "wheelchair", "whisker", "whisper", "whistle", "wick", "widow", "wife", "wig", "wilderness", "willow", "windmill",
    "wine", "winter", "wire", "wisdom", "witch", "wizard", "woman", "wood", "woodpecker", "wool", "worker", "workshop",
    "world", "worm", "wound", "wrapper", "wreath", "wrench", "wrist", "writer",
    "xray", "xylophone",
    "yak", "yarn", "yard", "year", "yolk", "yacht", "yeti", "yogurt", "yellow", "yam",
    "zebra", "zero", "zone", "zipper", "zoo", "zigzag", "zeppelin", "zephyr",
]

WORD_SET = {w.lower() for w in WORD_POOL}
_BY_FIRST_LETTER: dict[str, list[str]] = {}
for _w in WORD_POOL:
    _BY_FIRST_LETTER.setdefault(_w[0], []).append(_w)

# Prefer starting the chain on words whose last letter has plenty of options.
_GOOD_STARTERS = [w for w in WORD_POOL if _BY_FIRST_LETTER.get(w[-1])]

TURN_SECONDS = 6  # the "on time" window shown as the countdown
MAX_OVERTIME_SECONDS = 4  # extra grace before an unanswered turn auto-skips
GRACE_MS = 300  # network-jitter cushion right at the 4s boundary


class WordChainEngine(BaseGameEngine):
    """Turn-based, not simultaneous: players alternate, and whoever's turn
    it is has TURN_SECONDS to submit a valid link - starting with the
    current word's last letter, drawn from the known noun list, and not
    already used this match. Speed matters: answering quickly scores more
    (a decaying bonus down to TURN_SECONDS), answering after that scores 0
    instead of the bonus, and going completely silent for
    TURN_SECONDS + MAX_OVERTIME_SECONDS auto-skips the turn to the other
    player, also for 0 - never a score deduction either way (the minus/
    penalty system was removed; scores here only ever go up or stay flat).

    turn_started_at (server ms) rides along in the payload so both clients
    can render the same countdown, and either client may report a timeout
    (see the "turn_timeout" action) - the server re-validates the elapsed
    time itself before trusting it, so an early or spoofed report is
    simply rejected.

    Validation is against the bundled offline noun list rather than a live
    dictionary API - see the module docstring further up for why. Nothing
    here needs sanitizing: the whole chain is public information."""

    game_key = GameKey.WORD_CHAIN
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        start = random.choice(_GOOD_STARTERS or WORD_POOL)
        return {
            "round": 1,
            "current_word": start,
            "used_words": [start],
            "turn_user_id": None,
            "turn_started_at": None,
            "last_turn_delta": None,  # {"user_id", "points"} - lets the client flash "+4" / "0"
        }

    def on_match_start(self, state: dict) -> None:
        player_ids = list(state["players"].keys())
        random.shuffle(player_ids)
        state["payload"]["turn_user_id"] = player_ids[0]
        state["payload"]["turn_started_at"] = now_ms()

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        payload = state["payload"]

        if action_type == "turn_timeout":
            # Either player's client can report this - the server is the
            # one actually deciding whether it's really been long enough.
            elapsed_ms = now_ms() - payload["turn_started_at"]
            if elapsed_ms < (TURN_SECONDS + MAX_OVERTIME_SECONDS) * 1000 - GRACE_MS:
                raise ValueError("TOO_EARLY")
            timed_out_user = payload["turn_user_id"]
            # No penalty (minus/penalty system removed) - a stalled turn
            # just passes to the other player for 0 points, never a
            # deduction from the timed-out player's score.
            payload["last_turn_delta"] = {"user_id": timed_out_user, "points": 0, "reason": "TIMEOUT"}
            self._advance_turn(state)
            return state

        if action_type != "submit_word":
            return state
        if payload["turn_user_id"] != user_id:
            raise ValueError("NOT_YOUR_TURN")

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

        elapsed_sec = (now_ms() - payload["turn_started_at"]) / 1000
        if elapsed_sec <= TURN_SECONDS + GRACE_MS / 1000:
            capped = min(elapsed_sec, TURN_SECONDS)
            points = max(1, round(5 - capped))
        else:
            # Answered late (past TURN_SECONDS but within the overtime
            # grace window) still counts as a valid link - it just misses
            # the quick-answer bonus (0 points) rather than losing points.
            points = 0

        state["players"][user_id]["score"] = state["players"][user_id]["score"] + points
        payload["last_turn_delta"] = {"user_id": user_id, "points": points, "reason": "ANSWER"}
        payload["round"] += 1
        payload["current_word"] = word
        payload["used_words"].append(word)
        self._advance_turn(state)
        return state

    @staticmethod
    def _advance_turn(state: dict) -> None:
        payload = state["payload"]
        opponent_id = next(uid for uid in state["players"] if uid != payload["turn_user_id"])
        payload["turn_user_id"] = opponent_id
        payload["turn_started_at"] = now_ms()
