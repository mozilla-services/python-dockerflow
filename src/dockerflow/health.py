# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.

# Django check IDs
INFO_CANT_CHECK_MIGRATIONS = 'dockerflow.health.I001'
WARNING_UNAPPLIED_MIGRATION = 'dockerflow.health.W001'
ERROR_CANNOT_CONNECT_DATABASE = 'dockerflow.health.E001'
ERROR_UNUSABLE_DATABASE = 'dockerflow.health.E002'
ERROR_MISCONFIGURED_DATABASE = 'dockerflow.health.E003'
ERROR_CANNOT_CONNECT_REDIS = 'dockerflow.health.E004'
ERROR_MISSING_REDIS_CLIENT = 'dockerflow.health.E005'
ERROR_MISCONFIGURED_REDIS = 'dockerflow.health.E006'
ERROR_REDIS_PING_FAILED = 'dockerflow.health.E007'

# Flask check IDs
ERROR_DB_API_EXCEPTION = 'dockerflow.health.E008'
ERROR_SQLALCHEMY_EXCEPTION = 'dockerflow.health.E009'
ERROR_REDIS_EXCEPTION = 'dockerflow.health.E010'
