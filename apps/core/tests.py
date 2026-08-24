from django.test import TestCase

from apps.core.templatetags.ui_extras import basename, initials, stars


class InitialsFilterTests(TestCase):
    def test_two_word_name(self):
        self.assertEqual(initials('Игорь Мельников'), 'ИМ')

    def test_single_word_name(self):
        self.assertEqual(initials('Игорь'), 'И')

    def test_three_word_name_uses_first_two(self):
        self.assertEqual(initials('Игорь Петрович Мельников'), 'ИП')

    def test_empty_value(self):
        self.assertEqual(initials(''), '?')
        self.assertEqual(initials(None), '?')


class BasenameFilterTests(TestCase):
    def test_strips_storage_path(self):
        class FakeFile:
            name = 'orders/specs/2026/08/spec_10482.pdf'

        self.assertEqual(basename(FakeFile()), 'spec_10482.pdf')

    def test_plain_string_without_slash(self):
        class FakeFile:
            name = 'spec.pdf'

        self.assertEqual(basename(FakeFile()), 'spec.pdf')

    def test_empty_value(self):
        self.assertEqual(basename(None), '')
        self.assertEqual(basename(''), '')


class StarsFilterTests(TestCase):
    def test_full_score(self):
        self.assertEqual(stars(5), '★★★★★')

    def test_partial_score(self):
        self.assertEqual(stars(3), '★★★☆☆')

    def test_zero_score(self):
        self.assertEqual(stars(0), '☆☆☆☆☆')

    def test_clamps_out_of_range(self):
        self.assertEqual(stars(9), '★★★★★')
        self.assertEqual(stars(-2), '☆☆☆☆☆')

    def test_invalid_value(self):
        self.assertEqual(stars(None), '')
        self.assertEqual(stars('not-a-number'), '')
