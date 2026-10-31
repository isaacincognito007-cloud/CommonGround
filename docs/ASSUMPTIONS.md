# Assumptions and Rulings

## Task 0 Recon Findings

- **Sessions & Roles:** Sessions are managed by opaque tokens in `cg_session` cookies, associated with `user_id`. Roles are assigned in the `users` table (`member`, `manager`, `admin`, `owner`). The `public_user` function returns sanitized user data.
- **Error Handling:** Errors follow a pattern where a custom `Problem` exception is raised with `code`, `field`, `message`, and `status`. Status codes: 401 unauthenticated, 403 forbidden, 404 not found, 409 illegal state, 422 invalid body, 400 bad request.
- **Activity Logging:** The `activity` table is append-only, enforced by database triggers (`audit_no_update`, `audit_no_delete`). Columns: id, actor_id, resource_id, booking_id, action, detail, created.
- **Static Files:** Served from `web/` directory via the Handler's do_GET path. Serves app.js, style.css, favicon.svg, and HTML view.
- **Organization:** There is no specific organisation or tenant entity. Resources are owned by a user (`owner_id`) and can have an assigned manager (`manager_id`).
- **Existing Approval:** Booking approval flow exists via `/api/bookings/{id}/action` with actions: approve, reject, waitlist, cancel, check_in, return, confirm_return, incident, resolve, extend, assign_manager. The `manages` function checks if a user is an admin or is the owner/manager of a resource.
- **Database:** SQLite with PRAGMA journal_mode=WAL, foreign_keys=ON, busy_timeout=15000. Supports fallback to PostgreSQL.
- **Notifications:** Existing `notifications` table with id, user_id, message, dedupe, created. Used via `notify()` function with deduplication.
- **Error Shape:** Existing error shape is `{'error': {'code': ..., 'field': ..., 'message': ..., 'status': ...}}`
- **Routes:** All API routes under `/api/`. Pattern: `/api/{resource}/{id}/{action}` for specific operations.
- **Session Auth:** `auth()` method validates cookie, checks session expiration, optionally validates CSRF token for unsafe operations.
- **Roles in Use:** `member`, `manager`, `admin`, `owner` (for resources, not a login role)
- **User Verification:** Existing `verified` (INTEGER) and `credentials` (TEXT JSON) fields on users table. Verification is done via `/api/users/{id}/verify` endpoint (admin only).
- **Resource Sharing Flow:** Listing → Request → Approval → Collection/Checkout → Usage → Return exists via booking workflow.

## Verification Workflow Decisions

- Activities will include actor_role for better audit trails
- Verification status transitions will follow state machine rules strictly
- Notifications will use existing notify pattern but with structured fields
- Demo mode will use environment variable `CG_DEMO_MODE`
- All verification endpoints will use the existing Problem exception pattern
