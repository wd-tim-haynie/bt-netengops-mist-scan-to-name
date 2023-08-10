import requests
from os import getenv

def getch_windows():
    return msvcrt.getch().decode('utf-8')

def getch_unix():
    import sys, tty, termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

try:
    import msvcrt
    getch = getch_windows
except ImportError:
    getch = getch_unix


murl = 'https://api.mist.com/api/v1'
my_headers = {"Authorization": f"Token {getenv('MIST_TOKEN')}",
              "Content-Type": "application/json"}
sesh = requests.Session()
orgid = sesh.get(f"{murl}/self", headers=my_headers).json()['privileges'][0]['org_id']  # assumes only 1 item returned

sites = dict()
aps_added = list()
sitecode = str()


def main():
    siteid = Select_Site()
    GetSiteCode(siteid)

    keep_adding = True
    while keep_adding:
        aps = Load_APs(siteid)
        Add_APs(siteid, aps)
        print(f"\n{len(aps_added)} APs were added.")
        confirmation = input("Done adding APs? Confirm with 'y': ").lower()
        if confirmation == 'y':
            keep_adding = False

    print(f"Done adding APs. {len(aps_added)} APs were added.")
    for ap in aps_added:
        print(ap)

    sesh.close()


def Select_Site():
    url = f"{murl}/orgs/{orgid}/sites"

    sites_list = sesh.get(url, headers=my_headers).json()
    sites_list.sort(key=Name_Sort)

    site_num = 0
    for site in (sites_list):
        print(f"{site_num}: {site['name']}")
        site_num += 1

    confirmed = False
    while not confirmed:
        selection = IntCatch("\nWhich site? ")
        siteid = sites_list[selection]['id']
        confirmation = input(f"You selected {sites_list[selection]['name']}, confirm with 'y': ").lower()
        if confirmation == 'y':
            confirmed = True

    return siteid


def Name_Sort(dictionary):
    return dictionary['name']


def Load_APs(siteid):
    url = f"{murl}/sites/{siteid}/devices"

    # devices is a list of dictionaries. Each device is a single AP dict and its attributes
    aps = list()
    aps = sesh.get(url, headers=my_headers).json()
    aps.sort(key=Name_Sort)

    if len(aps) != 0:
        print("\nHere are the devices currently at the site:")
        for ap in aps:
            if ap['name'] == '':
                print(f"{ap['mac']}")
            else:
                print(ap['mac'], ap['name'])
    print(f"There is a total of {len(aps)} APs currently at the site")

    return aps


def Add_APs(siteid, aps):

    floor = ''
    confirmed = False
    while not confirmed:
        print("\nWhich floor are you adding APs to?")
        print("Include leading zeros if required (e.g. FLR3, FLR09, FLR24, LL, B1, P2, etc.).")
        floor = input("Leave blank for single floor sites: ").upper()

        if floor == '':
            confirmation = input("You entered nothing, so no floor name will be embedded. Confirm with 'y': ").lower()
            floor = '-'
        else:
            confirmation = input(f"{floor} will be embedded in the name as the floor number. Confirm with 'y': ")
            confirmation = confirmation.lower()
            floor = '-' + floor + '-'

        if confirmation == 'y':
            confirmed = True

    apnum = 0
    confirmed = False
    while not confirmed:
        apnum = IntCatch("\nStarting AP number: ")
        confirmation = input(f"We will start numbering from {apnum}. Confirm with 'y': ").lower()
        if confirmation == 'y':
            confirmed = True

    proceed = True
    while proceed:
        print("Scan or type AP MAC. Type 'p' to go back: ")
        mac = ScanMAC()
        mac = mac.replace(':', '')
        mac = mac.replace('.', '')
        mac = mac.replace('-', '')
        mac = mac.lower()

        if mac == 'p':
            proceed = False
        else:
            assigned = Assign(siteid, mac)
            if assigned:
                deviceid = GetDeviceID(siteid, mac)
                renamed, apnum = Rename(siteid, deviceid, sitecode, floor, apnum)
                if renamed:
                    apnum += 1

def GetDeviceID(siteid, mac):
    url = f"{murl}/sites/{siteid}/devices?mac={mac}"
    req = sesh.get(url, headers=my_headers)
    deviceid = req.json()[0]['id']

    return deviceid

