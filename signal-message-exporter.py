import os
import sys
import sqlite3
import logging
import argparse
from xml.dom import minidom
import base64


def run_cmd(cmd):
    logging.info(f"running command: {cmd}")
    r = os.popen(cmd)
    logging.info(r.read())
    rtn = r.close()
    if rtn is not None:
        logging.info(f"command failed: {cmd}")
        sys.exit(rtn)


def print_num_sms():
    q = "select count(*) as tally from sms where type in (20, 87, 23)"
    cursor.execute(q)
    (tally,) = cursor.fetchone()
    logging.info(f"Total num SMS messages: {tally}")


def print_num_signal():
    q = "select count(*) as tally from sms where type in (10485780, 10485783)"
    cursor.execute(q)
    (tally,) = cursor.fetchone()
    logging.info(f"Total number Signal messages: {tally}")


def print_num_mms():
    q = "select count(*) as tally from mms where msg_box in (20, 87, 23)"
    cursor.execute(q)
    (tally,) = cursor.fetchone()
    logging.info(f"Total num MMS messages: {tally}")


def print_num_signal_mms():
    q = "select count(*) as tally from mms where msg_box in (10485780, 10485783)"
    cursor.execute(q)
    (tally,) = cursor.fetchone()
    logging.info(f"Total number Signal Multimedia messages: {tally}")


def get_recipients():
    cursor.execute("select * from recipient")
    contacts_by_id = {}
    for c in cursor.fetchall():
        c = dict(c)
        if 'phone' in c and c['phone']:
            clean_number = c["phone"].replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            contacts_by_id[c['_id']] = {'phone': clean_number, 'name': c['system_display_name']}

    return contacts_by_id


def get_groups():
    cursor.execute("select group_id, recipient_id, members from groups")
    groups_by_id = {}
    for g in cursor.fetchall():
        g = dict(g)
        if g['members']:
            for member_recipient_id in g['members'].split(','):
                if g['recipient_id'] not in groups_by_id:
                    groups_by_id[g['recipient_id']] = []
                groups_by_id[g['recipient_id']].append(ADDRESSES[int(member_recipient_id)])
    return groups_by_id


def xml_create_sms(root, row):
    sms = root.createElement('sms')
    sms.setAttribute('protocol', '0')
    sms.setAttribute('subject', 'null')
    sms.setAttribute('date', str(row['date_sent']))
    sms.setAttribute('service_center', row['service_center'])
    sms.setAttribute('toa', 'null')
    sms.setAttribute('sc_toa', 'null')
    sms.setAttribute('read', '1')
    sms.setAttribute('status', '-1')

    try:
        sms.setAttribute('address', ADDRESSES[row["address"]]['phone'])
        sms.setAttribute('contact_name', ADDRESSES[row["address"]]['name'])
    except KeyError:
        logging.error(f'Could not find contact in the recipient table with ID: {row["address"]}, sms looks like: {row}')
        sys.exit(1)

    try:
        t = TYPES[row['type']]
    except KeyError:
        t = 2  # default to received
    sms.setAttribute('type', str(t))
    sms.setAttribute('body', str(row['body']))
    return sms


def xml_create_mms(root, row, parts, addrs):
    mms = root.createElement('mms')
    mms.setAttribute('date', str(row["date"]))
    mms.setAttribute('ct_t', "application/vnd.wap.multipart.related")

    try:
        t = TYPES[row['msg_box']]
    except KeyError:
        t = 2  # default to received
    mms.setAttribute('msg_box', str(t))
    mms.setAttribute('rr', 'null')
    mms.setAttribute('sub', 'null')
    mms.setAttribute('read_status', '1')

    try:
        phone = ADDRESSES[row["address"]]['phone']
        name = ADDRESSES[row["address"]]['name']
    except KeyError:
        try:
            phone = GROUPS[row["address"]][0]['phone']
            name = GROUPS[row["address"]][0]['name']
        except (KeyError, IndexError):
            logging.error(f'Could not find contact in the recipient table with ID: {row["address"]}, mms looks like: {row}')
            sys.exit(1)

    mms.setAttribute('address', phone)
    mms.setAttribute('contact_name ', name)
    mms.setAttribute('m_id', 'null')
    mms.setAttribute('read', '1')
    mms.setAttribute('m_size', str(row['m_size']))
    mms.setAttribute('m_type', str(row['m_type']))
    mms.setAttribute('sim_slot', '0')

    for part in parts:
        mms.appendChild(xml_create_mms_part(root, part))

    # The type of address, 129 = BCC, 130 = CC, 151 = To, 137 = From
    if t == 1:
        type_address = 151
    else:
        type_address = 137
    type_address = 137  # todo
    for addr in addrs:
        mms.appendChild(xml_create_mms_addr(root, addr, type_address))
    return mms


