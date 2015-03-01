"""Netlink Messages Interface (lib/msg.c).
https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c
https://github.com/thom311/libnl/blob/libnl3_2_25/include/netlink/msg.h

Netlink message construction/parsing interface.

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation version 2.1
of the License.
"""

import ctypes
import logging
import os
import resource
import string

from libnl.attr import nla_for_each_attr, nla_find, nla_is_nested, nla_len, nlmsg_data
from libnl.cache_mngt import nl_msgtype_lookup, nl_cache_ops_associate_safe
from libnl.linux_private.genetlink import GENL_HDRLEN, genlmsghdr
from libnl.linux_private.netlink import (nlmsghdr, NLMSG_ERROR, NLMSG_HDRLEN, NETLINK_GENERIC, NLMSG_NOOP, NLMSG_DONE,
                                         NLMSG_OVERRUN, NLM_F_REQUEST, NLM_F_MULTI, NLM_F_ACK, NLM_F_ECHO, NLM_F_ROOT,
                                         NLM_F_MATCH, NLM_F_ATOMIC, NLM_F_REPLACE, NLM_F_EXCL, NLM_F_CREATE,
                                         NLM_F_APPEND, nlmsgerr, NLMSG_ALIGN, nlattr)
from libnl.misc import bytearray_ptr
from libnl.netlink_private.netlink import BUG
from libnl.netlink_private.types import nl_msg, NL_MSG_CRED_PRESENT
from libnl.utils import __type2str

_LOGGER = logging.getLogger(__name__)
default_msg_size = resource.getpagesize()
NL_AUTO_PORT = 0
NL_AUTO_PID = NL_AUTO_PORT
NL_AUTO_SEQ = 0


def nlmsg_size(payload):
    """Calculates size of netlink message based on payload length.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L54

    Positional arguments:
    payload -- length of payload (integer).

    Returns:
    Size of netlink message without padding (integer).
    """
    return int(NLMSG_HDRLEN + payload)


nlmsg_msg_size = nlmsg_size  # Alias. https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L59


def nlmsg_total_size(payload):
    """Calculates size of netlink message including padding based on payload length.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L72

    This function is identical to nlmsg_size() + nlmsg_padlen().

    Positional arguments:
    payload -- length of payload (integer).

    Returns:
    Size of netlink message including padding (integer).
    """
    return int(NLMSG_ALIGN(nlmsg_msg_size(payload)))


def nlmsg_for_each_attr(nlh, hdrlen, rem):
    """Iterate over a stream of attributes in a message.
    https://github.com/thom311/libnl/blob/libnl3_2_25/include/netlink/msg.h#L123

    Positional arguments:
    nlh -- netlink message header (nlmsghdr class instance).
    hdrlen -- length of family header (integer).
    rem -- initialized to len, holds bytes currently remaining in stream (c_int).

    Returns:
    Generator yielding nl_attr instances.
    """
    return nla_for_each_attr(nlmsg_attrdata(nlh, hdrlen), nlmsg_attrlen(nlh, hdrlen), rem)


def nlmsg_datalen(nlh):
    """Return length of message payload.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L121

    Positional arguments:
    nlh -- Netlink message header (nlmsghdr class instance).

    Returns:
    Length of message payload in bytes.
    """
    return nlh.nlmsg_len - NLMSG_HDRLEN


nlmsg_len = nlmsg_datalen  # Alias. https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L126


def nlmsg_attrdata(nlh, hdrlen):
    """Head of attributes data.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L143

    Positional arguments:
    nlh -- Netlink message header (nlmsghdr class instance).
    hdrlen -- length of family specific header (integer).

    Returns:
    First attribute (nlattr class instance with others in its payload).
    """
    data = nlmsg_data(nlh)
    return nlattr(bytearray_ptr(data, NLMSG_ALIGN(hdrlen)))


def nlmsg_attrlen(nlh, hdrlen):
    """Length of attributes data.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L154

    nlh -- Netlink message header (nlmsghdr class instance).
    hdrlen -- length of family specific header (integer).

    Returns:
    Integer.
    """
    return max(nlmsg_len(nlh) - NLMSG_ALIGN(hdrlen), 0)


