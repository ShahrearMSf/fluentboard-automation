# Subtasks endpoints

Base: `/wp-json/fluent-boards/v2`. Call via `request.sh METHOD PATH [BODY]`.

Subtasks are grouped under a parent task into one or more **subtask groups** (a kind of checklist section). Many endpoints take `task_id` in the path — for most subtask ops, `task_id` refers to the **parent** task; for a few (delete, clone, move-to-board), `task_id` refers to the **subtask itself**.

## Quirks worth knowing before you build on these endpoints

- **`GET /subtasks` returns `title: null` for every subtask group**, even when the group was created with a title and the UI clearly shows it. The titles are stored server-side; the list response just omits them. To learn a group's title, capture it from the **create response** (see `subtaskGroup.value` below) and remember it client-side, or call the rename endpoint to overwrite it.
- **Subtask titles are editable via the regular task PUT endpoint**, not a subtask-specific route. Since subtasks are stored as tasks with `parent_id` set, the standard `PUT /projects/{board_id}/tasks/{subtask_id}` with `{ "property": "title", "value": "…" }` works and is the only documented way to rename a subtask. `update-task.sh` works on subtask IDs unchanged. No edit endpoint is listed in the table below because there's no subtask-specific one.
- **Mark a subtask complete with `PUT { "property":"status", "value":"closed" }` — and only that.** The server auto-sets `last_completed_at` when you flip status. **Do NOT also set `last_completed_at` in a follow-up PUT — that resets the subtask to `status=open` and clears the completion timestamp.** Confirmed by experiment: `status=closed` → `LIST` shows `status=closed, last_completed_at=<now>`; a subsequent `PUT last_completed_at=<x>` on the same subtask flips both back to `open / null`. To re-open a closed subtask, send `{ "property":"status", "value":"open" }`.
- **`GET /projects/{B}/tasks/{subtask_id}` returns stale / partial data** for subtasks (often `status: "open"`, `last_completed_at: null`, `parent_id: null` — even when the subtask is closed and parented). Always use the parent-task subtasks list (`GET /projects/{B}/tasks/{parent_id}/subtasks`) to read the truth; only use the bare task GET for unrelated metadata.
- **`create-subtask-group.sh` and `create-subtask.sh` may fail under zsh** with `(eval):N: failed to change group ID: operation not permitted` — this is a shell-level issue that has shown up on at least one macOS install. If you hit it, fall back to direct API calls via `request.sh` (the underlying endpoints work fine; only the wrappers trip).

| # | Method | Path | Purpose |
|---|--------|------|---------|
| 1 | GET | `/projects/{board_id}/tasks/{task_id}/subtasks` | List subtask groups + their subtasks. |
| 2 | POST | `/projects/{board_id}/tasks/{task_id}/subtasks` | Create a subtask. |
| 3 | POST | `/projects/{board_id}/tasks/{task_id}/subtask-group` | Create a subtask group. |
| 4 | PUT | `/projects/{board_id}/tasks/{task_id}/subtask-group` | Rename a subtask group. |
| 5 | DELETE | `/projects/{board_id}/tasks/{task_id}/subtask-group` | Delete a subtask group. |
| 6 | DELETE | `/projects/{board_id}/tasks/{task_id}/delete-subtask` | Delete a subtask (here `task_id` = subtask). |
| 7 | POST | `/projects/{board_id}/tasks/{task_id}/move-subtask` | Move subtask(s) between groups (same parent). |
| 8 | PUT | `/projects/{board_id}/tasks/update-subtask-position/{subtask_id}` | Reorder a subtask. |
| 9 | PUT | `/projects/{board_id}/tasks/{task_id}/convert-to-subtask` | Convert a task to a subtask of another task. |
| 10 | PUT | `/projects/{board_id}/tasks/{task_id}/move-to-board` | Move subtask to a different board/stage. |
| 11 | POST | `/projects/{board_id}/tasks/{task_id}/clone-subtask` | Clone a subtask. |

## 2. POST — create subtask

```json
{ "title": "Open PR", "group_id": 18, "due_at": "2026-04-22", "add_to_top": true }
```

`title` and `group_id` are required. `add_to_top=true` inserts at position 0.

## 3–5. Subtask groups

```json
// create
{ "title": "Rollout checklist" }

// update
{ "group_id": 18, "title": "Rollout checklist (v2)" }

// delete
{ "group_id": 18 }
```

The **create response** uses an unusual shape — the title comes back as a key/value pair, not as a `title` field:

```json
{
  "subtaskGroup": {
    "key": "group_name",
    "value": "Rollout checklist",
    "task_id": 80927,
    "id": 181429,
    "created_at": "…",
    "updated_at": "…"
  },
  "message": "New Subtask group has been added"
}
```

So pull the new group id from `subtaskGroup.id` and the title from `subtaskGroup.value`. `create-subtask-group.sh` already handles this and emits a normalised `{group_id, title, raw_create}` shape.

## 7. POST — move subtasks between groups

```json
{ "group_id": 20, "subtask_id": [101, 102, 103] }
```

`subtask_id` accepts a single integer or an array.

## 8. PUT — reorder a subtask

```json
{ "newPosition": 3, "newSubtasksGroupId": 20 }
```

## 9. PUT — convert task to subtask

```json
{ "parent_id": 80927, "assigneeId": 42, "subtaskGroupId": 18 }
```

Demotes the task and nests it under `parent_id`. `subtaskGroupId` targets a specific checklist; `assigneeId` optionally sets the new owner.

## 10. PUT — move subtask to a different stage

```json
{ "stage_id": 512 }
```

The `task_id` in the path is the subtask's own ID.
