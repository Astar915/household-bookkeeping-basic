from __future__ import annotations

import unittest

from bookkeeping.region_time import (
    DEFAULT_TIME_ZONE,
    SUPPORTED_TIME_ZONES,
    normalize_time_zone,
    region_timezone,
)


class RegionTimeTests(unittest.TestCase):
    def test_supported_regions_have_iana_zones_and_invalid_values_fall_back(self) -> None:
        self.assertEqual(normalize_time_zone("Asia/Shanghai"), "Asia/Shanghai")
        self.assertEqual(normalize_time_zone("not-a-region"), DEFAULT_TIME_ZONE)
        self.assertEqual(region_timezone("America/New_York").key, "America/New_York")
        self.assertTrue(SUPPORTED_TIME_ZONES)


if __name__ == "__main__":
    unittest.main()