def nlmsg_valid_hdr(nlh, hdrlen):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L166

    Positional arguments:
    nlh -- netlink message header (nlmsghdr class instance).
    hdrlen -- integer.

    Returns True if valid, False otherwise.
    """
    return not nlh.nlmsg_len < nlmsg_msg_size(hdrlen)


def nlmsg_find_attr(nlh, hdrlen, attrtype):
    """Find a specific attribute in a netlink message.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L231

    Positional arguments:
    nlh -- netlink message header (nlmsghdr class instance).
    attrtype -- type of attribute to look for.

    Returns:
    The first attribute which matches the specified type (nlattr class instance).
    """
    return nla_find(nlmsg_attrdata(nlh, hdrlen), attrtype)


def nlmsg_alloc(len_=default_msg_size):
    """Allocate a new netlink message with maximum payload size specified.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L299

    Allocates a new netlink message without any further payload. The maximum payload size defaults to
    resource.getpagesize() or as otherwise specified with nlmsg_set_default_size().

    Returns:
    Newly allocated netlink message (nl_msg class instance).
    """
    len_ = max(nlmsghdr.SIZEOF, len_)
    nm = nl_msg()
    nm.nm_refcnt = 1
    nm.nm_nlh = nlmsghdr(bytearray(b'\0') * len_)
    nm.nm_protocol = -1
    nm.nm_size = len_
    nm.nm_nlh.nlmsg_len = nlmsg_total_size(0)
    _LOGGER.debug('msg 0x%x: Allocated new message, maxlen=%d', id(nm), len_)
    return nm


nlmsg_alloc_size = nlmsg_alloc  # Alias.


def nlmsg_inherit(hdr=None):
    """Allocate a new netlink message and inherit netlink message header.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L322

    Allocates a new netlink message and inherits the original message header. If `hdr` is not None it will be used as a
    template for the netlink message header, otherwise the header is left blank.

    Keyword arguments:
    hdr -- netlink message header template (nlmsghdr class instance).

    Returns:
    Newly allocated netlink message (nl_msg class instance).
    """
    nm = nlmsg_alloc()
    if hdr:
        new = nm.nm_nlh
        new.nlmsg_type = hdr.nlmsg_type
        new.nlmsg_flags = hdr.nlmsg_flags
        new.nlmsg_seq = hdr.nlmsg_seq
        new.nlmsg_pid = hdr.nlmsg_pid
    return nm


def nlmsg_alloc_simple(nlmsgtype, flags):
    """Allocate a new netlink message.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L346

    Positional arguments:
    nlmsgtype -- netlink message type (integer).
    flags -- message flags (integer).

    Returns:
    Newly allocated netlink message (nl_msg class instance).
    """
    nlh = nlmsghdr(nlmsg_type=nlmsgtype, nlmsg_flags=flags)
    msg = nlmsg_inherit(nlh)
    _LOGGER.debug('msg 0x%x: Allocated new simple message', id(msg))
    return msg


def nlmsg_set_default_size(max_):
    """Set the default maximum message payload size for allocated messages.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L365

    Positional arguments:
    max_ -- size of payload in bytes (integer).
    """
    global default_msg_size
    default_msg_size = max(nlmsg_total_size(0), max_)


def nlmsg_convert(hdr):
    """Convert a netlink message received from a netlink socket to a nl_msg.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L382

    Allocates a new netlink message and copies all of the data pointed to by `hdr` into the new message object.

    Positional arguments:
    hdr -- nlmsghdr class instance.

    Returns:
    New nl_msg class instance derived,
    """
    nm = nlmsg_alloc()
    nm.nm_nlh = hdr
    return nm


def nlmsg_append(msg, data):
    """Append data to tail of a netlink message.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L442

    Positional arguments:
    msg -- netlink message (nl_msg class instance).
    data -- data to add.

    Returns:
    0 on success or a negative error code.
    """
    msg.nm_nlh.payload.append(data)
    _LOGGER.debug('msg 0x%x: Appended %s', id(msg), type(data).__name__)
    return 0


def nlmsg_put(n, pid, seq, type_, flags):
    """Add a netlink message header to a netlink message.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L503

    Adds or overwrites the netlink message header in an existing message object.

    Positional arguments:
    n -- netlink message (nl_msg class instance).
    pid -- netlink process id or NL_AUTO_PID.
    seq -- sequence number of message or NL_AUTO_SEQ.
    type_ -- message type.
    flags -- message flags.

    Returns:
    nlmsghdr class instance.
    """
    if not n.nm_nlh:
        n.nm_nlh = nlmsghdr()
    nlh = n.nm_nlh
    nlh.nlmsg_type = type_
    nlh.nlmsg_flags = flags
    nlh.nlmsg_pid = pid
    nlh.nlmsg_seq = seq
    _LOGGER.debug('msg 0x%x: Added netlink header type=%d, flags=%d, pid=%d, seq=%d', id(n), type_, flags, pid, seq)
    return nlh


def nlmsg_hdr(msg):
    """Return actual Netlink message.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L536

    Returns the actual Netlink message casted to a nlmsghdr class instance.

    Positional arguments:
    msg -- Netlink message (nl_msg class instance).

    Returns:
    nlmsghdr class instance.
    """
    return msg.nm_nlh


def nlmsg_set_proto(msg, protocol):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L584

    Positional arguments:
    msg -- netlink message (nl_msg class instance).
    protocol -- integer.
    """
    msg.nm_protocol = protocol


