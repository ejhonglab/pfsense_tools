#!/usr/bin/env python3

"""
Automates pfsense OpenVPN user creation, which includes:
    - making a user (with a key)
    - exporting client configuration
"""

import os
from os.path import join, exists
import getpass
from http.cookiejar import LWPCookieJar
import string
import secrets
import sys, logging

import mechanize
from bs4 import BeautifulSoup


def genpass():
    length = 12
    charset = string.ascii_letters + string.digits
    return ''.join([secrets.choice(charset) for _ in range(length)])


debug = False
if debug:
    logger = logging.getLogger("mechanize")
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.setLevel(logging.DEBUG)

br = mechanize.Browser()

if debug:
    br.set_debug_http(True)
    br.set_debug_responses(True)
    br.set_debug_redirects(True)

cj = LWPCookieJar('cookie.txt')
br.set_cookiejar(cj)

user_manager_url = 'http://gateway/system_usermanager.php'
response = br.open(user_manager_url)

# Check if it gives us back the login page. if so, authenticate.
html = response.read()
#print(html)
#print('login.css' in html.decode('utf-8'))
if 'login.css' in html.decode('utf-8'):
    br.open('http://gateway/index.php')
    br.select_form(class_='login')
    br.form['usernamefld'] = 'admin'
    passw = getpass.getpass(prompt='pfsense admin password:')
    br.form['passwordfld'] = passw
    response = br.submit()
    del passw

    html = response.read()
    if response.geturl().endswith('index.php'):
        raise ValueError('authentication failed. try another password.')

    response = br.open(user_manager_url)
    cj.save(ignore_discard=True, ignore_expires=True)

html = response.read()
soup = BeautifulSoup(html, 'html.parser')
existing_users = {e.find_all('td')[1].getText().strip() for e in
    soup.find('tbody').find_all('tr')}

user_prefix = 'hong'
max_incr_user_n = -1
for u in existing_users:
    if u.startswith(user_prefix):
        try:
            n = int(u[len(user_prefix):])
        except ValueError:
            continue
        if n > max_incr_user_n:
            max_incr_user_n = n
next_incr_user = user_prefix + str(max_incr_user_n + 1)

user = input('new username (default={}): '.format(next_incr_user))
if len(user) == 0:
    user = next_incr_user
else:
    if user in existing_users:
        raise ValueError('user {} already exists'.format(user))

export_dir = 'hongvpn_{}'.format(user)
if exists(export_dir):
    raise IOError('export dir {} already exists'.format(export_dir))

passw = getpass.getpass(prompt='password (default=random):')
if len(passw) == 0:
    passw = genpass()

br.open('http://gateway/system_usermanager.php?act=new')
br.select_form(action='/system_usermanager.php?act=new')
br.form['usernamefld'] = user
br.form['passwordfld1'] = passw
br.form['passwordfld2'] = passw
# "Full name"
#br.form['descr'] = 

br.form.find_control('showcert').items[0].selected = True

# "Descriptive name" for certificate
br.form['name'] = user + ' vpn'

response = br.submit()

response = br.open('http://gateway/vpn_openvpn_export.php')
html = response.read()
soup = BeautifulSoup(html, 'html.parser')
lines = [x for x in soup.prettify().splitlines() if x.startswith('servers[')]
lines = lines[slice(9, None, 5)]
user_id = None
for line in lines:
    line_user = line.split("'")[1]
    if line_user == user:
        user_id = int(line.split('][')[2])
        break
assert user_id is not None

export_url = ('http://gateway'
    '/vpn_openvpn_export.php?act=confinline&srvid=1&usrid={}&crtid=0'
    '&useaddr=serveraddr&verifyservercn=auto&blockoutsidedns=0&legacy=1'
    '&randomlocalport=0&usetoken=0&usepkcs11=0&pkcs11providers=&pkcs11id'
    '=&advancedoptions=script-security%202%0Aup%20%2Fetc%2Fopenvpn%2Fupdate'
    '-resolv-conf%0Adown%20%2Fetc%2Fopenvpn%2Fupdate-resolv-conf%0Aauth-user'
    '-pass%20hong_vpn_user_and_pass.txt'
).format(user_id)

print('exporting config to {}'.format(export_dir))
print('copy the files it contains to /etc/openvpn on the client computer')
os.mkdir(export_dir)
br.retrieve(export_url, filename=join(export_dir,
    'hongvpn_{}.conf'.format(user)))

with open(join(export_dir, 'hong_vpn_user_and_pass.txt'), 'w') as f:
    f.write(user + '\n')
    f.write(passw + '\n')

