#
# Methods that return File(pathid,dirname,filename) for searches
#

import datetime
import sqlite3

CACHE_SIZE = 2000000
SQL_SET_CACHE = "PRAGMA cache_size = {};".format(CACHE_SIZE)

class SLGSQL:
    def __init__(self,fname):
        self.conn = sqlite3.connect(fname)
        self.conn.row_factory = sqlite3.Row
        self.conn.cursor().execute(SQL_SET_CACHE)

    def iso_now(self):
        """Report current time in ISO-8601 format"""
        return datetime.datetime.now().isoformat()[0:19]

    def send_schema(self,schema):
        """Create the schema if it doesn't exist."""
        c = self.conn.cursor()
        for line in schema.split(";"):
            c.execute(line)

    def execselect(self, sql, vals=()):
        """Execute a SQL query and return the first line"""
        c = self.conn.cursor()
        c.execute(sql, vals)
        return c.fetchone()