def Assign(siteid, mac):
        assigned = False

        url = f"{murl}/orgs/{orgid}/inventory"
        my_params = {
            "op": "assign",
            "site_id": siteid,
            "macs": [mac],
            "no_reassign": "true" # prevents stealing from another site if already assigned
        }

        req = sesh.put(url, headers=my_headers, json=my_params)

        if req.json()['reason'] == ['does not exist']:
            print('FAILURE: This AP has not been claimed')
        elif len(req.json()['reason']) > 0:
            if req.json()['reason'][0].find('already assigned to site') > -1:
                site = req.json()['reason'][0].replace('already assigned to site ', '')
                url = f"{murl}/sites/{site}"
                req = sesh.get(url, headers=my_headers)
                name = req.json()['name']
                print(f"FAILURE: This AP is already assigned to {name}")
        elif len(req.json()['success']) == 1: # we found the AP and assigned it to the site. or maybe it was there
            assigned = True
        else:
            print("An unhandled error occurred and Tim needs to fix his shitty script")
            #pprint(req.json())

        return assigned


def Rename(siteid, deviceid, sitecode, floor, apnum):
    url = f"{murl}/sites/{siteid}/devices/{deviceid}"

    req = sesh.get(url, headers=my_headers)
    currentname = req.json()['name']

    if currentname != '':
        print("FAILURE: This AP already has a name:", currentname)
        renamed = False
        return renamed, apnum

    # check to see if the name exists at the site
    newapname = ''
    name_available = False
    while not name_available:
        newapname = f"{sitecode}-AP{floor}" + str(apnum).rjust(2, '0')
        url = f"{murl}/sites/{siteid}/devices?name={newapname}"
        req = sesh.get(url, headers=my_headers)
        if req.json() == []:
            name_available = True
        else:
            print(f"WARNING: {newapname} is already taken")
            apnum += 1

    my_params = {
        "name": newapname
    }

    url = f"{murl}/sites/{siteid}/devices/{deviceid}"

    req = sesh.put(url, headers=my_headers, json=my_params)

    mac = req.json()['mac']
    name = req.json()['name']

    print(f"Added {mac} to site as {name}")

    aps_added.append({"mac":mac,"name":name})

    renamed = True
    return renamed, apnum

def ScanMAC():

    allowed_chars = '1234567890abcdefABCDEF'
    allowed_delimiters = ':.-'
    num_chars = 0
    user_input = ''

    while num_chars < 12:
        char = getch()
        if char == '\r':  # carriage return or new line
            user_input = ''  # reset user input
            print("\nCleared current MAC.")
        elif char == '\x7f' or char == '\x08':  # backspace for Unix or Windows
            if user_input:  # Only do something if user_input is not empty
                user_input = user_input[:-1]  # Trim a character from user_input
                num_chars = max(0, num_chars - 1)  # Decrement num_chars
                print('\b \b', end='', flush=True)  # Move cursor back, overwrite with space, then move back again
        elif char in allowed_delimiters:
            user_input += char
            print (char, end='', flush=True)
        elif char in allowed_chars:
            user_input += char
            num_chars += 1
            print (char, end='', flush=True)
        elif char.lower() == 'p':
            return 'p'

    print()
    return user_input


def GetSiteCode(siteid):
    global sitecode

    url = f"{murl}/sites/{siteid}/setting"

    #pull existing site variables
    vars = sesh.get(url, headers=my_headers).json()['vars']

    try:
        sitecode = vars['SITE_CODE']
        print(f"This site has a defined site code as {sitecode}.")
    except KeyError:
        print("\nThis site does not have a site code assigned. Let's set one now.")

        code = ''
        confirmed = False
        while not confirmed:
            code = input("What should the site code be (e.g. VA, SMAT, HQ6110, BDR): ").upper()
            confirmation = input(f"The site will be assigned the site code {code}. Confirm with 'y': ").lower()
            if confirmation == 'y':
                confirmed = True

        vars['SITE_CODE'] = code
        my_params = {"vars": vars}

        sitecode = sesh.put(url, headers=my_headers, json=my_params).json()['vars']['SITE_CODE']

def IntCatch(promptstr):
    bad_input = True
    resp = ''
    while bad_input:
        try:
            resp = int(input(promptstr))
            bad_input = False
        except:
            print("Bad input, try again")

    return resp

main()
