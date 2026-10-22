import random
import unittest

from tdbox.transform import (
    BLACKBOX_LENGTH,
    INSERT_ALPHABET,
    TOKEN_LENGTH,
    token_id_to_black_box,
    validate_black_box,
)


def _token() -> str:
    # 23 chars, first and last hex.
    return "2" + "B" * (TOKEN_LENGTH - 2) + "f"


class TransformTest(unittest.TestCase):
    def test_length(self):
        self.assertEqual(len(token_id_to_black_box(_token(), random.Random(0))), BLACKBOX_LENGTH)

    def test_roundtrip(self):
        rng = random.Random(42)
        tokens = [
            "2" + "B" * (TOKEN_LENGTH - 2) + "f",
            "a" + "C" * (TOKEN_LENGTH - 2) + "0",
            "f" + "9" * (TOKEN_LENGTH - 2) + "e",
        ]
        for token in tokens:
            self.assertTrue(validate_black_box(token, token_id_to_black_box(token, rng)))

    def test_first_char_mapping(self):
        # '2' is index 2 in "0123456789abcdef" -> index 2 in "ghijklmnopqrstuv" -> 'i'
        bb = token_id_to_black_box(_token(), random.Random(0))
        self.assertEqual(bb[0], "i")

    def test_inserted_slots_hold_base62_chars(self):
        bb = token_id_to_black_box(_token(), random.Random(0))
        # The three inserted slots carry a random base62 char (which may overlap
        # the token's own alphabet, so we assert membership, not difference).
        for index in (4, 15, 24):
            self.assertIn(bb[index], INSERT_ALPHABET)

    def test_deterministic_with_seed(self):
        token = _token()
        self.assertEqual(
            token_id_to_black_box(token, random.Random(0)),
            token_id_to_black_box(token, random.Random(0)),
        )

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValueError):
            token_id_to_black_box("2" + "B" * (TOKEN_LENGTH - 3) + "f")

    def test_rejects_non_hex_first_char(self):
        with self.assertRaises(ValueError):
            token_id_to_black_box("X" + "B" * (TOKEN_LENGTH - 2) + "f")

    def test_rejects_non_hex_last_char(self):
        with self.assertRaises(ValueError):
            token_id_to_black_box("2" + "B" * (TOKEN_LENGTH - 2) + "Z")

    def test_validate_rejects_wrong_length(self):
        self.assertFalse(validate_black_box(_token(), "x" * (BLACKBOX_LENGTH - 1)))


if __name__ == "__main__":
    unittest.main()
