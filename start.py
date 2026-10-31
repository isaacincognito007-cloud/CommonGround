"""Local first-run setup. Isaac Shiloah Herbert V · ISAAC.INCOGNITO007."""
import getpass
import os
import sys
import server

def main():
    server.init_db()
    with server.connect() as connection:
        empty = connection.execute('SELECT 1 FROM users LIMIT 1').fetchone() is None
    if empty:
        print('CommonGround · Campus workspace setup')
        print('Create a password for the five fictional campus accounts.')
        print('Use isolated sample accounts for local exploration only.')
        password = os.environ.get('CG_SEED_PASSWORD')
        if not password:
            password = getpass.getpass('Initial account password (12+ characters): ')
            if getpass.getpass('Confirm password: ') != password:
                raise SystemExit('Passwords did not match. Run setup again.')
        if len(password) < 12:
            raise SystemExit('Use at least 12 characters. Run setup again.')
        os.environ['CG_SEED_PASSWORD'] = password
        server.init_db(True)
        os.environ.pop('CG_SEED_PASSWORD', None)
        print('Accounts: member, newcomer, owner, manager, admin @campus.example')
        print('Open http://127.0.0.1:8000 unless you configured another host or port.')
    server.main()

if __name__ == '__main__':
    main()