def nlmsg_set_src(msg, addr):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L599"""
    msg.nm_src = addr


def nlmsg_get_dst(msg):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L614"""
    return msg.nm_dst


def nlmsg_get_creds(msg):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L625"""
    if msg.nm_flags & NL_MSG_CRED_PRESENT:
        return msg.nm_creds
    return None


nl_msgtypes = {
    NLMSG_NOOP: 'NOOP',
    NLMSG_ERROR: 'ERROR',
    NLMSG_DONE: 'DONE',
    NLMSG_OVERRUN: 'OVERRUN',
}


def nl_nlmsgtype2str(type_):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L646

    Positional arguments:
    type_ -- integer (e.g. nlh.nlmsg_type).

    Returns:
    String.
    """
    return str(__type2str(type_, nl_msgtypes))


def nl_nlmsg_flags2str(flags):
    """Netlink Message Flags Translations.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L664

    Positional arguments:
    flags -- integer.

    Returns:
    String.
    """
    all_flags = (
        ('REQUEST', NLM_F_REQUEST),
        ('MULTI', NLM_F_MULTI),
        ('ACK', NLM_F_ACK),
        ('ECHO', NLM_F_ECHO),
        ('ROOT', NLM_F_ROOT),
        ('MATCH', NLM_F_MATCH),
        ('ATOMIC', NLM_F_ATOMIC),
        ('REPLACE', NLM_F_REPLACE),
        ('EXCL', NLM_F_EXCL),
        ('CREATE', NLM_F_CREATE),
        ('APPEND', NLM_F_APPEND),
    )
    print_flags = []
    for k, v in all_flags:
        if not flags & v:
            continue
        flags &= ~v
        print_flags.append(k)
    if flags:
        print_flags.append('0x{0:x}'.format(flags))
    return ','.join(print_flags)


def dump_hex(start, prefix=0):
    """Converts `start` to hex and logs it, 16 bytes per log statement.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L760

    Positional arguments:
    start -- bytearray() instance.

    Keyword arguments:
    prefix -- additional number of whitespace pairs to prefix each log statement with.
    """
    prefix_whitespaces = '  ' * prefix
    limit = 16 - (prefix * 2)
    for line in (start[i:i+limit] for i in range(0, len(start), limit)):  # http://stackoverflow.com/a/9475354/1198943
        hex_line = ''.join('{0:02x} '.format(i) for i in line).ljust(limit * 3)
        ascii_line = ''.join(c if c in string.printable[:95] else '.' for c in (chr(i) for i in line))
        _LOGGER.debug('    %s%s%s', prefix_whitespaces, hex_line, ascii_line)


def print_hdr(msg):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L793

    Positional arguments:
    msg -- message to print (nl_msg class instance).
    """
    nlh = nlmsg_hdr(msg)

    _LOGGER.debug('    .nlmsg_len = %d', nlh.nlmsg_len)

    ops = nl_cache_ops_associate_safe(msg.nm_protocol, nlh.nlmsg_type)
    if ops:
        mt = nl_msgtype_lookup(ops, nlh.nlmsg_type)
        if not mt:
            raise BUG
        buf = '{0}::{1}'.format(ops.co_name, mt.mt_name)
    else:
        buf = nl_nlmsgtype2str(nlh.nlmsg_type)

    _LOGGER.debug('    .type = %d <%s>', nlh.nlmsg_type, buf)
    _LOGGER.debug('    .flags = %d <%s>', nlh.nlmsg_flags, nl_nlmsg_flags2str(nlh.nlmsg_flags))
    _LOGGER.debug('    .seq = %d', nlh.nlmsg_seq)
    _LOGGER.debug('    .port = %d', nlh.nlmsg_pid)


def print_genl_hdr(start):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L831

    Positional arguments:
    start -- bytearray() instance.
    """
    ghdr = genlmsghdr.from_buffer(start)
    _LOGGER.debug('  [GENERIC NETLINK HEADER] %d octets', GENL_HDRLEN)
    _LOGGER.debug('    .cmd = %d', ghdr.cmd)
    _LOGGER.debug('    .version = %d', ghdr.version)
    _LOGGER.debug('    .unused = %#d', ghdr.reserved)


