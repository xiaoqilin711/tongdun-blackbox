import random
import unittest

from tdbox.session import make_sid, make_token


class SessionTest(unittest.TestCase):
    def test_make_sid_structure(self):
        sid = make_sid(1700000000, random.Random(0))
        self.assertTrue(sid.startswith("TS4"))
        # TS4(3) + base61(6) + checksum(2) + tail(8) = 19 chars
        self.assertEqual(len(sid), 19)

    def test_make_token_structure(self):
        token = make_token(1700000000, random.Random(0))
        self.assertTrue(token.startswith("TR4"))
        # TR4(3) + base61(6) + tail(3) + tail(7) + checksum(2) = 21 chars
        self.assertEqual(len(token), 21)

    def test_deterministic_with_seed(self):
        self.assertEqual(make_sid(1700000000, random.Random(0)), make_sid(1700000000, random.Random(0)))
        self.assertEqual(make_token(1700000000, random.Random(0)), make_token(1700000000, random.Random(0)))


if __name__ == "__main__":
    unittest.main()
