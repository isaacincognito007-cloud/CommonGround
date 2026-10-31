# CommonGround Verification Workflow - Progress Tracker

## Phase 0: Recon and baseline
- [x] Git repository initialized and baseline committed
- [x] Branch fix/verification created
- [x] README, server.py, web/app.js, tests reviewed
- [x] docs/ASSUMPTIONS.md written

## Phase 1: Security fixes first
- [x] Existing verify endpoint: block self-verification (403)
- [x] Enforce state rules on existing verify endpoint
- [x] Require reason on reject
- [x] Log through new activity columns
- [x] Notify affected user
- [x] Confirm role/ownership from DB per request
- [x] Whitelist writable fields on users/resources INSERT/UPDATE
- [x] Edit-reset: material edit to verified resource sets to unverified
- [x] Enforce valid verification_status via triggers (SQLite) / constraint (Postgres)

## Phase 2: Audit columns
- [x] Idempotent ALTER TABLE on activity for actor_role, target_type, target_id, from_status, to_status, reason
- [x] Keep existing immutability triggers
- [ ] Log denied attempts as verification_denied (capped per actor per minute)

## Phase 3: Endpoints
- [x] POST /api/verification/request
- [x] GET /api/admin/verifications
- [x] PATCH /api/admin/verify
- [x] GET /api/verification/history
- [x] GET /api/notifications
- [x] POST /api/notifications/read
- [ ] Manager's own resource request approvable only by Owner/Admin (partial - assign_manager flow exists)

## Phase 4: End-to-end sharing journey
- [ ] Trace and fix Listing -> Request -> Approval -> Collection/Checkout -> Usage -> Return
- [ ] Write one test running whole journey with three accounts

## Phase 5: UI
- [x] VerificationBadge helper in web/app.js (added but needs full integration)
- [ ] Owner/User gets Request verification button
- [ ] Manager/Admin gets pending queue with Approve/Reject (reason required) and history
- [ ] Disable buttons while in flight
- [ ] Notification bell: poll every 30s and on window focus
- [ ] Opening marks items read through API
- [ ] Fix responsive issues at 320, 360, 375, 414px

## Phase 6: Demo mode
- [ ] CG_DEMO_MODE env flag (default off)
- [ ] When on: seed Owner/Admin, Manager, User with hashed passwords + resources in each state
- [ ] Collapsible "Demo accounts" panel below login form with Use buttons
- [ ] When off: nothing seeded, no credentials in responses
- [ ] README documents CG_DEMO_MODE=1 for judge deployment

## Phase 7: Tests
- [x] Fix Windows cleanup errors
- [ ] Test groups: self-verification/mass-assignment; escalation/forged roles; state machine/409s; activity-log atomicity; notifications; edit-reset; migration; full journey
- [ ] Suite finishes with zero errors
- [ ] Mutation test: remove each guard and confirm test fails

## Phase 8: Docs and report
- [ ] README: roles, permissions, verification workflow, demo mode, test running
- [ ] docs/BUILD_REPORT.md