def print_genl_msg(_, hdr, ops, payloadlen):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L831

    Positional arguments:
    hdr -- netlink message header (nlmsghdr class instance).
    ops -- cache operations (nl_cache_ops class instance).
    payloadlen -- length of payload in message (ctypes.c_int instance).

    Returns:
    data
    """
    data = bytearray(nlmsg_data(hdr))
    if payloadlen.value < GENL_HDRLEN:
        return data

    print_genl_hdr(data)
    payloadlen.value -= GENL_HDRLEN

    if ops:
        hdrsize = ops.co_hdrsize - GENL_HDRLEN
        if hdrsize > 0:
            if payloadlen.value < hdrsize:
                return data
            _LOGGER.debug('  [HEADER] %d octets', hdrsize)
            dump_hex(data)
            payloadlen.value -= hdrsize

    return data


def dump_attr(attr, prefix=0):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L862

    Positional arguments:
    attr -- nlattr class instance.

    Keyword arguments:
    prefix -- additional number of whitespace pairs to prefix each log statement with.
    """
    dump_hex(attr.payload, prefix)


def dump_attrs(attrs, _, prefix=0):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L869

    Positional arguments:
    attrs -- nlattr class instance.

    Keyword arguments:
    prefix -- additional number of whitespace pairs to prefix each log statement with.
    """
    prefix_whitespaces = '  ' * prefix
    for nla in nla_for_each_attr(attrs):
        alen = nla_len(nla)
        if nla.nla_type == 0:
            _LOGGER.debug('%s  [ATTR PADDING] %d octets', prefix_whitespaces, alen)
        else:
            is_nested = ' NESTED' if nla_is_nested(nla) else ''
            _LOGGER.debug('%s  [ATTR %02d%s] %d octets', prefix_whitespaces, nla.nla_type, is_nested, alen)

        if nla_is_nested(nla):
            dump_attrs(nla.payload, alen, prefix+1)
        else:
            dump_attr(nla, prefix)


def dump_error_msg(msg):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L908

    Positional arguments:
    msg -- message to print (nl_msg class instance).
    """
    hdr = nlmsg_hdr(msg)
    err = nlmsgerr.from_buffer(nlmsg_data(hdr))

    _LOGGER.debug('  [ERRORMSG] %d octets', err.SIZEOF)

    if nlmsg_len(hdr) >= err.SIZEOF:
        _LOGGER.debug('    .error = %d "%s"', err.error, os.strerror(-err.error))
        _LOGGER.debug('  [ORIGINAL MESSAGE] %d octets', hdr.SIZEOF)
        errmsg = nlmsg_inherit(err.msg)
        print_hdr(errmsg)


def print_msg(msg, hdr):
    """https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L929

    Positional arguments:
    msg -- netlink message (nl_msg class instance).
    hdr -- netlink message header (nlmsghdr class instance).
    """
    payloadlen = ctypes.c_int(nlmsg_len(hdr))
    attrlen = 0
    data = nlmsg_data(hdr)
    ops = nl_cache_ops_associate_safe(msg.nm_protocol, hdr.nlmsg_type)
    if ops:
        attrlen = nlmsg_attrlen(hdr, ops.co_hdrsize)
        payloadlen.value -= attrlen
    if msg.nm_protocol == NETLINK_GENERIC:
        data = print_genl_msg(msg, hdr, ops, payloadlen)
    if payloadlen.value:
        _LOGGER.debug('  [PAYLOAD] %d octets', payloadlen.value)
        dump_hex(data.ljust(payloadlen.value, b'\0'))
    if attrlen:
        attrs = nlmsg_attrdata(hdr, ops.co_hdrsize)
        dump_attrs(attrs, attrlen, 0)


def nl_msg_dump(msg):
    """Dump message in human readable format to handle.
    https://github.com/thom311/libnl/blob/libnl3_2_25/lib/msg.c#L970

    Positional arguments:
    msg -- message to print (nl_msg class instance).
    """
    hdr = nlmsg_hdr(msg)

    _LOGGER.debug('--------------------------   BEGIN NETLINK MESSAGE ---------------------------')

    _LOGGER.debug('  [NETLINK HEADER] %d octets', hdr.SIZEOF)
    print_hdr(msg)

    if hdr.nlmsg_type == NLMSG_ERROR:
        dump_error_msg(msg)
    elif nlmsg_len(hdr) > 0:
        print_msg(msg, hdr)

    _LOGGER.debug('---------------------------  END NETLINK MESSAGE   ---------------------------')
