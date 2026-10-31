"""Trusted operator account and backup tools. Never exposed as an HTTP endpoint.
Isaac Shiloah Herbert V · ISAAC.INCOGNITO007.
"""
import argparse
import getpass
import json
import re
import secrets
import sqlite3
from pathlib import Path
import server

def ask_password():
    password = getpass.getpass('Password (12+ characters): ')
    if len(password) < 12 or password != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords must match and contain at least 12 characters.')
    return password

def main():
    parser = argparse.ArgumentParser(description='CommonGround trusted operator tools')
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create-user')
    create.add_argument('--email', required=True)
    create.add_argument('--name', required=True)
    create.add_argument('--role', choices=['member','owner','manager','admin'], required=True)
    create.add_argument('--group', required=True)
    create.add_argument('--verified', action='store_true')
    create.add_argument('--training', action='append', default=[])
    reset = sub.add_parser('reset-password')
    reset.add_argument('--email', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('destination')
    args = parser.parse_args()
    server.init_db()
    if args.command == 'backup':
        destination = Path(args.destination)
        if destination.exists():
            raise SystemExit('Choose a new backup path; existing files will not be overwritten.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental replacement of an existing path.
        with destination.open('xb'):
            pass
        with server.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        print('Backup completed. Protect the backup like the live database.')
        return
    email = args.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 180:
        raise SystemExit('Supply a valid email address.')
    if args.command == 'create-user':
        if not 1 <= len(args.name.strip()) <= 100 or not 1 <= len(args.group.strip()) <= 100:
            raise SystemExit('Name and group must contain 1–100 characters.')
        if len(args.training) > 20 or any(not 1 <= len(x) <= 100 for x in args.training):
            raise SystemExit('Supply up to 20 training names of 1–100 characters.')
        with server.connect() as connection:
            if connection.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
                raise SystemExit('An account already exists for this email.')
        password = ask_password()
        uid = secrets.token_hex(10)
        with server.connect() as connection:
            connection.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(uid,args.name.strip(),email,server.password_hash(password),args.role,args.group.strip(),args.verified,json.dumps(args.training)))
            server.audit(connection,uid,None,None,'Account provisioned','Trusted console operator created '+args.role+' account; membership='+str(args.verified)+'; training='+', '.join(args.training))
        print('Account created. ID:',uid)
        print('Send access instructions through your institution’s approved channel.')
    else:
        with server.connect() as connection:
            user = connection.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
        if not user:
            raise SystemExit('Account not found.')
        password = ask_password()
        with server.connect() as connection:
            connection.execute('UPDATE users SET password=? WHERE id=?',(server.password_hash(password),user['id']))
            connection.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            server.audit(connection,user['id'],None,None,'Operator password reset','Trusted console operator reset password and revoked sessions')
        print('Password reset. Every previous session was revoked.')

if __name__ == '__main__':
    main()
