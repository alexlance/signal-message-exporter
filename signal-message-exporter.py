import os
import sys
import sqlite3
import logging
import argparse
import xml.dom.minidom
import base64
from shutil import which, rmtree  # noqa


# Minidom bug: https://github.com/python/cpython/issues/50002
# In theory this monkey patches minidom to encode line breaks in attributes,
# but unfortunately there's a "replace" method not found error when I uncomment it
# def _write_data(writer, data, isAttrib=False):
#     "Writes datachars to writer."
#     if isAttrib:
#         data = data.replace("\r", "&#xD;").replace("\n", "&#xA;")
#         data = data.replace("\t", "&#x9;")
#     writer.write(data)
# xml.dom.minidom._write_data = _write_data  # noqa
#
#
# def writexml(self, writer, indent="", addindent="", newl=""):
#     # indent = current indentation
#     # addindent = indentation to add to higher levels
#     # newl = newline string
#     writer.write(indent + "<" + self.tagName)
#
#     attrs = self._get_attributes()
#     a_names = attrs.keys()
#     # a_names.sort()
#
#     for a_name in a_names:
#         writer.write(" %s=\"" % a_name)
#         _write_data(writer, attrs[a_name].value, isAttrib=True)
#         writer.write("\"")
#     if self.childNodes:
#         writer.write(">%s" % (newl))
#         for node in self.childNodes:
#             node.writexml(writer, indent + addindent, addindent, newl)
#         writer.write("%s</%s>%s" % (indent, self.tagName, newl))
#     else:
#         writer.write("/>%s" % (newl))
# xml.dom.minidom.Element.writexml = writexml  # noqa


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
            contacts_by_id[c['_id']] = {'phone': clean_number, 'name': c['system_display_name'], 'recipient_id': c['_id']}
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


def xml_create_sms(root, row, addrs):
    sms = root.createElement('sms')
    sms.setAttribute('protocol', '0')
    sms.setAttribute('subject', 'null')
    sms.setAttribute('date', str(row['date_sent']))
    sms.setAttribute('service_center', row['service_center'])
    sms.setAttribute('toa', 'null')
    sms.setAttribute('sc_toa', 'null')
    sms.setAttribute('read', '1')
    sms.setAttribute('status', '-1')

    phone = ""
    name = ""
    tilda = ""
    space = ""

    if addrs and len(addrs):
        for p in addrs:
            if "phone" in p and p["phone"]:
                phone += tilda + str(p["phone"])
                tilda = "~"
            if "name" in p and p["name"]:
                name += space + str(p["name"])
                space = ", "

    sms.setAttribute('address', phone)
    sms.setAttribute('contact_name ', name)

    try:
        t = TYPES[int(row['type'])]
    except KeyError:
        t = 1  # default to received
    sms.setAttribute('type', str(t))
    sms.setAttribute('body', str(row.get('body', '')))
    return sms


def xml_create_mms(root, row, parts, addrs, sender):
    mms = root.createElement('mms')
    partselement = root.createElement('parts')
    addrselement = root.createElement('addrs')
    mms.setAttribute('date', str(row["date"]))
    mms.setAttribute('ct_t', "application/vnd.wap.multipart.related")

    # msg_box - The type of message, 1 = Received, 2 = Sent, 3 = Draft, 4 = Outbox
    try:
        t = TYPES[int(row.get('msg_box', 20))]
    except KeyError:
        t = 1
    mms.setAttribute('msg_box', str(t))
    mms.setAttribute('rr', 'null')
    mms.setAttribute('sub', 'null')
    mms.setAttribute('read_status', '1')

    phone = ""
    name = ""
    tilda = ""
    space = ""

    if addrs and len(addrs):
        for p in addrs:
            if "phone" in p and p["phone"]:
                phone += tilda + str(p["phone"])
                tilda = "~"
            if "name" in p and p["name"]:
                name += space + str(p["name"])
                space = ", "

    mms.setAttribute('address', phone)
    mms.setAttribute('contact_name ', name)
    mms.setAttribute('m_id', 'null')
    mms.setAttribute('read', '1')
    mms.setAttribute('m_size', str(row['m_size']))
    mms.setAttribute('m_type', str(row['m_type']))
    mms.setAttribute('sim_slot', '0')

    if parts or row.get('body', ''):
        mms.appendChild(partselement)
        if row.get('body', ''):
            partselement.appendChild(xml_create_mms_text_part(root, row.get('body', '')))
        else:
            for part in parts:
                partselement.appendChild(xml_create_mms_part(root, part))

    if addrs:
        mms.appendChild(addrselement)

    for addr in addrs:
        # The type of address, 129 = BCC, 130 = CC, 151 = To, 137 = From
        # group alex, ben, meg: alex sends message, alex=From, ben and meg=To
        # msg_box - The type of message, 1 = Received, 2 = Sent, 3 = Draft, 4 = Outbox
        if sender == addr["phone"]:
            type_address = 137
        else:
            type_address = 151
        addrselement.appendChild(xml_create_mms_addr(root, addr, type_address))
    return mms


