# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack Foundation
# Copyright 2012-2013 IBM Corp.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Tests for database migrations. This test case reads the configuration
file test_migrations.conf for database connection settings
to use in the tests. For each connection found in the config file,
the test case runs a series of test cases to ensure that migrations work
properly both upgrading and downgrading, and that no data loss occurs
if possible.

There are also "opportunistic" tests for both mysql and postgresql in here,
which allows testing against all 3 databases (sqlite in memory, mysql, pg) in
a properly configured unit test environment.

For the opportunistic testing you need to set up a db named 'openstack_citest'
with user 'openstack_citest' and password 'openstack_citest' on localhost.
The test will then use that db and u/p combo to run the tests.

For postgres on Ubuntu this can be done with the following commands:

sudo -u postgres psql
postgres=# create user openstack_citest with createdb login password
      'openstack_citest';
postgres=# create database openstack_citest with owner openstack_citest;

"""

import collections
import commands
import ConfigParser
import datetime
import os
import urlparse
import uuid

from migrate.versioning import repository
import netaddr
import sqlalchemy
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import sqlite
import sqlalchemy.exc

import nova.db.sqlalchemy.migrate_repo
from nova.openstack.common import lockutils
from nova.openstack.common import log as logging
from nova.openstack.common import timeutils
from nova import test
import nova.virt.baremetal.db.sqlalchemy.migrate_repo


LOG = logging.getLogger(__name__)


def _get_connect_string(backend, user, passwd, database):
    """
    Try to get a connection with a very specific set of values, if we get
    these then we'll run the tests, otherwise they are skipped
    """
    if backend == "postgres":
        backend = "postgresql+psycopg2"
    elif backend == "mysql":
        backend = "mysql+mysqldb"
    else:
        raise Exception("Unrecognized backend: '%s'" % backend)

    return ("%(backend)s://%(user)s:%(passwd)s@localhost/%(database)s"
            % locals())


def _is_backend_avail(backend, user, passwd, database):
    try:
        connect_uri = _get_connect_string(backend, user, passwd, database)
        engine = sqlalchemy.create_engine(connect_uri)
        connection = engine.connect()
    except Exception:
        # intentionally catch all to handle exceptions even if we don't
        # have any backend code loaded.
        return False
    else:
        connection.close()
        engine.dispose()
        return True


def _have_mysql(user, passwd, database):
    present = os.environ.get('NOVA_TEST_MYSQL_PRESENT')
    if present is None:
        return _is_backend_avail('mysql', user, passwd, database)
    return present.lower() in ('', 'true')


def _have_postgresql(user, passwd, database):
    present = os.environ.get('NOVA_TEST_POSTGRESQL_PRESENT')
    if present is None:
        return _is_backend_avail('postgres', user, passwd, database)
    return present.lower() in ('', 'true')


def get_table(engine, name):
    """Returns an sqlalchemy table dynamically from db.

    Needed because the models don't work for us in migrations
    as models will be far out of sync with the current data."""
    metadata = sqlalchemy.schema.MetaData()
    metadata.bind = engine
    return sqlalchemy.Table(name, metadata, autoload=True)


def get_mysql_connection_info(conn_pieces):
    database = conn_pieces.path.strip('/')
    loc_pieces = conn_pieces.netloc.split('@')
    host = loc_pieces[1]
    auth_pieces = loc_pieces[0].split(':')
    user = auth_pieces[0]
    password = ""
    if len(auth_pieces) > 1:
        if auth_pieces[1].strip():
            password = "-p\"%s\"" % auth_pieces[1]

    return (user, password, database, host)


def get_pgsql_connection_info(conn_pieces):
    database = conn_pieces.path.strip('/')
    loc_pieces = conn_pieces.netloc.split('@')
    host = loc_pieces[1]

    auth_pieces = loc_pieces[0].split(':')
    user = auth_pieces[0]
    password = ""
    if len(auth_pieces) > 1:
        password = auth_pieces[1].strip()

    return (user, password, database, host)


class CommonTestsMixIn(object):
    """These tests are shared between TestNovaMigrations and
    TestBaremetalMigrations.

    BaseMigrationTestCase is effectively an abstract class, meant to be derived
    from and not directly tested against; that's why these `test_` methods need
    to be on a Mixin, so that they won't be picked up as valid tests for
    BaseMigrationTestCase.
    """
    def test_walk_versions(self):
        for key, engine in self.engines.items():
            self._walk_versions(engine, self.snake_walk)

    def test_mysql_opportunistically(self):
        self._test_mysql_opportunistically()

    def test_mysql_connect_fail(self):
        """
        Test that we can trigger a mysql connection failure and we fail
        gracefully to ensure we don't break people without mysql
        """
        if _is_backend_avail('mysql', "openstack_cifail", self.PASSWD,
                             self.DATABASE):
            self.fail("Shouldn't have connected")

    def test_postgresql_opportunistically(self):
        self._test_postgresql_opportunistically()

    def test_postgresql_connect_fail(self):
        """
        Test that we can trigger a postgres connection failure and we fail
        gracefully to ensure we don't break people without postgres
        """
        if _is_backend_avail('postgres', "openstack_cifail", self.PASSWD,
                             self.DATABASE):
            self.fail("Shouldn't have connected")


class BaseMigrationTestCase(test.TestCase):
    """Base class fort testing migrations and migration utils."""
    USER = None
    PASSWD = None
    DATABASE = None

    def __init__(self, *args, **kwargs):
        super(BaseMigrationTestCase, self).__init__(*args, **kwargs)

        self.DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__),
                                       'test_migrations.conf')
        # Test machines can set the NOVA_TEST_MIGRATIONS_CONF variable
        # to override the location of the config file for migration testing
        self.CONFIG_FILE_PATH = os.environ.get('NOVA_TEST_MIGRATIONS_CONF',
                                      self.DEFAULT_CONFIG_FILE)
        self.MIGRATE_FILE = nova.db.sqlalchemy.migrate_repo.__file__
        self.REPOSITORY = repository.Repository(
                        os.path.abspath(os.path.dirname(self.MIGRATE_FILE)))
        self.INIT_VERSION = 0

        self.snake_walk = False
        self.test_databases = {}
        self.migration = None
        self.migration_api = None

    def setUp(self):
        super(BaseMigrationTestCase, self).setUp()

        # Load test databases from the config file. Only do this
        # once. No need to re-run this on each test...
        LOG.debug('config_path is %s' % self.CONFIG_FILE_PATH)
        if os.path.exists(self.CONFIG_FILE_PATH):
            cp = ConfigParser.RawConfigParser()
            try:
                cp.read(self.CONFIG_FILE_PATH)
                defaults = cp.defaults()
                for key, value in defaults.items():
                    self.test_databases[key] = value
                self.snake_walk = cp.getboolean('walk_style', 'snake_walk')
            except ConfigParser.ParsingError, e:
                self.fail("Failed to read test_migrations.conf config "
                          "file. Got error: %s" % e)
        else:
            self.fail("Failed to find test_migrations.conf config "
                      "file.")

        self.engines = {}
        for key, value in self.test_databases.items():
            self.engines[key] = sqlalchemy.create_engine(value)

        # We start each test case with a completely blank slate.
        self._reset_databases()

    def tearDown(self):
        # We destroy the test data store between each test case,
        # and recreate it, which ensures that we have no side-effects
        # from the tests
        self._reset_databases()
        super(BaseMigrationTestCase, self).tearDown()

    def execute_cmd(self, cmd=None):
        status, output = commands.getstatusoutput(cmd)
        LOG.debug(output)
        self.assertEqual(0, status,
                         "Failed to run: %s\n%s" % (cmd, output))

    @lockutils.synchronized('pgadmin', 'nova-', external=True)
    def _reset_pg(self, conn_pieces):
        (user, password, database, host) = \
            get_pgsql_connection_info(conn_pieces)
        os.environ['PGPASSWORD'] = password
        os.environ['PGUSER'] = user
        # note(boris-42): We must create and drop database, we can't
        # drop database which we have connected to, so for such
        # operations there is a special database template1.
        sqlcmd = ("psql -w -U %(user)s -h %(host)s -c"
                  " '%(sql)s' -d template1")

        sql = ("drop database if exists %(database)s;") % locals()
        droptable = sqlcmd % locals()
        self.execute_cmd(droptable)

        sql = ("create database %(database)s;") % locals()
        createtable = sqlcmd % locals()
        self.execute_cmd(createtable)

        os.unsetenv('PGPASSWORD')
        os.unsetenv('PGUSER')

    def _reset_databases(self):
        for key, engine in self.engines.items():
            conn_string = self.test_databases[key]
            conn_pieces = urlparse.urlparse(conn_string)
            engine.dispose()
            if conn_string.startswith('sqlite'):
                # We can just delete the SQLite database, which is
                # the easiest and cleanest solution
                db_path = conn_pieces.path.strip('/')
                if os.path.exists(db_path):
                    os.unlink(db_path)
                # No need to recreate the SQLite DB. SQLite will
                # create it for us if it's not there...
            elif conn_string.startswith('mysql'):
                # We can execute the MySQL client to destroy and re-create
                # the MYSQL database, which is easier and less error-prone
                # than using SQLAlchemy to do this via MetaData...trust me.
                (user, password, database, host) = \
                        get_mysql_connection_info(conn_pieces)
                sql = ("drop database if exists %(database)s; "
                        "create database %(database)s;") % locals()
                cmd = ("mysql -u \"%(user)s\" %(password)s -h %(host)s "
                       "-e \"%(sql)s\"") % locals()
                self.execute_cmd(cmd)
            elif conn_string.startswith('postgresql'):
                self._reset_pg(conn_pieces)

    def _test_mysql_opportunistically(self):
        # Test that table creation on mysql only builds InnoDB tables
        if not _have_mysql(self.USER, self.PASSWD, self.DATABASE):
            self.skipTest("mysql not available")
        # add this to the global lists to make reset work with it, it's removed
        # automatically in tearDown so no need to clean it up here.
        connect_string = _get_connect_string("mysql", self.USER, self.PASSWD,
                self.DATABASE)
        (user, password, database, host) = \
                get_mysql_connection_info(urlparse.urlparse(connect_string))
        engine = sqlalchemy.create_engine(connect_string)
        self.engines[database] = engine
        self.test_databases[database] = connect_string

        # build a fully populated mysql database with all the tables
        self._reset_databases()
        self._walk_versions(engine, False, False)

        connection = engine.connect()
        # sanity check
        total = connection.execute("SELECT count(*) "
                                   "from information_schema.TABLES "
                                   "where TABLE_SCHEMA='%(database)s'" %
                                   locals())
        self.assertTrue(total.scalar() > 0, "No tables found. Wrong schema?")

        noninnodb = connection.execute("SELECT count(*) "
                                       "from information_schema.TABLES "
                                       "where TABLE_SCHEMA='%(database)s' "
                                       "and ENGINE!='InnoDB' "
                                       "and TABLE_NAME!='migrate_version'" %
                                       locals())
        count = noninnodb.scalar()
        self.assertEqual(count, 0, "%d non InnoDB tables created" % count)
        connection.close()

    def _test_postgresql_opportunistically(self):
        # Test postgresql database migration walk
        if not _have_postgresql(self.USER, self.PASSWD, self.DATABASE):
            self.skipTest("postgresql not available")
        # add this to the global lists to make reset work with it, it's removed
        # automatically in tearDown so no need to clean it up here.
        connect_string = _get_connect_string("postgres", self.USER,
                self.PASSWD, self.DATABASE)
        engine = sqlalchemy.create_engine(connect_string)
        (user, password, database, host) = \
                get_mysql_connection_info(urlparse.urlparse(connect_string))
        self.engines[database] = engine
        self.test_databases[database] = connect_string

        # build a fully populated postgresql database with all the tables
        self._reset_databases()
        self._walk_versions(engine, False, False)

    def _walk_versions(self, engine=None, snake_walk=False, downgrade=True):
        # Determine latest version script from the repo, then
        # upgrade from 1 through to the latest, with no data
        # in the databases. This just checks that the schema itself
        # upgrades successfully.

        # Place the database under version control
        self.migration_api.version_control(engine,
                self.REPOSITORY,
                self.INIT_VERSION)
        self.assertEqual(self.INIT_VERSION,
                self.migration_api.db_version(engine,
                                         self.REPOSITORY))

        LOG.debug('latest version is %s' % self.REPOSITORY.latest)
        versions = range(self.INIT_VERSION + 1, self.REPOSITORY.latest + 1)

        for version in versions:
            # upgrade -> downgrade -> upgrade
            self._migrate_up(engine, version, with_data=True)
            if snake_walk:
                downgraded = self._migrate_down(
                        engine, version - 1, with_data=True)
                if downgraded:
                    self._migrate_up(engine, version)

        if downgrade:
            # Now walk it back down to 0 from the latest, testing
            # the downgrade paths.
            for version in reversed(versions):
                # downgrade -> upgrade -> downgrade
                downgraded = self._migrate_down(engine, version - 1)

                if snake_walk and downgraded:
                    self._migrate_up(engine, version)
                    self._migrate_down(engine, version - 1)

    def _migrate_down(self, engine, version, with_data=False):
        try:
            self.migration_api.downgrade(engine, self.REPOSITORY, version)
        except NotImplementedError:
            # NOTE(sirp): some migrations, namely release-level
            # migrations, don't support a downgrade.
            return False

        self.assertEqual(version,
                         self.migration_api.db_version(engine,
                                                  self.REPOSITORY))

        # NOTE(sirp): `version` is what we're downgrading to (i.e. the 'target'
        # version). So if we have any downgrade checks, they need to be run for
        # the previous (higher numbered) migration.
        if with_data:
            post_downgrade = getattr(
                    self, "_post_downgrade_%03d" % (version + 1), None)
            if post_downgrade:
                post_downgrade(engine)

        return True

    def _migrate_up(self, engine, version, with_data=False):
        """migrate up to a new version of the db.

        We allow for data insertion and post checks at every
        migration version with special _pre_upgrade_### and
        _check_### functions in the main test.
        """
        # NOTE(sdague): try block is here because it's impossible to debug
        # where a failed data migration happens otherwise
        try:
            if with_data:
                data = None
                pre_upgrade = getattr(
                        self, "_pre_upgrade_%03d" % version, None)
                if pre_upgrade:
                    data = pre_upgrade(engine)

            self.migration_api.upgrade(engine, self.REPOSITORY, version)
            self.assertEqual(version,
                             self.migration_api.db_version(engine,
                                                           self.REPOSITORY))
            if with_data:
                check = getattr(self, "_check_%03d" % version, None)
                if check:
                    check(engine, data)
        except Exception:
            LOG.error("Failed to migrate to version %s on engine %s" %
                      (version, engine))
            raise


class TestNovaMigrations(BaseMigrationTestCase, CommonTestsMixIn):
    """Test sqlalchemy-migrate migrations."""
    USER = "openstack_citest"
    PASSWD = "openstack_citest"
    DATABASE = "openstack_citest"

    def __init__(self, *args, **kwargs):
        super(TestNovaMigrations, self).__init__(*args, **kwargs)

        self.DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__),
                                       'test_migrations.conf')
        # Test machines can set the NOVA_TEST_MIGRATIONS_CONF variable
        # to override the location of the config file for migration testing
        self.CONFIG_FILE_PATH = os.environ.get('NOVA_TEST_MIGRATIONS_CONF',
                                      self.DEFAULT_CONFIG_FILE)
        self.MIGRATE_FILE = nova.db.sqlalchemy.migrate_repo.__file__
        self.REPOSITORY = repository.Repository(
                        os.path.abspath(os.path.dirname(self.MIGRATE_FILE)))

    def setUp(self):
        super(TestNovaMigrations, self).setUp()

        if self.migration is None:
            self.migration = __import__('nova.db.migration',
                    globals(), locals(), ['INIT_VERSION'], -1)
            self.INIT_VERSION = self.migration.INIT_VERSION
        if self.migration_api is None:
            temp = __import__('nova.db.sqlalchemy.migration',
                    globals(), locals(), ['versioning_api'], -1)
            self.migration_api = temp.versioning_api

    def _pre_upgrade_134(self, engine):
        now = timeutils.utcnow()
        data = [{
            'id': 1,
            'uuid': '1d739808-d7ec-4944-b252-f8363e119755',
            'mac': '00:00:00:00:00:01',
            'start_period': now,
            'last_refreshed': now + datetime.timedelta(seconds=10),
            'bw_in': 100000,
            'bw_out': 200000,
            }, {
            'id': 2,
            'uuid': '1d739808-d7ec-4944-b252-f8363e119756',
            'mac': '2a:f2:48:31:c1:60',
            'start_period': now,
            'last_refreshed': now + datetime.timedelta(seconds=20),
            'bw_in': 1000000000,
            'bw_out': 200000000,
            }, {
            'id': 3,
            # This is intended to be the same as above.
            'uuid': '1d739808-d7ec-4944-b252-f8363e119756',
            'mac': '00:00:00:00:00:02',
            'start_period': now,
            'last_refreshed': now + datetime.timedelta(seconds=30),
            'bw_in': 0,
            'bw_out': 0,
            }]

        bw_usage_cache = get_table(engine, 'bw_usage_cache')
        engine.execute(bw_usage_cache.insert(), data)
        return data

    def _check_134(self, engine, data):
        bw_usage_cache = get_table(engine, 'bw_usage_cache')

        # Checks if both columns have been successfuly created.
        self.assertIn('last_ctr_in', bw_usage_cache.c)
        self.assertIn('last_ctr_out', bw_usage_cache.c)

        # Checks if all rows have been inserted.
        bw_items = bw_usage_cache.select().execute().fetchall()
        self.assertEqual(len(bw_items), 3)

        bw = bw_usage_cache.select(
            bw_usage_cache.c.id == 1).execute().first()

        # New columns have 'NULL' as default value.
        self.assertEqual(bw['last_ctr_in'], None)
        self.assertEqual(bw['last_ctr_out'], None)

        self.assertEqual(data[0]['mac'], bw['mac'])

    # migration 141, update migrations instance uuid
    def _pre_upgrade_141(self, engine):
        data = {
            'instance_uuid': str(uuid.uuid4())
            }
        migrations = get_table(engine, 'migrations')
        engine.execute(migrations.insert(), data)
        result = migrations.insert().values(data).execute()
        data['id'] = result.inserted_primary_key[0]
        return data

    def _check_141(self, engine, data):
        migrations = get_table(engine, 'migrations')
        row = migrations.select(
            migrations.c.id == data['id']).execute().first()
        # Check that change to String(36) went alright
        self.assertEqual(data['instance_uuid'], row['instance_uuid'])

    # migration 146, availability zone transition
    def _pre_upgrade_146(self, engine):
        data = {
            'availability_zone': 'custom_az',
            'name': 'name',
            }

        aggregates = get_table(engine, 'aggregates')
        result = aggregates.insert().values(data).execute()
        # NOTE(sdague) it's important you don't insert keys by value in
        # postgresql, because its autoincrement counter won't get updated
        data['id'] = result.inserted_primary_key[0]
        return data

    def _check_146(self, engine, data):
        aggregate_md = get_table(engine, 'aggregate_metadata')
        md = aggregate_md.select(
            aggregate_md.c.aggregate_id == data['id']).execute().first()
        self.assertEqual(data['availability_zone'], md['value'])

    def _post_downgrade_146(self, engine):
        # Downgrade should delete availability_zone aggregate_metadata entries
        aggregate_md = get_table(engine, 'aggregate_metadata')
        num_azs = aggregate_md.count().where(
                aggregate_md.c.key == 'availability_zone').execute().scalar()
        self.assertEqual(0, num_azs)

    # migration 147, availability zone transition for services
    def _pre_upgrade_147(self, engine):
        az = 'test_zone'
        host1 = 'compute-host1'
        host2 = 'compute-host2'
        # start at id == 2 because we already inserted one
        data = [
            {'id': 1, 'host': host1,
             'binary': 'nova-compute', 'topic': 'compute',
             'report_count': 0, 'availability_zone': az},
            {'id': 2, 'host': 'sched-host',
             'binary': 'nova-scheduler', 'topic': 'scheduler',
             'report_count': 0, 'availability_zone': 'ignore_me'},
            {'id': 3, 'host': host2,
             'binary': 'nova-compute', 'topic': 'compute',
             'report_count': 0, 'availability_zone': az},
            ]

        services = get_table(engine, 'services')
        engine.execute(services.insert(), data)
        self._pre_upgrade_147_no_duplicate_aggregate_hosts(engine)
        return data

    def _pre_upgrade_147_no_duplicate_aggregate_hosts(self, engine):
        engine.execute(get_table(engine, 'aggregate_metadata').insert(), [
            {'aggregate_id': 1,
             'key': 'availability_zone',
             'value': 'custom_az'}])

        engine.execute(get_table(engine, 'aggregate_hosts').insert(), [
            {'aggregate_id': 1,
             'host': 'compute-host3'}])

        engine.execute(get_table(engine, 'services').insert(), [
            {'id': 99, 'host': 'compute-host3',
             'binary': 'nova-compute', 'topic': 'compute',
             'report_count': 0, 'availability_zone': 'custom_az'}])

    def _check_147(self, engine, data):
        aggregate_md = get_table(engine, 'aggregate_metadata')
        aggregate_hosts = get_table(engine, 'aggregate_hosts')
        # NOTE(sdague): hard coded to id == 2, because we added to
        # aggregate_metadata previously
        for item in data:
            md = aggregate_md.select(
                aggregate_md.c.aggregate_id == 2).execute().first()
            if item['binary'] == "nova-compute":
                self.assertEqual(item['availability_zone'], md['value'])

        host = aggregate_hosts.select(
            aggregate_hosts.c.aggregate_id == 2
            ).execute().first()
        self.assertEqual(host['host'], data[0]['host'])

        # NOTE(sdague): id 3 is just non-existent
        host = aggregate_hosts.select(
            aggregate_hosts.c.aggregate_id == 3
            ).execute().first()
        self.assertEqual(host, None)

        self._check_147_no_duplicate_aggregate_hosts(engine, data)

    def _check_147_no_duplicate_aggregate_hosts(self, engine, data):
        aggregate_hosts = get_table(engine, 'aggregate_hosts')
        agg1_hosts = [h['host'] for h in aggregate_hosts.select(
            aggregate_hosts.c.aggregate_id == 1
            ).execute().fetchall()]
        self.assertEqual(['compute-host3'], agg1_hosts)

    # migration 149, changes IPAddr storage format
    def _pre_upgrade_149(self, engine):
        provider_fw_rules = get_table(engine, 'provider_fw_rules')
        console_pools = get_table(engine, 'console_pools')
        data = {
            'provider_fw_rules':
                [
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "127.0.0.1/30"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "128.128.128.128/16"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "128.128.128.128/32"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "2001:db8::1:2/48"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "::1/64"},
                {'protocol': 'tcp', 'from_port': 1234, 'to_port': 1234,
                 'cidr': "0000:0000:0000:2013:0000:6535:abcd:ef11/64"},
                {'protocol': 'tcp', 'from_port': 1234, 'to_port': 1234,
                 'cidr': "0000:1020:0000:2013:0000:6535:abcd:ef11/128"},
                ],
            'console_pools':
                [
                {'address': '10.10.10.10'},
                {'address': '128.100.100.100'},
                {'address': '2002:2002:2002:2002:2002:2002:2002:2002'},
                {'address': '::1'},
                {'address': '0000:0000:0000:2013:0000:6535:abcd:ef11'}
                ]
            }

        engine.execute(provider_fw_rules.insert(), data['provider_fw_rules'])

        for pool in data['console_pools']:
            engine.execute(console_pools.insert(), pool)

        return data

    def _check_149(self, engine, data):
        provider_fw_rules = get_table(engine, 'provider_fw_rules')
        result = provider_fw_rules.select().execute()

        iplist = map(lambda x: str(netaddr.IPNetwork(x['cidr'])),
                     data['provider_fw_rules'])

        for row in result:
            self.assertIn(str(netaddr.IPNetwork(row['cidr'])), iplist)

        console_pools = get_table(engine, 'console_pools')
        result = console_pools.select().execute()

        iplist = map(lambda x: str(netaddr.IPAddress(x['address'])),
                     data['console_pools'])

        for row in result:
            self.assertIn(str(netaddr.IPAddress(row['address'])), iplist)

    # migration 151 - changes period_beginning and period_ending to DateTime
    def _pre_upgrade_151(self, engine):
        task_log = get_table(engine, 'task_log')
        data = {
            'task_name': 'The name of the task',
            'state': 'The state of the task',
            'host': 'compute-host1',
            'period_beginning': str(datetime.datetime(2013, 02, 11)),
            'period_ending': str(datetime.datetime(2013, 02, 12)),
            'message': 'The task_log message',
            }
        result = task_log.insert().values(data).execute()
        data['id'] = result.inserted_primary_key[0]
        return data

    def _check_151(self, engine, data):
        task_log = get_table(engine, 'task_log')
        row = task_log.select(task_log.c.id == data['id']).execute().first()
        self.assertTrue(isinstance(row['period_beginning'],
            datetime.datetime))
        self.assertTrue(isinstance(row['period_ending'],
            datetime.datetime))
        self.assertEqual(
            data['period_beginning'], str(row['period_beginning']))
        self.assertEqual(data['period_ending'], str(row['period_ending']))

    # migration 152 - convert deleted from boolean to int
    def _pre_upgrade_152(self, engine):
        host1 = 'compute-host1'
        host2 = 'compute-host2'
        # NOTE(sdague): start at #4 because services data already in table
        # from 147
        services_data = [
            {'id': 4, 'host': host1, 'binary': 'nova-compute',
             'report_count': 0, 'topic': 'compute', 'deleted': False},
            {'id': 5, 'host': host1, 'binary': 'nova-compute',
             'report_count': 0, 'topic': 'compute', 'deleted': True}
            ]
        volumes_data = [
            {'id': 'first', 'host': host1, 'deleted': False},
            {'id': 'second', 'host': host2, 'deleted': True}
            ]

        services = get_table(engine, 'services')
        engine.execute(services.insert(), services_data)

        volumes = get_table(engine, 'volumes')
        engine.execute(volumes.insert(), volumes_data)
        return dict(services=services_data, volumes=volumes_data)

    def _check_152(self, engine, data):
        services = get_table(engine, 'services')
        service = services.select(services.c.id == 4).execute().first()
        self.assertEqual(0, service.deleted)
        service = services.select(services.c.id == 5).execute().first()
        self.assertEqual(service.id, service.deleted)

        volumes = get_table(engine, 'volumes')
        volume = volumes.select(volumes.c.id == "first").execute().first()
        self.assertEqual("", volume.deleted)
        volume = volumes.select(volumes.c.id == "second").execute().first()
        self.assertEqual(volume.id, volume.deleted)

    # migration 153, copy flavor information into system_metadata
    def _pre_upgrade_153(self, engine):
        fake_types = [
            dict(id=10, name='type1', memory_mb=128, vcpus=1,
                 root_gb=10, ephemeral_gb=0, flavorid="1", swap=0,
                 rxtx_factor=1.0, vcpu_weight=1, disabled=False,
                 is_public=True),
            dict(id=11, name='type2', memory_mb=512, vcpus=1,
                 root_gb=10, ephemeral_gb=5, flavorid="2", swap=0,
                 rxtx_factor=1.5, vcpu_weight=2, disabled=False,
                 is_public=True),
            dict(id=12, name='type3', memory_mb=128, vcpus=1,
                 root_gb=10, ephemeral_gb=0, flavorid="3", swap=0,
                 rxtx_factor=1.0, vcpu_weight=1, disabled=False,
                 is_public=False),
            dict(id=13, name='type4', memory_mb=128, vcpus=1,
                 root_gb=10, ephemeral_gb=0, flavorid="4", swap=0,
                 rxtx_factor=1.0, vcpu_weight=None, disabled=True,
                 is_public=True),
            dict(id=14, name='type5', memory_mb=128, vcpus=1,
                 root_gb=10, ephemeral_gb=0, flavorid="5", swap=0,
                 rxtx_factor=1.0, vcpu_weight=1, disabled=True,
                 is_public=False),
            ]

        fake_instances = [
            dict(uuid='m153-uuid1', instance_type_id=10, deleted=0),
            dict(uuid='m153-uuid2', instance_type_id=11, deleted=0),
            dict(uuid='m153-uuid3', instance_type_id=12, deleted=0),
            dict(uuid='m153-uuid4', instance_type_id=13, deleted=0),
            # NOTE(danms): no use of type5
            ]

        instances = get_table(engine, 'instances')
        instance_types = get_table(engine, 'instance_types')
        engine.execute(instance_types.insert(), fake_types)
        engine.execute(instances.insert(), fake_instances)

        return fake_types, fake_instances

    def _check_153(self, engine, data):
        fake_types, fake_instances = data
        # NOTE(danms): Fetch all the tables and data from scratch after change
        instances = get_table(engine, 'instances')
        instance_types = get_table(engine, 'instance_types')
        sys_meta = get_table(engine, 'instance_system_metadata')

        # Collect all system metadata, indexed by instance_uuid
        metadata = collections.defaultdict(dict)
        for values in sys_meta.select().execute():
            metadata[values['instance_uuid']][values['key']] = values['value']

        # Taken from nova/compute/api.py
        instance_type_props = ['id', 'name', 'memory_mb', 'vcpus',
                               'root_gb', 'ephemeral_gb', 'flavorid',
                               'swap', 'rxtx_factor', 'vcpu_weight']

        for instance in fake_instances:
            inst_sys_meta = metadata[instance['uuid']]
            inst_type = fake_types[instance['instance_type_id'] - 10]
            for prop in instance_type_props:
                prop_name = 'instance_type_%s' % prop
                self.assertIn(prop_name, inst_sys_meta)
                if prop == "vcpu_weight":
                    # NOTE(danms) vcpu_weight can be NULL
                    self.assertEqual(inst_sys_meta[prop_name],
                                     inst_type[prop] and str(inst_type[prop])
                                     or None)
                else:
                    self.assertEqual(str(inst_sys_meta[prop_name]),
                                     str(inst_type[prop]))

    # migration 154, add shadow tables for deleted data
    # There are 53 shadow tables but we only test one
    # There are additional tests in test_db_api.py
    def _pre_upgrade_154(self, engine):
        meta = sqlalchemy.schema.MetaData()
        meta.reflect(engine)
        table_names = meta.tables.keys()
        for table_name in table_names:
            self.assertFalse(table_name.startswith("_shadow"))

    def _check_154(self, engine, data):
        meta = sqlalchemy.schema.MetaData()
        meta.reflect(engine)
        table_names = set(meta.tables.keys())
        for table_name in table_names:
            if table_name.startswith("shadow_"):
                shadow_name = table_name
                base_name = table_name.replace("shadow_", "")
                self.assertIn(base_name, table_names)
            else:
                base_name = table_name
                shadow_name = "shadow_" + table_name
                self.assertIn(shadow_name, table_names)
            shadow_table = get_table(engine, shadow_name)
            base_table = get_table(engine, base_name)
            base_columns = []
            shadow_columns = []
            for column in base_table.columns:
                base_columns.append(column)
            for column in shadow_table.columns:
                shadow_columns.append(column)
            for ii, base_column in enumerate(base_columns):
                shadow_column = shadow_columns[ii]
            self.assertEqual(base_column.name, shadow_column.name)
            # NullType needs a special case.  We end up with NullType on sqlite
            # where bigint is not defined.
            if isinstance(base_column.type, sqlalchemy.types.NullType):
                self.assertTrue(isinstance(shadow_column.type,
                                           sqlalchemy.types.NullType))
            else:
                # Identical types do not test equal because sqlalchemy does not
                # override __eq__, but if we stringify them then they do.
                self.assertEqual(str(base_column.type),
                                 str(shadow_column.type))

    # migration 156 - introduce CIDR type
    def _pre_upgrade_156(self, engine):
        # assume the same data as from 149
        data = {
            'provider_fw_rules':
                [
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "127.0.0.1/30"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "128.128.128.128/16"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "128.128.128.128/32"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "2001:db8::1:2/48"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "::1/64"},
                {'protocol': 'tcp', 'from_port': 1234, 'to_port': 1234,
                 'cidr': "0000:0000:0000:2013:0000:6535:abcd:ef11/64"},
                {'protocol': 'tcp', 'from_port': 1234, 'to_port': 1234,
                 'cidr': "0000:1020:0000:2013:0000:6535:abcd:ef11/128"},
                ],
            'console_pools':
                [
                {'address': '10.10.10.10'},
                {'address': '128.100.100.100'},
                {'address': '2002:2002:2002:2002:2002:2002:2002:2002'},
                {'address': '::1'},
                {'address': '0000:0000:0000:2013:0000:6535:abcd:ef11'}
                ]
            }
        return data

    def _check_156(self, engine, data):
        # recheck the 149 data
        self._check_149(engine, data)

    def _pre_upgrade_158(self, engine):
        networks = get_table(engine, 'networks')
        data = [
            {'vlan': 1, 'deleted': 0},
            {'vlan': 1, 'deleted': 0},
            {'vlan': 1, 'deleted': 0},
        ]

        for item in data:
            networks.insert().values(item).execute()
        return data

    def _check_158(self, engine, data):
        networks = get_table(engine, 'networks')
        rows = networks.select().\
                    where(networks.c.deleted != networks.c.id).\
                    execute().\
                    fetchall()
        self.assertEqual(len(rows), 1)

    def _pre_upgrade_159(self, engine):
        data = {
            'provider_fw_rules':
                [
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "127.0.0.1/30"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "128.128.128.128/16"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "128.128.128.128/32"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "2001:db8::1:2/48"},
                {'protocol': 'tcp', 'from_port': 1234,
                 'to_port': 1234, 'cidr': "::1/64"},
                {'protocol': 'tcp', 'from_port': 1234, 'to_port': 1234,
                 'cidr': "0000:0000:0000:2013:0000:6535:abcd:ef11/64"},
                {'protocol': 'tcp', 'from_port': 1234, 'to_port': 1234,
                 'cidr': "0000:1020:0000:2013:0000:6535:abcd:ef11/128"},
                ],
            'console_pools':
                [
                {'address': '10.10.10.10'},
                {'address': '128.100.100.100'},
                {'address': '2002:2002:2002:2002:2002:2002:2002:2002'},
                {'address': '::1'},
                {'address': '0000:0000:0000:2013:0000:6535:abcd:ef11'}
                ]
            }
        return data

    # migration 159 - revert ip column size
    def _check_159(self, engine, data):
        dialect = engine.url.get_dialect()
        # NOTE(maurosr): check if column length is 39 again (it currently makes
        # sense only for mysql)
        if dialect not in [postgresql.dialect, sqlite.dialect]:
            console_pools = get_table(engine, 'console_pools')
            self.assertEqual(console_pools.columns['address'].type.length, 39)
        # recheck the 149 data
        self._check_149(engine, data)

    def _post_downgrade_159(self, engine):
        dialect = engine.url.get_dialect()
        # NOTE(maurosr): check if column length is 43 again (it currently makes
        # sense only for mysql)
        if dialect not in [postgresql.dialect, sqlite.dialect]:
            console_pools = get_table(engine, 'console_pools')
            self.assertEqual(console_pools.columns['address'].type.length, 43)

    # migration 160, fix system_metadata NULL deleted entries to be 0
    def _pre_upgrade_160(self, engine):
        fake_instances = [
            dict(uuid='m160-uuid1'),
            dict(uuid='m160-uuid2'),
            dict(uuid='m160-uuid3'),
            ]
        fake_sys_meta = [
            dict(instance_uuid='m160-uuid1', key='foo', value='bar'),
            dict(instance_uuid='m160-uuid2', key='foo2', value='bar2'),
            dict(instance_uuid='m160-uuid3', key='foo3', value='bar3')]

        instances = get_table(engine, 'instances')
        sys_meta = get_table(engine, 'instance_system_metadata')
        engine.execute(instances.insert(), fake_instances)

        # Create the metadata entries
        data = {}
        for sm in fake_sys_meta:
            result = sys_meta.insert().values(sm).execute()
            sm['id'] = result.inserted_primary_key[0]
            data[sm['id']] = sm

        # Make sure the entries in the DB for 'deleted' are None.
        our_ids = data.keys()
        results = sys_meta.select().where(sys_meta.c.id.in_(our_ids)).\
                                          execute()
        results = list(results)
        self.assertEqual(len(our_ids), len(results))
        for result in results:
            self.assertEqual(result['deleted'], None)
        return data

    def _check_160(self, engine, data):
        our_ids = data.keys()
        sys_meta = get_table(engine, 'instance_system_metadata')
        results = sys_meta.select().where(sys_meta.c.id.in_(our_ids)).\
                                    execute()
        results = list(results)
        self.assertEqual(len(our_ids), len(results))
        for result in results:
            the_id = result['id']
            # Make sure this is now 0.
            self.assertEqual(result['deleted'], 0)
            # Make sure nothing else changed.
            for key, value in data[the_id].items():
                self.assertEqual(value, result[key])

    # migration 161, fix system_metadata "None" values should be NULL
    def _pre_upgrade_161(self, engine):
        fake_instances = [dict(uuid='m161-uuid1')]
        sm_base = dict(instance_uuid='m161-uuid1', value=None)
        now = timeutils.utcnow().replace(microsecond=0)
        fake_sys_meta = [
            # Should be fixed
            dict(sm_base, key='instance_type_foo', value='None'),
            dict(sm_base, key='instance_type_bar', value='88 mph'),

            # Should be unaffected
            dict(sm_base, key='instance_type_name', value='None'),
            dict(sm_base, key='instance_type_flavorid', value='None'),
            dict(sm_base, key='foo', value='None'),
            dict(sm_base, key='instance_type_bat'),
            dict(sm_base, key='instance_type_baz', created_at=now),
            ]

        instances = get_table(engine, 'instances')
        sys_meta = get_table(engine, 'instance_system_metadata')
        engine.execute(instances.insert(), fake_instances)

        data = {}
        for sm in fake_sys_meta:
            result = sys_meta.insert().values(sm).execute()
            sm['id'] = result.inserted_primary_key[0]
            data[sm['id']] = sm

        return data

    def _check_161(self, engine, data):
        our_ids = data.keys()
        sys_meta = get_table(engine, 'instance_system_metadata')
        results = sys_meta.select().where(sys_meta.c.id.in_(our_ids)).\
                                    execute()
        results = list(results)
        self.assertEqual(len(our_ids), len(results))
        for result in results:
            the_id = result['id']
            key = result['key']
            value = result['value']
            original = data[the_id]

            if key == 'instance_type_baz':
                # Neither value nor created_at should have been altered
                self.assertEqual(result['value'], original['value'])
                self.assertEqual(result['created_at'], original['created_at'])
            elif key in ['instance_type_name', 'instance_type_flavorid']:
                # These should not have their values changed, but should
                # have corrected created_at stamps
                self.assertEqual(result['value'], original['value'])
                self.assertTrue(isinstance(result['created_at'],
                                           datetime.datetime))
            elif key.startswith('instance_type'):
                # Values like instance_type_% should be stamped and values
                # converted from 'None' to None where appropriate
                self.assertEqual(result['value'],
                                 None if original['value'] == 'None'
                                 else original['value'])
                self.assertTrue(isinstance(result['created_at'],
                                           datetime.datetime))
            else:
                # None of the non-instance_type values should have
                # been touched. Since we didn't set created_at on any
                # of them, they should all still be None.
                self.assertEqual(result['value'], original['value'])
                self.assertEqual(result['created_at'], None)


class TestBaremetalMigrations(BaseMigrationTestCase, CommonTestsMixIn):
    """Test sqlalchemy-migrate migrations."""
    USER = "openstack_citest"
    PASSWD = "openstack_citest"
    DATABASE = "openstack_baremetal_citest"

    def __init__(self, *args, **kwargs):
        super(TestBaremetalMigrations, self).__init__(*args, **kwargs)

        self.DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__),
                                       'test_baremetal_migrations.conf')
        # Test machines can set the NOVA_TEST_MIGRATIONS_CONF variable
        # to override the location of the config file for migration testing
        self.CONFIG_FILE_PATH = os.environ.get(
                'BAREMETAL_TEST_MIGRATIONS_CONF',
                self.DEFAULT_CONFIG_FILE)
        self.MIGRATE_FILE = \
                nova.virt.baremetal.db.sqlalchemy.migrate_repo.__file__
        self.REPOSITORY = repository.Repository(
                        os.path.abspath(os.path.dirname(self.MIGRATE_FILE)))

    def setUp(self):
        super(TestBaremetalMigrations, self).setUp()

        if self.migration is None:
            self.migration = __import__('nova.virt.baremetal.db.migration',
                    globals(), locals(), ['INIT_VERSION'], -1)
            self.INIT_VERSION = self.migration.INIT_VERSION
        if self.migration_api is None:
            temp = __import__('nova.virt.baremetal.db.sqlalchemy.migration',
                    globals(), locals(), ['versioning_api'], -1)
            self.migration_api = temp.versioning_api

    def _pre_upgrade_002(self, engine):
        data = [{'id': 1, 'key': 'fake-key', 'image_path': '/dev/null',
                 'pxe_config_path': '/dev/null/', 'root_mb': 0, 'swap_mb': 0}]
        table = get_table(engine, 'bm_deployments')
        engine.execute(table.insert(), data)
        return data

    def _check_002(self, engine, data):
        self.assertRaises(sqlalchemy.exc.NoSuchTableError,
                          get_table, engine, 'bm_deployments')

    def _post_downgrade_004(self, engine):
        bm_nodes = get_table(engine, 'bm_nodes')
        self.assertNotIn(u'instance_name', [c.name for c in bm_nodes.columns])
