import unittest

from agent import verify


class ParseNumberTests(unittest.TestCase):
    def test_english_format(self):
        self.assertEqual(verify.parse_number("13,221,498.11"), 13221498.11)

    def test_vietnamese_format(self):
        self.assertEqual(verify.parse_number("13.221.498,11"), 13221498.11)

    def test_plain_decimal(self):
        self.assertEqual(verify.parse_number("12.5"), 12.5)

    def test_thousands_only(self):
        self.assertEqual(verify.parse_number("1,234"), 1234.0)

    def test_negative(self):
        self.assertEqual(verify.parse_number("-42.5"), -42.5)


class UnsupportedNumbersTests(unittest.TestCase):
    def test_number_present_in_data_is_supported(self):
        pool = [13221498.11, 110197.0]
        self.assertEqual(verify.unsupported_numbers("Doanh thu là 13.221.498,11", pool), [])

    def test_invented_number_is_flagged(self):
        pool = [13221498.11]
        issues = verify.unsupported_numbers("Doanh thu là 99.999.999", pool)
        self.assertEqual(issues, ["99.999.999"])

    def test_small_numbers_and_years_are_ignored(self):
        pool = [500.0]
        self.assertEqual(verify.unsupported_numbers("Năm 2017 có 3 tháng", pool), [])

    def test_small_relative_difference_is_tolerated(self):
        pool = [1000.0]
        self.assertEqual(verify.unsupported_numbers("Khoảng 1.003", pool), [])


class DataValuesTests(unittest.TestCase):
    def test_collects_numeric_cells_only(self):
        rows = [[["electronics", 10, 2.5, True, None]]]
        self.assertEqual(sorted(verify.data_values(rows)), [2.5, 10.0])


if __name__ == "__main__":
    unittest.main()
