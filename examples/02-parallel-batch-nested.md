---
title: Add license headers to all Python files
executor: sonnet
includes:
  - branch-safety
  - nested-dispatch
nested_dispatch:
  max_depth: 1
  allowed_executors: [haiku]
---

# Task

Add the standard MIT license header to every Python file in `src/` that
doesn't already have one.

## License header to add

```python
# Copyright (c) 2026 Project Contributors
# Licensed under the MIT License. See LICENSE for details.
```

## Approach

1. Find all .py files in src/ missing the license header
2. Group them into batches of 10 files
3. For each batch, dispatch a haiku sub-worker with a brief listing
   the exact files to update
4. Wait for all sub-workers to complete
5. Run a verification pass: grep all .py files to confirm the header
   is present

## Sub-worker brief template

For each batch, write a brief like:

```markdown
---
title: Add license header batch N
executor: haiku
---
Add this exact header to the top of each file (before any existing code,
after any shebang line):

# Copyright (c) 2026 Project Contributors
# Licensed under the MIT License. See LICENSE for details.

Files:
- src/auth/login.py
- src/auth/session.py
- (... up to 10 files)
```

## Constraints

- Only add the header, do not modify any other content
- Preserve shebang lines (#!/usr/bin/env python3) at the top
- Do not add duplicate headers to files that already have one
- Sub-workers use haiku (this is mechanical insertion)
