import hashlib
import unittest

from tdbox.sign import encode_query, encode_query_value, header_sign


class SignTest(unittest.TestCase):
    def test_header_sign_matches_reference_md5(self):
        ts = "2026-01-01 00:00:00"
        expected = hashlib.md5(("wx-mini" + "wx-minkey" + ts).encode("utf-8")).hexdigest().upper()
        self.assertEqual(header_sign("wx-mini", "wx-minkey", ts), expected)

    def test_header_sign_empty(self):
        self.assertEqual(header_sign("", "", ""), hashlib.md5(b"").hexdigest().upper())

    def test_encode_query_value_wraps_string_in_quotes(self):
        # JSON.stringify("CAN") == '"CAN"', then encodeURIComponent -> %22CAN%22
        self.assertEqual(encode_query_value("CAN"), "%22CAN%22")

    def test_encode_query(self):
        encoded = encode_query({"departure": "CAN", "departDate": "2026-10-22"})
        self.assertEqual(encoded["departure"], "%22CAN%22")
        self.assertEqual(encoded["departDate"], "%222026-10-22%22")


if __name__ == "__main__":
    unittest.main()
