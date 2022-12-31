import os
import sys
import sqlite3
import logging
import argparse
from xml.dom import minidom
import base64
from shutil import which, rmtree


def run_cmd(cmd):
    logging.info(f"running command: {cmd}")
    r = os.popen(cmd)
    logging.info(r.read())
    rtn = r.close()
    if rtn is not None:
        logging.error(f"command failed: {cmd}")
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
    logging.info(f"Total number Signal media messages: {tally}")


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
                try:
                    groups_by_id[g['recipient_id']].append(ADDRESSES[int(member_recipient_id)])
                except KeyError:
                    logging.info(f"Unable to find a contact on your phone with ID: {member_recipient_id}")
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
        phone = ADDRESSES[row["address"]]['phone']
        name = ADDRESSES[row["address"]]['name']
    except KeyError:
        try:
            phone = GROUPS[row["address"]][0]['phone']
            name = GROUPS[row["address"]][0]['name']
        except (KeyError, IndexError):
            logging.error(f'Could not find contact in the recipient table with ID: {row["address"]}, sms looks like: {row}')

    sms.setAttribute('address', phone)
    sms.setAttribute('contact_name ', name)

    try:
        t = TYPES[int(row['type'])]
    except KeyError:
        t = 1  # default to received
    sms.setAttribute('type', str(t))
    sms.setAttribute('body', str(row['body']))
    return sms


def xml_create_mms(root, row, parts, addrs):

    if 'recipient_id' in row:
        receiver = row['recipient_id']
    elif 'address' in row:
        receiver = row['address']
    else:
        logging.error(f'No message receiver detected in mms: {row}')
        raise Exception(f'No message receiver detected in mms: {row}')

    mms = root.createElement('mms')
    mms.setAttribute('date', str(row["date"]))
    mms.setAttribute('ct_t', "application/vnd.wap.multipart.related")

    try:
        t = TYPES[int(row['msg_box'])]
    except KeyError:
        t = 1  # default to received
    mms.setAttribute('msg_box', str(t))
    mms.setAttribute('rr', 'null')
    mms.setAttribute('sub', 'null')
    mms.setAttribute('read_status', '1')

    phone = ""
    name = ""
    tilda = ""
    space = ""

    try:
        phone = ADDRESSES[receiver]['phone']
        name = ADDRESSES[receiver]['name']
    except KeyError:
        try:
            if receiver in GROUPS and len(GROUPS[receiver]):
                for p in GROUPS[receiver]:
                    if "phone" in p and p["phone"]:
                        phone += tilda + str(p["phone"])
                        tilda = "~"
                    if "name" in p and p["name"]:
                        name += space + str(p["name"])
                        space = ", "
        except (KeyError, IndexError) as e:
            logging.error(f'Could not find contact in the recipient table with ID: {row["address"]}, mms looks like: {row}, error: {e}')

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
        logging.error(f'File not found for media message: {filename} for part: {row}')
        raise

    part.setAttribute("data", base64_encoded_file_data)
    return part


def xml_create_mms_addr(root, address, address_type):
    addr = root.createElement('addr')
    addr.setAttribute("address", str(address['phone']))
    addr.setAttribute("type", str(address_type))
    addr.setAttribute("charset", "UTF-8")  # todo
    return addr


def is_tool(name):
    """Check whether `name` is on PATH and marked as executable."""
    # from whichcraft import which
    return which(name) is not None


parser = argparse.ArgumentParser(description='Export Signal messages to an XML file compatible with SMS Backup & Restore')
# parser.add_argument('args', nargs='*')
# parser.add_argument('--mode', '-m', dest='mode', action='store', help="mode should be one sms-only, sms-mms-only, sms-mms-signal")
parser.add_argument('--verbose', '-v', dest='verbose', action='store_true', help='Make logging more verbose')
args = parser.parse_args()
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG if args.verbose else logging.INFO)

PLATFORM = sys.platform