def xml_create_mms_part(root, row):
    part = root.createElement('part')
    part.setAttribute("seq", str(row['seq']))
    part.setAttribute("name", str(row['name']))
    part.setAttribute("chset", str(row['chset']))
    part.setAttribute("cl", str(row['cl']))
    part.setAttribute("ct", str(row['ct']))

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


def xml_create_mms_text_part(root, body=''):
    if body:
        part = root.createElement('part')
        part.setAttribute("seq", "0")
        part.setAttribute("ct", "text/plain")
        part.setAttribute("text", body)
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
cursor3 = conn.cursor()

TYPES = {
    23:          2,  # me sent
    87:          2,  # me sent
    10485783:    2,  # me sent
    10485780:    1,  # received
    20:          1,  # received
    11075607:    1,  # received (?)
}

ADDRESSES = get_recipients()
GROUPS = get_groups()

print_num_sms()
print_num_signal()
print_num_mms()
print_num_signal_mms()

root = xml.dom.minidom.Document()
smses = root.createElement('smses')
root.appendChild(smses)

sms_counter = 0
sms_errors = 0
mms_counter = 0
mms_errors = 0

logging.info('Starting SMS and Signal text message export')

cursor.execute('select sms.*, thread.thread_recipient_id as receiver from sms left join thread on sms.thread_id = thread._id order by sms.date_sent desc')
for row in cursor.fetchall():
    sms_counter += 1
    row = dict(row)
    logging.debug(f'SMS processing: {row["_id"]}')

    addrs = []
    if row["receiver"] in GROUPS:
        addrs = GROUPS[row["receiver"]]
    elif row["receiver"] in ADDRESSES:
        addrs.append(ADDRESSES[row["receiver"]])

    try:
        smses.appendChild(xml_create_sms(root, row, addrs))
    except Exception as e:
        logging.error(f"Failed to export this text message: {row} because {e}")
        sms_errors += 1
        continue

logging.info(f'Finished text message export. Messages exported: {sms_counter} Errors: {sms_errors}')
logging.info('Starting MMS and Signal media message export')

cursor.execute('select mms.*, thread.thread_recipient_id as receiver, recipient.phone as senderphone from mms left join thread on mms.thread_id = thread._id left join recipient on mms.address = recipient._id order by mms.date desc')
for row in cursor.fetchall():
    mms_counter += 1
    row = dict(row)
    logging.debug(f'MMS processing: {row["_id"]}')

    parts = []
    cursor2.execute(f'select * from part where mid = {row["_id"]} order by seq')
    for part in cursor2.fetchall():
        parts.append(dict(part))

    addrs = []
    sender = ""
    if row["receiver"] in GROUPS:
        addrs = GROUPS[row["receiver"]]
        if row["address"] == row["receiver"]:
            # Not sure if we're going out on a limb by assuming that the only
            # recipient with a UUID will be the one having the phone number of
            # the device being backed up.
            cursor3.execute("select phone from recipient where uuid is not null")
            for row2 in cursor3.fetchall():
                sender = row2["phone"]
        else:
            sender = row["senderphone"]
    elif row["receiver"] in ADDRESSES:
        addrs.append(ADDRESSES[row["receiver"]])

    try:
        smses.appendChild(xml_create_mms(root, row, parts, addrs, sender))
    except Exception as e:
        logging.error(f"Failed to export this media message: {row} because {e}")
        mms_errors += 1
        continue

logging.info(f'Finished media export. Messages exported: {mms_counter} Errors: {mms_errors}')

# update the total count
smses.setAttribute("count", str(sms_counter + mms_counter))

with open("sms-backup-restore.xml", "w", encoding="utf-8") as f:
    root.writexml(f, indent="\t", addindent="\t", newl="\n", encoding="utf-8", standalone="yes")

conn.commit()
cursor.close()

rmtree('bits', ignore_errors=True)
logging.info("Complete.")
logging.info("Created: sms-backup-restore.xml")
logging.info("Now install SMS Backup & Restore and choose this file to restore")
if int(sms_errors + mms_errors) > 0:
    logging.error(f"WARNING: {sms_errors + mms_errors} messages were skipped! I.e. Not all messages were exported successfully. See output above for the messages that were skipped")
