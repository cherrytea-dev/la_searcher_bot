# Root Cause Analysis & Fix Plan: Duplicate Comments in `comments` Table

## Problem

Users receive duplicate comments in notifications. The `comments` table contains records with identical content (`comment_text`, `comment_author_nickname`, `comment_author_link`, `comment_global_num`, `search_forum_num`) but different `comment_num` and `comment_url` values.

**Example from the data** (topic 369143):
| id     | comment_num | comment_url (start=) | comment_global_num |
| ------ | ----------- | -------------------- | ------------------ |
| 299572 | 94          | start=94             | 1153832            |
| 299573 | 95          | start=95             | 1153832            |

Both records have the same text, same author, and same `comment_global_num` (1153832), proving they are the **same forum post** saved twice.

---

## Root Cause Analysis

### The Bug: `comment_num` is used as a pagination offset, not a comment index

In [`_get_comment_url()`](src/identify_updates_of_topics/_utils/forum.py:308):

```python
def _get_comment_url(self, search_num: int, comment_num: int) -> str:
    return f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'
```

The `start` parameter in phpBB is a **pagination offset**, not a sequential comment number. phpBB rounds `start` down to the nearest multiple of `posts_per_page` (usually 15). So:

- `start=94` → phpBB serves the page starting at offset 90 (posts 90-104)
- `start=95` → phpBB also serves the page starting at offset 90 (same page!)

Both URLs return **identical HTML content**.

### Why it didn't happen before the commit

**Before the commit** (old code at `d93630c`), the system worked with **folders** — it parsed the entire folder listing page which contained all topics with their reply counts from `forum_search_item.replies_count`. The reply count came directly from the folder listing page, which shows the **actual number of replies** (not pagination offsets).

**After the commit** (`1f04a78`), the system switched to working with **individual topics**. The key change is in [`_parse_one_search()`](src/identify_updates_of_topics/_utils/folder_updater.py:362):

```python
# OLD: reply count from folder listing page (accurate)
num_of_replies=forum_search_item.replies_count,

# NEW: reply count parsed from topic page (also accurate, but different source)
replies_count = self.forum.get_replies_count(forum_search_item.search_id)
num_of_replies=replies_count,
```

Both old and new code get the reply count correctly. **The `_parse_comments_and_detect_inforg_comments` method itself didn't change** — it always iterated over `comment_number` and passed it as `start`.

**So why did duplicates start appearing now?**

The answer is: **the `_get_comment_content` method does NOT have `@lru_cache`**, while `_get_topic_content` **DOES** have `@lru_cache` (added in the commit). This means:

- `_get_topic_content(search_num)` — cached, so parsing the topic page multiple times doesn't make extra HTTP requests
- `_get_comment_content(search_num, comment_num)` — **NOT cached**, so each `comment_number` value makes a separate HTTP request

But the real issue is simpler: **the old code also had this same bug**. The `_parse_comments_and_detect_inforg_comments` method and `_get_comment_url` are **identical** between old and new code. The duplication was always possible.

### Why duplicates are more likely now

The **real change** that made duplicates more likely is the **architectural shift from folder-based to topic-based processing**:

1. **Old code**: Processed all topics in a folder at once. When a folder was detected as changed, it would parse all topics and detect new comments. The folder-level hash check (`update_checker`) acted as a gate — if the folder content hash matched, no processing happened at all.

2. **New code**: Processes each topic individually via PubSub messages. Each topic is processed independently when a change is detected. The `_get_topic_content` is now cached with `@lru_cache`, but `_get_comment_content` is NOT cached.

The key insight: **the old code also had this exact same bug** — it also used `start={comment_num}` and also iterated over sequential numbers. The duplication was always theoretically possible, but:

- In the old code, the folder-level hash check meant that if the folder content didn't change, **no topics were processed at all**
- In the new code, each topic is processed independently, so **every topic with new replies** triggers the comment parsing loop

### The iteration logic (unchanged between versions)

In [`_parse_comments_and_detect_inforg_comments()`](src/identify_updates_of_topics/_utils/folder_updater.py:246):

```python
for comment_number in range(searches_line.num_of_replies + 1, snapshot_line.num_of_replies + 1):
    comment_data = self.forum.get_comment_data(snapshot_line.topic_id, comment_number)
```

This iterates over **every reply number** between old and new reply counts. Since `comment_number` is treated as a pagination offset, multiple consecutive `comment_number` values can map to the same forum page, causing the same comment to be parsed multiple times.

### Data Flow Diagram

```mermaid
flowchart LR
    A[New replies detected] --> B[Iterate comment_number\nfrom old_count+1 to new_count]
    B --> C[Build URL:\nstart=comment_number]
    C --> D[Fetch forum page\n(NOT cached)]
    D --> E[Parse first div.post]
    E --> F[INSERT into comments table\n(no duplicate check)]
    
    C2[comment_number=94] --> D2[start=94 → page offset 90]
    C3[comment_number=95] --> D3[start=95 → page offset 90]
    D2 --> E2[Same first post!\nglobal_num=1153832]
    D3 --> E3[Same first post!\nglobal_num=1153832]
    E2 --> F2[INSERT record #299572]
    E3 --> F3[INSERT record #299573]
```

### Why `comment_global_num` is the same

In [`get_comment_data()`](src/identify_updates_of_topics/_utils/forum.py:240-246):

```python
soup = BeautifulSoup(content, features='lxml')
search_code_blocks = soup.find('div', 'post')  # Gets FIRST post on page!
```

