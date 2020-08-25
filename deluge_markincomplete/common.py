# -*- coding: utf-8 -*-
# Copyright (C) 2020 Chinmaya Dabral <quantcon11@gmail.com>
#
# Basic plugin template created by the Deluge Team.
#
# This file is part of MarkIncomplete and is licensed under GNU GPL 3.0, or later,
# with the additional special exception to link portions of this program with
# the OpenSSL library. See LICENSE for more details.
from __future__ import unicode_literals

import os.path

from pkg_resources import resource_filename


def get_resource(filename):
    return resource_filename(__package__, os.path.join('data', filename))


def get_file_by_index(files, index):
    """ For lists of dicts returned by Torrent.get_files() and Torrent.get_orig_files() """
    # Seems like index i is always at the ith position in the list, so check that first
    f = files[index]
    if f['index'] == index:
        return f
    # Otherwise, check the rest of the elements
    for f in files:
        if f['index'] == index:
            return f
    # Unsuccessful
    return None
