#!/usr/bin/env python3
"""
Convert conn.execute(stmt, a=foo, b=bar) → conn.execute(stmt, dict(a=foo, b=bar))
for SQLAlchemy 2.0 future mode compatibility.

Uses the tokenizer to find calls, then does text-based transformation.
"""

import io
import tokenize
from pathlib import Path


def _get_tokens(code: str):
    return list(tokenize.generate_tokens(io.StringIO(code).readline))


def fix_file(filepath: str) -> bool:
    path = Path(filepath)
    original = path.read_text()

    if '.execute' not in original:
        return False

    try:
        tokens = _get_tokens(original)
    except Exception:
        return False

    # Find all .execute( calls
    calls = []
    for i, tok in enumerate(tokens):
        if (tok.type == tokenize.OP and tok.string == '.'
                and i + 2 < len(tokens)
                and tokens[i + 1].type == tokenize.NAME
                and tokens[i + 1].string == 'execute'
                and tokens[i + 2].type == tokenize.OP
                and tokens[i + 2].string == '('):
            depth = 0
            for j in range(i + 2, len(tokens)):
                if tokens[j].type == tokenize.OP:
                    if tokens[j].string == '(':
                        depth += 1
                    elif tokens[j].string == ')':
                        depth -= 1
                        if depth == 0:
                            calls.append((i, j))
                            break

    if not calls:
        return False

    lines = original.split('\n')

    # We'll track modifications by (start_line, start_col, end_line, end_col, new_text)
    modifications = []

    for dot_idx, close_idx in calls:
        dot_tok = tokens[dot_idx]
        close_tok = tokens[close_idx]
        open_tok = tokens[dot_idx + 2]

        s_line = open_tok.start[0]  # 1-based
        s_col = open_tok.start[1] + 1  # after (
        e_line = close_tok.start[0]
        e_col = close_tok.start[1]  # the )

        # Get inner text (between parens)
        if s_line == e_line:
            inner_text = lines[s_line - 1][s_col:e_col]
        else:
            # Multi-line: collect from s_line to e_line
            parts = []
            for ln in range(s_line - 1, e_line):
                if ln == s_line - 1:
                    parts.append(lines[ln][s_col:])
                elif ln == e_line - 1:
                    parts.append(lines[ln][:e_col])
                else:
                    parts.append(lines[ln])
            inner_text = '\n'.join(parts)

        # Check if inner has kwargs: find '=' at depth 0 (not inside nested parens)
        depth = 0
        has_kwargs = False
        eq_positions = []  # positions of '=' at depth 0
        for ci, c in enumerate(inner_text):
            if c in '([':
                depth += 1
            elif c in ')]':
                depth -= 1
            elif c == '=' and depth == 0:
                has_kwargs = True
                eq_positions.append(ci)

        if not has_kwargs:
            continue

        # Check if already has dict( or { around kwargs
        # Simple check: look for 'dict(' or '{' in inner_text after the first comma at depth 0
        depth = 0
        found_comma = False
        already_wrapped = False
        for ci, c in enumerate(inner_text):
            if c in '([':
                depth += 1
            elif c in ')]':
                depth -= 1
            elif c == ',' and depth == 0:
                found_comma = True
            elif found_comma and depth == 0 and c == '{':
                already_wrapped = True
                break
            elif found_comma and depth == 0 and inner_text[ci:ci+4] == 'dict':
                # Check it's dict( not just "dict" string
                rest = inner_text[ci+4:].strip()
                if rest.startswith('('):
                    already_wrapped = True
                    break

        if already_wrapped:
            continue

        # Find the split: first arg (stmt) vs kwargs
        # Split by first top-level comma
        depth = 0
        split_pos = None
        for ci, c in enumerate(inner_text):
            if c in '([':
                depth += 1
            elif c in ')]':
                depth -= 1
            elif c == ',' and depth == 0:
                split_pos = ci
                break

        if split_pos is None:
            continue  # no args

        stmt_part = inner_text[:split_pos]
        kwargs_part = inner_text[split_pos + 1:]  # after comma

        # Trim leading whitespace from kwargs_part for the dict wrapping
        kwargs_stripped = kwargs_part.lstrip()
        leading_ws = kwargs_part[:len(kwargs_part) - len(kwargs_stripped)]

        # Handle **var pattern - just strip the **
        if kwargs_stripped.startswith('**'):
            var_name = kwargs_stripped[2:].strip()
            new_kwargs = f'{leading_ws}{var_name}'
        else:
            new_kwargs = f'{leading_ws}dict({kwargs_stripped})'

        new_inner = f'{stmt_part},{new_kwargs}'

        # Build full new text
        if s_line == e_line:
            old_text = lines[s_line - 1][s_col - 1:e_col + 1]  # (inner)
            new_text = f'({new_inner})'
            modifications.append((s_line - 1, s_col - 1, s_line - 1, e_col + 1, new_text))
        else:
            # Multi-line: need to collapse
            old_first_line = lines[s_line - 1]
            old_last_line = lines[e_line - 1]
            prefix = old_first_line[:s_col - 1]  # before (
            new_full = f'{prefix}({new_inner})'
            modifications.append(
                (s_line - 1, 0, e_line - 1, len(old_last_line), new_full)
            )

    if not modifications:
        return False

    # Apply modifications in reverse order (bottom to top, right to left)
    modifications.sort(key=lambda m: (m[0], m[1]), reverse=True)

    for mod in modifications:
        s_ln, s_pos, e_ln, e_pos, new_text = mod
        if s_ln == e_ln:
            line = lines[s_ln]
            lines[s_ln] = line[:s_pos] + new_text + line[e_pos:]
        else:
            # Replace multiple lines with one
            # Keep indentation from the start line
            prefix = lines[s_ln][:s_pos]
            lines[s_ln] = prefix + new_text
            # Remove subsequent lines up to e_ln
            del lines[s_ln + 1:e_ln + 1]

    new_content = '\n'.join(lines)
    if original.endswith('\n') and not new_content.endswith('\n'):
        new_content += '\n'
    path.write_text(new_content)
    return True


def main():
    import sys
    patterns = sys.argv[1:] if len(sys.argv) > 1 else ['src/', 'tests/']

    files_to_check = []
    for pattern in patterns:
        p = Path(pattern)
        if p.is_file():
            files_to_check.append(p)
        elif p.is_dir():
            files_to_check.extend(p.rglob('*.py'))

    modified_files = []
    skipped_files = []
    for f in files_to_check:
        sp = str(f)
        if any(skip in sp for skip in [
            '__pycache__', '.egg', '/venv/', '/.venv/', '/.git/', '/_legacy/',
        ]):
            continue
        try:
            if fix_file(str(f)):
                modified_files.append(str(f))
        except Exception as e:
            skipped_files.append((str(f), str(e)))

    if modified_files:
        print(f'Modified {len(modified_files)} files:')
        for f in modified_files:
            print(f'  {f}')
    if skipped_files:
        print(f'\nSkipped {len(skipped_files)} files (errors):')
        for f, e in skipped_files:
            print(f'  {f}: {e}')
    if not modified_files and not skipped_files:
        print('No files modified.')


if __name__ == '__main__':
    main()
