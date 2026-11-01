"""Fixes: notifications page crash ('Invalid time value') and adds a success pop-up after a verification review.
Run from the project root:  python .\fix_notifications.py"""
import pathlib, sys

def patch(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding='utf-8')
    changed = False
    for old, new, label in pairs:
        if new in s:
            print('already done:', label); continue
        if s.count(old) != 1:
            sys.exit(f'STOP - could not find "{label}" exactly once in {path}. Send me this message.')
        s = s.replace(old, new); changed = True; print('patched:', label)
    if changed:
        p.write_text(s, encoding='utf-8')

# server.py ---------------------------------------------------------------
patch('server.py', [
 # 1. the page reads n.message and n.created; the new table has body and created_at
 ("'notifications':[dict(x) for x in c.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],))]",
  "'notifications':[dict(x) for x in c.execute('SELECT *,body AS message,created_at AS created FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],))]",
  'notifications include message + created'),
 # 2. clearer notification text for the member
 ("notify(c,target,f'Your verification has been reviewed. {reason}')",
  "notify(c,target,(f'Your account has been verified. Review note: {reason}' if to_status=='verified' else f'Your account verification was updated to unverified. Review note: {reason}') if from_status!=to_status else f'Your training and membership details were reviewed and updated. Review note: {reason}')",
  'clearer verification notification text'),
])

# web/app.js --------------------------------------------------------------
OLD = "modal.close();await load();}catch(error){document.querySelector('#verify-error')"
NEW = ("await load();showDialog(`<div class=\"symbol\" aria-hidden=\"true\">✓</div>"
       "<h2 id=\"dialog-title\">Verification review saved</h2>"
       "<p>${esc(p.name||'The member')} has been notified of the outcome and your review note.</p>"
       "<div class=\"actions\"><button class=\"primary\" data-close>Done</button></div>`);}"
       "catch(error){document.querySelector('#verify-error')")
patch('web/app.js', [(OLD, NEW, 'success pop-up after saving a verification review')])
