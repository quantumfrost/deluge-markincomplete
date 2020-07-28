# -*- coding: utf-8 -*-
# Copyright (C) 2020 Chinmaya Dabral <quantcon11@gmail.com>
#
# Basic plugin template created by the Deluge Team.
#
# This file is part of MarkUnfinished and is licensed under GNU GPL 3.0, or later,
# with the additional special exception to link portions of this program with
# the OpenSSL library. See LICENSE for more details.
from __future__ import unicode_literals

import logging

import deluge.configmanager
# from deluge.core.rpcserver import export
from deluge.plugins.pluginbase import CorePluginBase
import deluge.component as component
from deluge._libtorrent import lt

# Some imports for type annotations
from deluge.core.torrentmanager import TorrentManager
from deluge.core.eventmanager import EventManager
from deluge.core.alertmanager import AlertManager
from deluge.core.core import Core

from twisted.internet import reactor

from .common import get_file_by_index

log = logging.getLogger(__name__)

DEFAULT_PREFS = {
    'extension': '!incomplete'
}

MAGNET_RENAME_DEFER_TIME = 2


class Core(CorePluginBase):
    core: Core
    torrent_manager: TorrentManager
    event_manager: EventManager
    alert_manager: AlertManager
    config: deluge.configmanager.ConfigManager
    extension: str
    eligibility_cache = {}

    def enable(self):
        log.info('Starting MarkUnfinished')
        self.config = deluge.configmanager.ConfigManager(
            'markunfinished.conf', DEFAULT_PREFS)
        self.extension = self.config['extension']
        # noinspection PyTypeChecker
        self.core = component.get('Core')
        # noinspection PyTypeChecker
        self.torrent_manager = component.get('TorrentManager')
        # noinspection PyTypeChecker
        self.event_manager = component.get('EventManager')
        # noinspection PyTypeChecker
        self.alert_manager = component.get("AlertManager")

        # Add progress_notification flag to libtorrent session so we actually receive TorrentFileCompletedEvent
        # Deluge alertmanager.py neglects adding this for some reason
        log.debug('Adding progress_notification alert_mask')
        session = self.core.session
        alert_mask = session.get_settings()['alert_mask']
        alert_mask |= lt.alert.category_t.progress_notification
        session.apply_settings({'alert_mask': alert_mask})

        # Register handlers
        log.debug('Registering handlers')
        self.event_manager.register_event_handler('TorrentAddedEvent', self.handle_torrent_added)
        self.event_manager.register_event_handler('TorrentFileCompletedEvent', self.handle_file_completed)
        self.alert_manager.register_handler('metadata_received_alert', self.handle_metadata_received)

    def disable(self):
        self.update_config()
        log.info('MarkUnfinished disabled')

    def update_config(self):
        log.info('Updating extension in config from %s to %s', self.config['extension'], self.extension)
        self.config['extension'] = self.extension

    def is_eligible(self, torrent_id):
        """ Checks to see if this torrent is eligible for being handled by this plugin.
        A torrent is eligible iff it doesn't have any files whose original names already end in
        the extension we are using. Almost all torrents should be eligible; this is just a precaution.
        We will also use memoization (per-session) to make it faster. """

        if torrent_id in self.eligibility_cache:
            eligibility = self.eligibility_cache[torrent_id]
            log.info('eligibility for %s is %s (cache hit)', torrent_id, eligibility)
            return eligibility

        try:
            torrent = self.torrent_manager[torrent_id]
        except KeyError:
            log.warning('torrent_id %s not found, returning not eligible', torrent_id)
            # We don't want to cache this value, because the torrent_id may be available in the future
            return False

        orig_files = torrent.get_orig_files()
        if not len(orig_files):
            log.info('torrent_id %s has zero files, returning not eligible', torrent_id)
            # Again, don't want to add this to cache, since the torrent could be waiting for metadata
            return False
        eligibility = all([not of['path'].endswith(self.extension) for of in orig_files])
        self.eligibility_cache[torrent_id] = eligibility
        log.info('eligibility for %s is %s (cache miss)', torrent_id, eligibility)
        return eligibility

    def handle_metadata_received(self, alert):
        try:
            torrent_id = str(alert.handle.info_hash())
        except RuntimeError:
            return

        log.info('metadata received for torrent_id %s, scheduling rename.', torrent_id)

        reactor.callLater(MAGNET_RENAME_DEFER_TIME, self.append_extension_if_eligible, torrent_id)

    def handle_torrent_added(self, torrent_id, from_state):
        """ Rename files if eligible """

        if from_state:
            log.debug('torrent_id %s added from state, skipping', torrent_id)
            return

        self.append_extension_if_eligible(torrent_id)

    def append_extension_if_eligible(self, torrent_id):
        """
        :param torrent_id: id of the torrent to rename files of
        :return: True if renamed, False if not eligible or no files.
            Returns False if there were zero files in the torrent, ex. if the metadata hasn't been
            downloaded yet for a magnet link
        """
        eligible = self.is_eligible(torrent_id)
        if not eligible:
            log.info('torrent_id %s not eligible, skipping', torrent_id)
            return False
        # Rename files
        torrent = self.torrent_manager[torrent_id]
        orig_files = torrent.get_orig_files()
        log.info('torrent_id %s is eligible, files to rename: %s', torrent_id, len(orig_files))
        progress = torrent.get_file_progress()
        new_files = []
        for of in orig_files:
            index, path = of['index'], of['path']
            # Only rename if file hasn't already completed
            # There may still be some race conditions possible where a file completes before the rename happens
            # If additionally, the file_completed callback runs before the rename, we may end up with
            # a completed file that has the extra extension. But this seems very unlikely.
            if progress[index] < 1.0:
                path = path + '.' + self.extension
                new_files.append((index, path))
        torrent.rename_files(new_files)
        return True

    def handle_file_completed(self, torrent_id, index):
        """ Rename files back to original if appropriate """

        log.debug('torrent_id %s file index %s completed', torrent_id, index)

        eligible = self.is_eligible(torrent_id)
        if not eligible:
            log.debug('torrent_id %s not eligible, skipping rename back to original', torrent_id)
            return

        torrent = self.torrent_manager[torrent_id]

        # Check if the file actually has the extension
        files = torrent.get_files()
        f = get_file_by_index(files, index)
        if f is None:
            return  # Shouldn't happen
        path = f['path']
        if not path.endswith(self.extension):
            log.info('torrent_id %s file index %s was never renamed in the first place. '
                     'Likely added while plugin was inactive.',
                     torrent_id, index)
            return  # It was never renamed. The torrent was likely added while the plugin was inactive

        # Finally, rename back to original name
        orig_files = torrent.get_orig_files()
        f = get_file_by_index(orig_files, index)
        orig_path = f['path']
        log.info('Renaming torrent_id %s file index %s back to original path: %s',
                 torrent_id, index, orig_path)
        torrent.rename_files([(index, orig_path)])

    def update(self):
        pass

    # @export
    # def set_config(self, config):
    #     """Sets the config dictionary"""
    #     for key in config:
    #         self.config[key] = config[key]
    #     self.config.save()
    #
    # @export
    # def get_config(self):
    #     """Returns the config dictionary"""
    #     return self.config.config
