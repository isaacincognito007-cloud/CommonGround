# Resource-Sharing Verification Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a comprehensive role-based verification system for users and resources, ensuring secure, auditable, and cross-account workflows in the CommonGround platform.

**Architecture:** Extend the existing SQLite/Python backend with verification status fields and logic; add frontend UI components (VerificationBadge) and dashboard views; integrate real-time notifications for status changes.

**Tech Stack:** Python 3.11+, SQLite, HTML/CSS/Vanilla JS.

**Spec:** The task requirements detailed in the previous conversation.

## Global Constraints

- Preserve the existing UI (theme, colors, spacing).
- Do not remove, replace, or rearrange existing components unnecessarily.
- Role-based permissions (User, Owner, Manager/Admin) must be enforced server-side.
- All verification actions must be recorded in the `activity` log.
- Do not introduce new dependencies (external email services, etc.).

## Review Focus

1. **Self-verification loophole:** A user trying to verify their own account.
2. **Unauthorized escalation:** A user attempting to access Manager/Admin verification endpoints.
3. **Manager self-approval:** A Manager approving their own resource request (must be blocked).
4. **Notification persistence:** Ensuring notifications exist after refresh.
5. **UI Visibility:** Ensuring no text/buttons are clipped on small screens.

---

### Task 1: Database Migration
**Files:**
- Modify: `server.py` (init_db function)

- [ ] **Step 1: Add verification columns to users and resources tables in `server.py`**
- [ ] **Step 2: Verify column addition**
- [ ] **Step 3: Commit**

### Task 2: Backend Logic for Verification
**Files:**
- Modify: `server.py` (add endpoints)

- [ ] **Step 1: Implement `PATCH /api/admin/verify` and `reject` logic for Users and Resources**
- [ ] **Step 2: Add authorization checks to ensure only Managers can trigger verification**
- [ ] **Step 3: Implement internal notification service call**
- [ ] **Step 4: Commit**

### Task 3: Verification UI Enhancements
**Files:**
- Create: `web/components/VerificationBadge.js` (or similar)
- Modify: `web/app.js` (Dashboard rendering)

- [ ] **Step 1: Implement `VerificationBadge` component**
- [ ] **Step 2: Update User Profile and Resource Detail views to use the badge**
- [ ] **Step 3: Update Dashboard to show verification status**
- [ ] **Step 4: Commit**

### Task 4: Notifications & Workflow Integration
**Files:**
- Modify: `server.py` (notification logic)

- [ ] **Step 1: Implement persistent notification storage**
- [ ] **Step 2: Integrate notifications into the verification flow**
- [ ] **Step 3: Commit**

### Task 5: UI/UX Fixes and Demo Credentials
**Files:**
- Modify: `web/style.css`, `web/app.js` (login form)

- [ ] **Step 1: Fix layout clipping issues identified in screenshots**
- [ ] **Step 2: Inject Demo Account credentials display into the Login form**
- [ ] **Step 3: Commit**