if PLATFORM == 'win32':
    BKP_TOOL = 'signalbackup-tools'
elif PLATFORM in ['linux', 'linux2']:
    BKP_TOOL = '/usr/bin/signalbackup-tools'
else:
    BKP_TOOL = None

if not is_tool(BKP_TOOL):
    BKP_TOOL = input(r'Could not find signalbackup-tools, please input full path to executable: ')

SIG_KEY = os.environ.get("SIG_KEY", '')
SIG_FILE = os.environ.get("SIG_FILE", '')

if not os.environ.get("SIG_KEY"):
    SIG_KEY = input("Could not find SIG_KEY environment variable, please input here: ")
if not os.environ.get("SIG_FILE"):
    SIG_FILE = input(r"Could not find SIG_FILE environment variable, please input full path to Signal backupfile here: ")

logging.info('Recreating temporary export dir')
rmtree('bits', ignore_errors=True)
os.makedirs('bits', exist_ok=True)
try:
    os.remove('sms-backup-restore.xml')
    logging.info('Removed existing sms-backup-restore.xml')
except FileNotFoundError:
    pass

logging.info('Starting signalbackup-tools')
run_cmd(f'{BKP_TOOL} --input {SIG_FILE} --output bits/ --password {SIG_KEY} --no-showprogress')
logging.info('Finished signalbackup-tools')
logging.info('Parsing the sqlite database bits/database.sqlite')

# parse the sqlite database generated by github.com/bepaald/signalbackup-tools
conn = sqlite3.connect(os.path.join("bits", "database.sqlite"))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor2 = conn.cursor()

TYPES = {
    23:          2,  # me sent
    87:          2,  # me sent
    10485783:    2,  # me sent
    10485780:    1,  # received
    20:          1,  # received
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

sms_counter = 0
sms_errors = 0
mms_counter = 0
mms_errors = 0

logging.info('Starting SMS and Signal text message export')

cursor.execute('select * from sms order by date_sent')
for row in cursor.fetchall():
    sms_counter += 1
    row = dict(row)
    logging.debug(f'SMS processing: {row["_id"]}')
    try:
        smses.appendChild(xml_create_sms(root, row))
    except Exception as e:
        logging.error(f"Failed to export this text message: {row} because {e}")
        sms_errors += 1
        continue

logging.info(f'Finished text message export. Messages exported: {sms_counter} Errors: {sms_errors}')
logging.info('Starting MMS and Signal media message export')

cursor.execute('select * from mms order by date')
for row in cursor.fetchall():
    mms_counter += 1
    row = dict(row)
    logging.debug(f'MMS processing: {row["_id"]}')

    parts = []
    cursor2.execute(f'select * from part where mid = {row["_id"]} order by seq')
    for part in cursor2.fetchall():
        parts.append(dict(part))

    addrs = []
    if row['address'] in GROUPS:
        addrs = GROUPS[row['address']]
    elif row['address'] in ADDRESSES:
        addrs.append(ADDRESSES[row['address']])

    try:
        smses.appendChild(xml_create_mms(root, row, parts, addrs))
    except Exception as e:
        logging.error(f"Failed to export this media message: {row} because {e}")
        mms_errors += 1
        continue

logging.info(f'Finished media export. Messages exported: {mms_counter} Errors: {mms_errors}')

# update the total count
smses.setAttribute("count", str(sms_counter + mms_counter))

with open("sms-backup-restore.xml", "w", encoding="utf-8") as f:
    root.writexml(f, encoding="utf-8", standalone="yes")

conn.commit()
cursor.close()

rmtree('bits', ignore_errors=True)
logging.info("Complete.")
logging.info("Created: sms-backup-restore.xml")
logging.info("Now install SMS Backup & Restore and choose this file to restore")
if int(sms_errors + mms_errors) > 0:
    logging.error(f"WARNING: {sms_errors + mms_errors} messages were skipped! I.e. Not all messages were exported successfully. See output above for the messages that were skipped")
