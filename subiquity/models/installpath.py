# Copyright 2018 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os


log = logging.getLogger("subiquity.models.installpath")


class InstallpathModel(object):
    """Model representing install options"""

    path = 'ubuntu'
    results = {}

    def __init__(self, target, sources=None):
        self.target = target
        self.cmdline_sources = sources
        self.sources = {}
        if sources:
            self.path = 'cmdline'

    @property
    def paths(self):
        cmdline = []
        if self.cmdline_sources:
            cmdline = [(_('Install from cli provided sources'), 'cmdline')]
        return cmdline + [
            (_('Install Ubuntu'),                         'ubuntu'),
            (_('Install MAAS bare-metal cloud (region)'), 'maas_region'),
            (_('Install MAAS bare-metal cloud (rack)'),   'maas_rack'),
        ]

    def update(self, results):
        self.results = results

    def render(self):
        src_map = {
            'ubuntu': ['cp:///media/filesystem'],
            'maas_region': ['cp:///media/region'],
            'maas_rack': ['cp:///media/rack'],
            'cmdline': self.cmdline_sources,
            }
        src_list = src_map[self.path]

        self.sources = {}
        for n, u in enumerate(src_list):
            self.sources[self.path + "%02d" % n] = u

        config = {
            'sources': self.sources,
            }

        def t(path):
            return os.path.join(self.target, path)

        if self.path == 'maas_region':
            config['debconf_selections'] = {
                'maas-username': ('maas-region-controller maas/username '
                                  'string %s' % self.results['username']),
                'maas-password': ('maas-region-controller maas/password '
                                  'password %s' % self.results['password']),
            }
            config['late_commands'] = {
                # Maintainer scripts cache self.results, from config files, if
                # they # exist.  These shouldn't exist, since this was fixed in
                # livecd-rootfs but remove these, just to be sure.
                '900-maas': ['rm', '-f', t('etc/maas/rackd.conf')],
                '901-maas': ['rm', '-f', t('etc/maas/region.conf')],
                # All the crazy things are workarounds for maas maintainer
                # scripts deficiencies see:
                # LP: #1766209
                # LP: #1766211
                # LP: #1766214
                # LP: #1766218
                # LP: #1766241
                #
                # uuid is not initialized by reconfigure, maybe it should,
                # if it is at all used make it so, to make it match the
                # udeb/deb installs
                '902-maas': ['curtin', 'in-target', '--',
                             'maas-rack', 'config', '--init'],
                # this should do setups of maas-url for the rack controller,
                # and secret if needed.
                '903-maas': ['curtin', 'in-target', '--', 'dpkg-reconfigure',
                             '-u', '-fnoninteractive', 'maas-rack-controller'],
                # Below are workaround to make postgresql database running,
                # and invoke-rc.d --force to not faill and a running postgresql
                # is needed, to change the role password and to create an admin
                # user.
                '904-maas': ['mount', '-o', 'bind', '/proc', t('proc')],
                '905-maas': ['mount', '-o', 'bind', '/sys', t('sys')],
                '906-maas': ['mount', '-o', 'bind', '/dev', t('dev')],
                '907-maas': ['mount', '-o', 'bind', '/dev/shm', t('dev/shm')],
                '908-maas': ['mount', '-o', 'bind', t('bin/true'),
                             t('usr/sbin/invoke-rc.d')],
                '909-maas': ['chroot', self.target, 'sh', '-c',
                             'pg_ctlcluster --skip-systemctl-redirect '
                             '$(/bin/ls /var/lib/postgresql/) main start'],
                # These are called like this, because reconfigure doesn't
                # create nor change an admin user account, nor regens the
                # semi-autogenerated maas-url
                '910-maas':
                    ['chroot', self.target, 'sh', '-c', (
                        'debconf -fnoninteractive -omaas-region-controller '
                        '/var/lib/dpkg/info/maas-region-controller.config '
                        'configure')],
                '911-maas':
                    ['chroot', self.target, 'sh', '-c', (
                        'debconf -fnoninteractive -omaas-region-controller '
                        '/var/lib/dpkg/info/maas-region-controller.postinst '
                        'configure')],
                '912-maas': ['chroot', self.target, 'sh', '-c', (
                        'pg_ctlcluster --skip-systemctl-redirect '
                        '$(/bin/ls /var/lib/postgresql/) main stop')],
                '913-maas': ['umount', t('usr/sbin/invoke-rc.d')],
                '914-maas': ['umount', t('dev/shm')],
                '915-maas': ['umount', t('dev')],
                '916-maas': ['umount', t('sys')],
                '917-maas': ['umount', t('proc')],
            }
        elif self.path == 'maas_rack':
            config['debconf_selections'] = {
                'maas-url': ('maas-rack-controller '
                             'maas-rack-controller/maas-url '
                             'string %s' % self.results['url']),
                'maas-secret': ('maas-rack-controller '
                                'maas-rack-controller/shared-secret '
                                'password %s' % self.results['secret']),
            }
            config['late_commands'] = {
                '90-maas': ['rm', '-f', t('etc/maas/rackd.conf')],
                '91-maas': ['curtin', 'in-target', '--', 'maas-rack',
                            'config', '--init'],
                # maas-rack-controller is broken, and does db_input & go on
                # the password question in the postinst...  when it should have
                # been done in .config and it doesn't gracefully handle the
                # case of db_go returning 30 skipped
                '93-maas': ['curtin', 'in-target', '--', 'sh', '-c',
                            ('debconf -fnoninteractive -omaas-rack-controller '
                             '/var/lib/dpkg/info/maas-rack-controller.postinst'
                             ' configure || :')],
            }
        elif self.path != "ubuntu":
            raise ValueError("invalid Installpath %s" % self.path)
        return config