Since both URLs resolve to the same page, `soup.find('div', 'post')` returns the **same first post** in both cases. The `comment_global_num` is extracted from the permanent link URL (`viewtopic.php?p={id}#p{id}`), which is the same for the same post.

### Why `write_comment()` doesn't prevent duplicates

In [`write_comment()`](src/identify_updates_of_topics/_utils/database.py:153):

```python
def write_comment(self, comment_data: ForumCommentItem) -> None:
    with self.connect() as conn:
        if not comment_data.comment_text:
            return
        stmt = sqlalchemy.text("""
            INSERT INTO comments 
                (comment_url, comment_text, comment_author_nickname,
                comment_author_link, search_forum_num, comment_num, 
                notification_sent, comment_global_num)
            VALUES (:a, :b, :c, :d, :e, :f, :g, :h); 
        """)
        conn.execute(stmt, ...)
```

There is:
- No `ON CONFLICT` clause
- No `SELECT`-before-`INSERT` check
- No unique constraint on the `comments` table to prevent duplicates

---

## Proposed Fix

### Approach: Add duplicate prevention in `write_comment()`

The most robust fix is to add an `ON CONFLICT` clause to the INSERT statement, using the natural unique identifier: `comment_global_num` (the global post ID from the forum URL).

#### Option A (Recommended): `INSERT ... ON CONFLICT DO NOTHING`

1. Add a **unique constraint** on `(comment_global_num, search_forum_num)` in the `comments` table
2. Modify the `INSERT` statement to use `ON CONFLICT (comment_global_num, search_forum_num) DO NOTHING`

**Affected files:**

| File                                                                                                                 | Change                                                                    |
| -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [`src/identify_updates_of_topics/_utils/database.py:153-173`](src/identify_updates_of_topics/_utils/database.py:153) | Add `ON CONFLICT` to INSERT statement                                     |
| Database migration                                                                                                   | Add unique constraint on `comments(comment_global_num, search_forum_num)` |

**Updated SQL:**

```sql
INSERT INTO comments 
    (comment_url, comment_text, comment_author_nickname,
     comment_author_link, search_forum_num, comment_num, 
     notification_sent, comment_global_num)
VALUES (:a, :b, :c, :d, :e, :f, :g, :h)
ON CONFLICT (comment_global_num, search_forum_num) DO NOTHING;
```

**Why `comment_global_num` is the right unique identifier:**
- It's the globally unique post ID assigned by phpBB
- It's extracted from the permanent link URL (`viewtopic.php?p={id}#p{id}`)
- It uniquely identifies a single forum post, regardless of pagination
- The combination `(comment_global_num, search_forum_num)` ensures we only avoid duplicates within the same topic (though `comment_global_num` is globally unique by itself)

#### Option B (Alternative): `SELECT` before `INSERT`

Less efficient but doesn't require a DB schema change. Add a check in `write_comment()`:

```python
# Check if comment with this global_num already exists
existing = conn.execute(
    text("SELECT id FROM comments WHERE comment_global_num = :g AND search_forum_num = :s"),
    {"g": comment_data.comment_forum_global_id, "s": comment_data.search_forum_num}
).fetchone()
if existing:
    return
```

### Edge Cases to Consider

1. **`comment_forum_global_id` is `None`**: When `comment_data.ignore = True`, the `comment_global_num` is saved as `NULL`. Multiple ignored comments can have `NULL` global IDs. The unique constraint won't apply to `NULL` values in PostgreSQL (NULLs are considered distinct), so this is safe — ignored comments won't be affected.

2. **Test for deleted/duplicate `comment_url`**: The existing data shows different `comment_url` values for the same comment. The fix handles this correctly because we're deduplicating by `comment_global_num`, not by URL.

3. **Existing duplicates in the database**: The fix only prevents NEW duplicates. Existing duplicates will remain. If cleanup is needed, a separate SQL script would be required:
   ```sql
   DELETE FROM comments
   WHERE id NOT IN (
       SELECT MIN(id) FROM comments
       GROUP BY comment_global_num, search_forum_num
   );
   ```

---

## Implementation Steps

### Step 1: Database migration
- Add a unique constraint on `comments(comment_global_num, search_forum_num)`
- This may require cleanup of existing duplicates first

### Step 2: Modify `write_comment()` in `database.py`
- Replace plain `INSERT` with `INSERT ... ON CONFLICT DO NOTHING`

### Step 3: Update tests
- Add test cases in [`test_db_client.py:130-138`](tests/test_identify_updates_of_topics/test_db_client.py:130) to verify that inserting a duplicate `comment_global_num` is handled gracefully
- Update existing tests if needed

### Step 4: Clean up existing duplicates (optional)
- Run a SQL script to remove duplicate records from the `comments` table

---

## Summary

| Aspect         | Detail                                                                                                                                                                                                                  |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Root cause** | Sequential `comment_number` values are used as phpBB pagination offsets (`start`), so multiple values map to the same page. `get_comment_data()` always gets the first post, and `write_comment()` does a blind INSERT. |
| **Why now?**   | The architectural change from folder-based to topic-based processing means each topic is processed independently. The old code had the same bug but the folder-level hash check reduced the frequency.                  |
| **Fix**        | Add `ON CONFLICT (comment_global_num, search_forum_num) DO NOTHING` to the INSERT statement, preventing duplicate records by their unique global post ID.                                                               |
| **Risk**       | Low. The fix is localized to one method. The unique constraint is natural (a forum post can only appear once in a topic).                                                                                               |
| **Testing**    | Verify that inserting the same `comment_global_num` twice doesn't create a second record.                                                                                                                               |