def xml_create_mms_part(root, row):
    part = root.createElement('part')
    part.setAttribute("seq", str(row['seq']))
    part.setAttribute("ct", str(row['ct']))
    part.setAttribute("name", str(row['name']))
    part.setAttribute("chset", str(row['chset']))
    part.setAttribute("cl", str(row['cl']))
    part.setAttribute("text", str(row['caption']))

    filename = f"bits/Attachment_{row['_id']}_{row['unique_id']}.bin"
    try:
        with open(filename, 'rb') as f:
            b = base64.b64encode(f.read())
            base64_encoded_file_data = str(b.decode())
    except FileNotFoundError:
        logging.error(f'Exiting: file not found: {filename} for part: {row}')
        sys.exit(1)

    part.setAttribute("data", base64_encoded_file_data)
    return part


def xml_create_mms_addr(root, address, address_type):
    addr = root.createElement('addr')
    addr.setAttribute("address", str(address['phone']))
    addr.setAttribute("type", str(address_type))
    addr.setAttribute("charset", "UTF-8")  # todo
    return addr


parser = argparse.ArgumentParser(description='Export Signal messages to an XML file compatible with SMS Backup & Restore')
# parser.add_argument('args', nargs='*')
# parser.add_argument('--mode', '-m', dest='mode', action='store', help="mode should be one sms-only, sms-mms-only, sms-mms-signal")
parser.add_argument('--verbose', '-v', dest='verbose', action='store_true', help='Make logging more verbose')
args = parser.parse_args()
#
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG if args.verbose else logging.INFO)

if not os.environ.get("SIG_KEY"):
    logging.error("Missing environment variable SIG_KEY, try eg: export SIG_KEY=123456789101112131415161718192")
    sys.exit(1)
if not os.environ.get("SIG_FILE"):
    logging.error("Missing environment variable SIG_FILE, try eg: export SIG_FILE=signal-2022-01-01-01-01-01.backup")
    sys.exit(1)

# if not os.path.exists('bits/'):
run_cmd("mkdir -p bits")
run_cmd("rm -f sms-backup-restore.xml")
run_cmd(f'/usr/bin/signalbackup-tools --input {os.environ["SIG_FILE"]} --output bits/ --password {os.environ["SIG_KEY"]} --no-showprogress')

# parse the sqlite database generated by github.com/bepaald/signalbackup-tools
conn = sqlite3.connect(os.path.join("bits", "database.sqlite"))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor2 = conn.cursor()

TYPES = {
    23: 1,        # sent
    87: 1,        # sent
    10485780: 1,  # sent
    20: 2,        # received
    10485783: 2,  # received
}

ADDRESSES = get_recipients()
GROUPS = get_groups()

print_num_sms()
print_num_signal()
print_num_mms()
print_num_signal_mms()

root = minidom.Document()
smses = root.createElement('smses')
root.appendChild(smses)

counter = 0

cursor.execute('select * from sms order by date_sent')
for row in cursor.fetchall():
    counter += 1
    row = dict(row)
    logging.info(f'sms processing: {row["_id"]}')
    smses.appendChild(xml_create_sms(root, row))

cursor.execute('select * from mms order by date')
for row in cursor.fetchall():
    counter += 1
    row = dict(row)
    logging.info(f'mms processing: {row["_id"]}')

    parts = []
    cursor2.execute(f'select * from part where mid = {row["_id"]} order by seq')
    for part in cursor2.fetchall():
        parts.append(dict(part))

    addrs = []
    if row['address'] in GROUPS:
        addrs = GROUPS[row['address']]
    elif row['address'] in ADDRESSES:
        addrs.append(ADDRESSES[row['address']])

    smses.appendChild(xml_create_mms(root, row, parts, addrs))


# update the total count
smses.setAttribute("count", str(counter))

# xml_str = root.toprettyxml(indent="\t")
with open("sms-backup-restore.xml", "w") as f:
    f.write(root.toxml(encoding="utf-8", standalone="yes").decode())

conn.commit()
cursor.close()

run_cmd("rm -rf bits")
logging.info("Complete.")
logging.info("Created: sms-backup-restore.xml")
logging.info("Now install SMS Backup & Restore and choose this file to restore")
