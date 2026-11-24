import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import calc


class AddTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
