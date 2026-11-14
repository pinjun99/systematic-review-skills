#!/usr/bin/env python3
# Copyright 2026 Ooi Pin Jun
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path
import unittest


SHARED = Path(__file__).resolve().parents[1]
APACHE_HEADER = """# Copyright 2026 Ooi Pin Jun
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""


class LicenseHeaderTests(unittest.TestCase):
    def test_all_shared_python_files_have_apache_header(self):
        paths = sorted(SHARED.rglob("*.py"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.relative_to(SHARED)):
                text = path.read_text(encoding="utf-8")
                if text.startswith("#!"):
                    text = text.split("\n", 1)[1]
                self.assertTrue(text.startswith(APACHE_HEADER), path)


if __name__ == "__main__":
    unittest.main()
