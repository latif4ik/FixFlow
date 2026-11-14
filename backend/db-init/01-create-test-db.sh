#!/bin/sh
# Runs once on first initialisation of the Postgres data volume.
# Creates a second database used exclusively by the test suite.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	CREATE DATABASE fixflow_test OWNER "$POSTGRES_USER";
SQL
