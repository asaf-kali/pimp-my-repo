---
name: flatten
description: >
  Apply flat code style: no more than 2 indentation levels per function, early returns,
  extracted sub-functions. Use when the user says "flatten", "too nested", "simplify nesting",
  "early returns", or asks to reduce indentation. Also apply proactively when writing new
  functions or reviewing code — flat style is the default, not an afterthought.
---

# flatten

Flatten means: no more than 2 levels of indentation per function. Achieve this through
early returns, extracted sub-functions, and loop inversion. Never change behavior.

## Techniques

### 1. Early return (guard clause)

Replace `if X: ... else: ...` with a guard that returns early, leaving the happy path flat.

**Before:**
```python
def process(data):
    if data is not None:
        result = compute(data)
        if result.ok:
            return result.value
        else:
            raise ValueError(result.error)
    else:
        return None
```

**After:**
```python
def process(data):
    if data is None:
        return None
    result = compute(data)
    if not result.ok:
        raise ValueError(result.error)
    return result.value
```

### 2. Extract sub-function

When a block inside a function is large or has its own "local" logic, pull it out.

**Before:**
```python
def run(config):
    if config.mode == "fast":
        items = []
        for x in config.inputs:
            if x.valid:
                items.append(transform(x))
        return items
    else:
        return []
```

**After:**
```python
def run(config):
    if config.mode != "fast":
        return []
    return _collect_valid(config.inputs)

def _collect_valid(inputs):
    return [transform(x) for x in inputs if x.valid]
```

### 3. Invert loop conditions (skip instead of nest)

Replace `if condition: <body>` inside a loop with `if not condition: continue`.

**Before:**
```python
for item in items:
    if item.active:
        if item.value > 0:
            results.append(process(item))
```

**After:**
```python
for item in items:
    if not item.active:
        continue
    if item.value <= 0:
        continue
    results.append(process(item))
```

### 4. Split branchy function into two focused functions

When a function has a big `if/else` where both branches are long, split into two functions
and dispatch from a thin coordinator.

**Before:**
```python
def lock(project_section):
    if project_section and project_section.get("requires-python"):
        # 10 lines
        ...
        detected_minor = None
    else:
        initial = resolve(...)
        if initial is None:
            ...
            return
        # 10 more lines
        detected_minor = int(...)
    # shared tail — search loop
    for minor in range(...):
        ...
```

**After:**
```python
def lock(project_section):
    if project_section and project_section.get("requires-python"):
        if _try_existing(project_section):
            return
        _search(skip_minor=None)
        return
    _resolve_and_lock()

def _resolve_and_lock():
    initial = resolve(...)
    if initial is None:
        ...
        return
    detected_minor = int(...)
    if _try(detected_minor):
        return
    _search(skip_minor=detected_minor)

def _search(skip_minor):
    for minor in range(...):
        ...
```

### 5. Extract except body

When an except clause is long, pull it into a handler function.

**Before:**
```python
try:
    self.uv.sync_all()
except CalledProcessError as e:
    stderr = e.stderr or ""
    if MSG_A in stderr:
        logger.info("...")
    elif MSG_B in stderr:
        logger.info("...")
    else:
        raise
    self._fix()
    self.uv.sync_all()
```

**After:**
```python
try:
    self.uv.sync_all()
except CalledProcessError as e:
    self._handle_sync_error(e)

def _handle_sync_error(self, e):
    stderr = e.stderr or ""
    if MSG_A in stderr:
        logger.info("...")
    elif MSG_B in stderr:
        logger.info("...")
    else:
        raise e
    self._fix()
    self.uv.sync_all()
```

## Process

1. Read the full function — understand behavior before touching anything.
2. Identify the deepest nesting. Ask: can this block become an early return or a sub-function?
3. Apply one technique at a time.
4. Run `just lint && just test` after each extraction.
5. If a moved function no longer uses `self`, make it module-level (check for `ARG001`).
   But if tests call it as an instance method, keep it in the class with `# noqa: ARG002`.

## Rules

- Never change observable behavior — only structure.
- Max 2 levels of indentation per function. Enforce it.
- Extracted functions get names that describe what they do, not how: `_resolve_and_lock`, not `_do_the_else_branch`.
- No bare `raise` outside an except block — use `raise e` when re-raising in a helper.
- Module-level helpers go after the class, before other module-level helpers.
- Always run `just lint && just test` after flattening.
